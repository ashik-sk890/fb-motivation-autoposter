"""Modern visual artwork engine supporting AI image APIs and rich illustrated SVG scenes."""

from __future__ import annotations

import base64
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from src.config import AppConfig


def _is_valid_image_bytes(data: bytes) -> bool:
    """Verify binary data begins with PNG, JPEG, or WebP magic bytes and is non-trivial."""
    if len(data) < 15_000:
        return False
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = data.startswith(b"\xff\xd8\xff")
    is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return is_png or is_jpg or is_webp


def _download_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 45) -> bytes:
    """Download bytes via stdlib urllib with a standard User-Agent."""
    req_headers = {"User-Agent": "AttitudeAutoposter/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _try_gemini_imagen(prompt: str, api_key: str) -> bytes | None:
    """Attempt artwork generation via Google AI Studio native Gemini image models."""
    if not api_key:
        return None
    for model in ("gemini-3.1-flash-image", "gemini-2.5-flash-image", "gemini-nano-banana-2.1"):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                parts = parsed["candidates"][0]["content"]["parts"]
                for part in parts:
                    inline = part.get("inlineData") or {}
                    if inline.get("data"):
                        data = base64.b64decode(inline["data"])
                        if _is_valid_image_bytes(data):
                            return data
        except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
            continue
    return None


def _try_huggingface(prompt: str, token: str) -> bytes | None:
    """Attempt fast image generation via Hugging Face Inference FLUX.1-schnell."""
    if not token:
        return None
    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    payload = json.dumps({"inputs": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "image/jpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            return data if _is_valid_image_bytes(data) else None
    except (urllib.error.URLError, TimeoutError):
        return None


def _try_openai_image(prompt: str, api_key: str) -> bytes | None:
    """Attempt image generation via OpenAI Images API if configured."""
    if not api_key:
        return None
    payload = json.dumps(
        {
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "medium",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=75) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
            b64 = parsed["data"][0].get("b64_json", "")
            if b64:
                data = base64.b64decode(b64)
                return data if _is_valid_image_bytes(data) else None
            img_url = parsed["data"][0].get("url", "")
            if img_url:
                data = _download_bytes(img_url)
                return data if _is_valid_image_bytes(data) else None
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None
    return None


def _multipart_form_payload(fields: dict[str, str]) -> tuple[bytes, str]:
    """Encode string fields as multipart/form-data body + Content-Type header."""
    boundary = f"----CfFluxBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, val in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{val}\r\n'.encode("utf-8")
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _try_cloudflare_flux(
    prompt: str,
    account_id: str,
    api_token: str,
    fast_tier: bool = False,
) -> bytes | None:
    """Attempt free-tier FLUX.2 9:16 portrait (or lightweight FLUX.1-schnell for secondary carousel slides)."""
    if not (account_id and api_token):
        return None
    base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
    attempts: list[tuple[str, bytes, str]] = []
    if not fast_tier:
        for model, fields in (
            ("@cf/black-forest-labs/flux-2-klein-9b", {"prompt": prompt, "width": "576", "height": "1024"}),
            ("@cf/black-forest-labs/flux-2-klein-4b", {"prompt": prompt, "width": "576", "height": "1024"}),
        ):
            body, ctype = _multipart_form_payload(fields)
            attempts.append((f"{base_url}/{model}", body, ctype))
    attempts.append(
        (
            f"{base_url}/@cf/black-forest-labs/flux-1-schnell",
            json.dumps({"prompt": prompt, "steps": 4}).encode("utf-8"),
            "application/json",
        )
    )

    for url, body, ctype in attempts:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": ctype,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=75) as resp:
                raw = resp.read()
                if _is_valid_image_bytes(raw):
                    return raw
                parsed = json.loads(raw.decode("utf-8"))
                if parsed.get("success") and (parsed.get("result") or {}).get("image"):
                    data = base64.b64decode(parsed["result"]["image"])
                    if _is_valid_image_bytes(data):
                        return data
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
            continue
    return None


def _try_composio_fal(prompt: str, config: AppConfig) -> bytes | None:
    """Attempt FLUX.1-schnell generation via Composio fal_ai instant account when opted in."""
    if not (config.use_composio_fal and config.composio_api_key.startswith("ck_")):
        return None
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "x-consumer-api-key": config.composio_api_key,
    }

    def call_fal(req_id: int, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                "arguments": {
                    "tools": [{"tool_slug": slug, "arguments": arguments}],
                    "sync_response_to_workbench": False,
                    "thought": f"Execute {slug} to generate card artwork.",
                    "current_step": slug,
                    "current_step_metric": "1/1",
                },
            },
        }
        req = urllib.request.Request(
            config.composio_mcp_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        for line in raw.splitlines():
            if line.startswith("data: "):
                rpc_obj = json.loads(line[6:])
                return json.loads(rpc_obj["result"]["content"][0]["text"])
        return json.loads(raw)

    try:
        sub = call_fal(
            701,
            "FAL_AI_SUBMIT_ASYNC_JOB",
            {
                "model_id": "fal-ai/flux/schnell",
                "input": {
                    "prompt": prompt[:950],
                    "image_size": {"width": 512, "height": 512},
                    "num_images": 1,
                    "num_inference_steps": 4,
                    "enable_safety_checker": True,
                    "output_format": "jpeg",
                },
            },
        )
        req_id = (((sub.get("data") or {}).get("results") or [{}])[0].get("response") or {}).get("data", {}).get("request_id")
        if not req_id:
            return None
        for idx in range(12):
            time.sleep(2.5)
            polled = call_fal(
                702 + idx,
                "FAL_AI_GET_QUEUE_REQUEST_RESULT",
                {"model_id": "fal-ai/flux/schnell", "request_id": req_id},
            )
            resp_data = (((polled.get("data") or {}).get("results") or [{}])[0].get("response") or {}).get("data") or {}
            images = resp_data.get("images") or (resp_data.get("response") or {}).get("images") or []
            if images and images[0].get("url"):
                img_bytes = _download_bytes(images[0]["url"], timeout=35)
                return img_bytes if _is_valid_image_bytes(img_bytes) else None
    except Exception:
        return None
    return None


def _try_deepai(prompt: str, api_key: str) -> bytes | None:
    """Attempt image generation via DeepAI text2img API (requires DeepAI Pro key)."""
    if not api_key:
        return None
    form = urllib.parse.urlencode(
        {
            "text": prompt,
            "grid_size": "1",
            "width": "768",
            "height": "1024",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.deepai.org/api/text2img",
        data=form,
        headers={
            "api-key": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
            out_url = parsed.get("output_url", "")
            if out_url:
                data = _download_bytes(out_url, timeout=45)
                return data if _is_valid_image_bytes(data) else None
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        return None
    return None


def _try_pollinations(prompt: str, api_key: str, seed: int) -> bytes | None:
    """Attempt artwork generation via Pollinations Flux endpoints with rate-limit backoff."""
    encoded = urllib.parse.quote(prompt, safe="")
    endpoints = [
        f"https://gen.pollinations.ai/image/{encoded}?model=flux&width=1080&height=1350&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1350&seed={seed}&nologo=true",
    ]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for url in endpoints:
        if "gen.pollinations.ai" in url and not api_key:
            continue
        for attempt in range(2):
            try:
                data = _download_bytes(url, headers=headers, timeout=55)
                if _is_valid_image_bytes(data):
                    return data
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt == 0:
                    retry_after = int(exc.headers.get("Retry-After", "6") or 6)
                    time.sleep(min(max(retry_after, 2), 12))
                    continue
                break
            except (urllib.error.URLError, TimeoutError):
                break
    return None


def build_illustrated_svg(layout_style: str, motif: str, accent: str, seed: int) -> str:
    """Create rich, high-visibility illustrated SVG scenes matched to each viral card style."""
    rng = random.Random(seed)

    if layout_style == "paper_sketch":
        return _svg_paper_sketch(motif)
    if layout_style == "sunrise_metaphor":
        return _svg_sunrise_crimson_tree(rng)
    if layout_style == "saffron_editorial":
        return _svg_saffron_ink(motif)
    if layout_style == "cartoon_metaphor":
        return _svg_cartoon_metaphor(motif)
    if layout_style == "pastel_viral":
        return _svg_pastel_viral(motif, accent)
    if layout_style == "vibrant_magazine":
        return _svg_vibrant_magazine(motif, accent)
    if layout_style == "gold_spotlight":
        return _svg_gold_spotlight(motif, rng)
    return _svg_monochrome_alpha(motif, accent, rng)


def _svg_pastel_viral(motif: str, accent: str) -> str:
    """Bright pastel daylight 2026 vector metaphor artwork for viral card insets."""
    fill_hi = accent or "#2563EB"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <linearGradient id="pastelSky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#e0f2fe"/>
      <stop offset="55%" stop-color="#fef9c3"/>
      <stop offset="100%" stop-color="#ffedd5"/>
    </linearGradient>
    <radialGradient id="sunnyOrb" cx="78%" cy="28%" r="26%">
      <stop offset="0%" stop-color="#fde047" stop-opacity="0.95"/>
      <stop offset="60%" stop-color="#fb923c" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#fb923c" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#pastelSky)"/>
  <rect width="1080" height="1350" fill="url(#sunnyOrb)"/>
  <!-- Floating clouds -->
  <ellipse cx="220" cy="240" rx="140" ry="52" fill="#ffffff" opacity="0.88"/>
  <ellipse cx="310" cy="220" rx="95" ry="44" fill="#ffffff" opacity="0.92"/>
  <ellipse cx="830" cy="360" rx="125" ry="42" fill="#ffffff" opacity="0.82"/>
  <!-- Vibrant pastel hills & stepping stones rising upward -->
  <path d="M0,1080 Q280,930 580,1030 T1080,960 L1080,1350 L0,1350 Z" fill="#fed7aa"/>
  <path d="M0,1150 Q380,1030 720,1140 T1080,1090 L1080,1350 L0,1350 Z" fill="#bae6fd"/>
  <!-- Ascending stairs & glowing star peak -->
  <g stroke="#0f172a" stroke-width="5" stroke-linejoin="round">
    <rect x="260" y="980" width="120" height="190" rx="12" fill="#ffffff"/>
    <rect x="410" y="860" width="120" height="310" rx="12" fill="#ffffff"/>
    <rect x="560" y="740" width="120" height="430" rx="12" fill="#ffffff"/>
    <rect x="710" y="610" width="120" height="560" rx="12" fill="{fill_hi}"/>
  </g>
  <!-- Confident minimalist character at top step -->
  <g transform="translate(770,540)" fill="#0f172a">
    <circle cx="0" cy="-35" r="24"/>
    <path d="M-24,0 L24,0 L32,68 L-32,68 Z" rx="8"/>
  </g>
</svg>"""


def _svg_vibrant_magazine(motif: str, accent: str) -> str:
    """Luminous daylight coral-azure editorial sunburst artwork."""
    hi = accent or "#F97316"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <linearGradient id="magSky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="48%" stop-color="#fed7aa"/>
      <stop offset="82%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
    <radialGradient id="sunBloom" cx="50%" cy="38%" r="42%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="40%" stop-color="#fde047" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#fb923c" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#magSky)"/>
  <rect width="1080" height="980" fill="url(#sunBloom)"/>
  <!-- Bright scenic layered peaks -->
  <path d="M0,780 L250,480 L470,690 L740,420 L1080,760 L1080,1000 L0,1000 Z" fill="#0284c7" opacity="0.72"/>
  <path d="M0,840 L310,600 L560,760 L820,560 L1080,820 L1080,1020 L0,1020 Z" fill="#0f172a" opacity="0.88"/>
  <!-- Vibrant warm beacon glow at summit -->
  <circle cx="740" cy="400" r="22" fill="{hi}"/>
  <circle cx="740" cy="400" r="46" fill="{hi}" opacity="0.28"/>
</svg>"""


def _svg_paper_sketch(motif: str) -> str:
    """Charcoal/ink metaphorical sketch artwork for textured cream sketchbook cards."""
    if motif == "cliff_birds":
        scene = """
  <g stroke="#1c1917" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <!-- Dramatic rocky cliff on right -->
    <path d="M510,590 L1080,585 L1080,1260 L615,1260 L600,1120 L575,980 L555,840 L525,710 Z" fill="#d6d0c4" stroke-width="4"/>
    <path d="M525,710 L690,715 M555,840 L740,860 M575,980 L760,1010 M615,720 L605,1160 M680,730 L695,1190 M780,690 L820,1210" stroke="#44403c" stroke-width="2.5" opacity="0.65"/>
    <path d="M540,600 L640,650 M650,595 L790,645 M820,592 L950,655" stroke="#292524" stroke-width="2"/>
    <!-- Crumbling pebbles falling -->
    <circle cx="485" cy="790" r="6" fill="#292524"/>
    <circle cx="468" cy="875" r="8" fill="#44403c"/>
    <circle cx="495" cy="955" r="5" fill="#292524"/>
    <circle cx="472" cy="1040" r="7" fill="#57534e"/>
    <!-- 4 passive perched birds on cliff -->
    <g transform="translate(650,540)" fill="#292524">
      <ellipse cx="0" cy="0" rx="28" ry="18"/>
      <circle cx="-22" cy="-16" r="13"/>
      <polygon points="-34,-18 -46,-13 -34,-10" fill="#1c1917"/>
      <path d="M24,6 L58,24 L20,12 Z"/>
      <line x1="-8" y1="16" x2="-12" y2="48" stroke="#1c1917" stroke-width="3"/>
      <line x1="8" y1="16" x2="10" y2="48" stroke="#1c1917" stroke-width="3"/>
    </g>
    <g transform="translate(745,515) scale(1.08)" fill="#1c1917">
      <ellipse cx="0" cy="0" rx="28" ry="18"/>
      <circle cx="-22" cy="-16" r="13"/>
      <polygon points="-34,-18 -46,-13 -34,-10"/>
      <path d="M24,6 L58,24 L20,12 Z"/>
      <line x1="-8" y1="16" x2="-12" y2="66" stroke="#1c1917" stroke-width="3"/>
      <line x1="8" y1="16" x2="10" y2="66" stroke="#1c1917" stroke-width="3"/>
    </g>
    <g transform="translate(835,535) scale(0.96)" fill="#292524">
      <ellipse cx="0" cy="0" rx="28" ry="18"/>
      <circle cx="-22" cy="-16" r="13"/>
      <polygon points="-34,-18 -46,-13 -34,-10"/>
      <path d="M24,6 L58,24 L20,12 Z"/>
      <line x1="-8" y1="16" x2="-10" y2="52" stroke="#1c1917" stroke-width="3"/>
    </g>
    <g transform="translate(935,510) scale(1.1)" fill="#1c1917">
      <ellipse cx="0" cy="0" rx="28" ry="18"/>
      <circle cx="-22" cy="-16" r="13"/>
      <polygon points="-34,-18 -46,-13 -34,-10"/>
      <path d="M24,6 L58,24 L20,12 Z"/>
      <line x1="-8" y1="16" x2="-10" y2="70" stroke="#1c1917" stroke-width="3"/>
    </g>
    <!-- Crimson freedom brushstroke swoosh -->
    <path d="M510,730 C390,785 260,790 130,680 C180,750 280,825 495,745 Z" fill="#dc2626" stroke="none" opacity="0.88"/>
    <!-- Bold soaring bird breaking away -->
    <g transform="translate(245,710) rotate(-14)" fill="#1c1917">
      <path d="M-30,0 C10,-18 55,-16 95,0 C55,22 10,20 -30,0 Z"/>
      <circle cx="-38" cy="-4" r="15"/>
      <polygon points="-51,-6 -70,-1 -51,4"/>
      <path d="M0,-8 C15,-95 65,-145 125,-165 C95,-105 70,-50 48,-4 Z" fill="#292524"/>
      <path d="M12,-6 C35,-65 75,-105 135,-118 C100,-70 68,-30 40,2 Z" fill="#1c1917"/>
      <path d="M75,4 L132,32 L78,16 Z"/>
    </g>
  </g>"""
    elif motif == "mountain_mask":
        scene = """
  <g stroke="#1c1917" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <!-- Mountain stairs & sunlit crown peak -->
    <path d="M620,1220 L810,630 L885,560 L965,640 L1080,1220 Z" fill="#d6d0c4" stroke-width="3.5"/>
    <path d="M735,1215 L775,1120 L750,1040 L805,940 L795,860 L850,765 L845,695 L885,635" stroke="#292524" stroke-width="5"/>
    <!-- Glowing crown above peak -->
    <g transform="translate(885,515)" fill="#dc2626" stroke="#1c1917" stroke-width="3">
      <polygon points="-36,20 -44,-18 -16,2 0,-26 16,2 44,-18 36,20"/>
      <line x1="0" y1="-48" x2="0" y2="-66" stroke="#dc2626" stroke-width="3"/>
      <line x1="-46" y1="-34" x2="-60" y2="-46" stroke="#dc2626" stroke-width="3"/>
      <line x1="46" y1="-34" x2="60" y2="-46" stroke="#dc2626" stroke-width="3"/>
    </g>
    <!-- Determined figure walking forward -->
    <g transform="translate(560,820)">
      <path d="M-45,420 L-35,130 C-30,75 20,55 68,75 L105,155 L85,420 Z" fill="#292524" stroke-width="4"/>
      <circle cx="35" cy="18" r="46" fill="#e7e2d8" stroke-width="4"/>
      <path d="M-8,12 C5,-35 72,-40 84,8 C65,-8 25,-8 -8,12 Z" fill="#1c1917"/>
      <path d="M60,18 L76,22" stroke-width="3"/>
    </g>
    <!-- Shed stone mask breaking behind -->
    <g transform="translate(420,910) rotate(-18)">
      <path d="M-55,-65 L55,-55 L42,68 L-10,88 L-52,50 Z" fill="#a8a29e" stroke-width="3.5"/>
      <path d="M-25,-22 L-6,-18 M15,-20 L34,-16 M-15,28 L16,32" stroke="#1c1917" stroke-width="3"/>
      <polygon points="-75,18 -62,10 -68,30" fill="#57534e" stroke="none"/>
      <polygon points="-90,62 -76,55 -82,76" fill="#78716c" stroke="none"/>
    </g>
  </g>"""
    else:
        # chained_mind: ball & chain attached to headband
        scene = """
  <g stroke="#1c1917" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <!-- Ground shadow -->
    <ellipse cx="520" cy="1205" rx="370" ry="26" fill="#b8b1a4" stroke="none" opacity="0.7"/>
    <!-- Heavy crosshatched iron ball -->
    <circle cx="290" cy="1075" r="125" fill="#78716c" stroke-width="4.5"/>
    <path d="M210,1010 C250,975 330,975 375,1025 M185,1075 C240,1045 340,1045 398,1085 M215,1140 C260,1115 335,1120 365,1155" stroke="#292524" stroke-width="2.5" opacity="0.65"/>
    <circle cx="250" cy="1025" r="34" fill="#d6d3d1" stroke="none" opacity="0.45"/>
    <!-- Heavy chain links -->
    <g stroke="#1c1917" stroke-width="7" fill="none">
      <ellipse cx="425" cy="985" rx="26" ry="13" transform="rotate(-32 425 985)"/>
      <ellipse cx="470" cy="952" rx="26" ry="13" transform="rotate(-32 470 952)"/>
      <ellipse cx="515" cy="918" rx="26" ry="13" transform="rotate(-32 515 918)"/>
      <ellipse cx="560" cy="884" rx="26" ry="13" transform="rotate(-32 560 884)"/>
      <ellipse cx="605" cy="850" rx="26" ry="13" transform="rotate(-32 605 850)"/>
      <ellipse cx="650" cy="816" rx="26" ry="13" transform="rotate(-32 650 816)"/>
    </g>
    <!-- Running figure weighed down by stone collar on head -->
    <g transform="translate(745,795)">
      <!-- Legs -->
      <path d="M-25,225 L-90,340 L-125,365 L-85,385 L-45,355 L15,245" fill="#44403c" stroke-width="4"/>
      <path d="M25,225 L75,335 L55,395 L105,398 L120,330 L65,220" fill="#292524" stroke-width="4"/>
      <!-- Torso & arms straining forward -->
      <path d="M-45,85 L45,75 L65,230 L-35,235 Z" fill="#d6d0c4" stroke-width="4"/>
      <path d="M40,95 L110,165 L95,185 L35,140" fill="#e7e2d8" stroke-width="4"/>
      <!-- Head + stone band -->
      <circle cx="15" cy="25" r="52" fill="#e7e2d8" stroke-width="4"/>
      <rect x="-46" y="-22" width="122" height="44" rx="10" fill="#78716c" stroke-width="4.5"/>
      <path d="M-25,-12 L-18,14 M10,-12 L16,14 M45,-12 L52,14" stroke="#292524" stroke-width="2.5"/>
      <!-- Crimson emphasis mark on shackles -->
      <circle cx="-54" cy="2" r="10" fill="#dc2626" stroke="#1c1917" stroke-width="2.5"/>
    </g>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <filter id="paper" x="0%" y="0%" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" result="noise"/>
      <feColorMatrix type="matrix" values="0 0 0 0 0.72  0 0 0 0 0.68  0 0 0 0 0.60  0 0 0 0.12 0"/>
    </filter>
    <radialGradient id="vign" cx="50%" cy="48%" r="72%">
      <stop offset="62%" stop-color="#f3efe6" stop-opacity="0"/>
      <stop offset="100%" stop-color="#cbc3b4" stop-opacity="0.72"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="#eeeae0"/>
  <rect width="1080" height="1350" filter="url(#paper)"/>
  <rect width="1080" height="1350" fill="url(#vign)"/>
  {scene}
</svg>"""


def _svg_sunrise_crimson_tree(rng: random.Random) -> str:
    """Golden-hour horizon with vibrant crimson-leaved tree, lone walker, and mirror water."""
    birds = []
    for bx, by in [(660, 560), (705, 540), (745, 575), (780, 535), (815, 565)]:
        birds.append(f'<path d="M{bx},{by} Q{bx+10},{by-12} {bx+20},{by} Q{bx+30},{by-12} {bx+40},{by}" fill="none" stroke="#1f2937" stroke-width="2.5"/>')
    birds_svg = "\n  ".join(birds)

    blossoms = []
    for _ in range(55):
        cx = rng.randint(315, 625)
        cy = rng.randint(680, 885)
        r = rng.randint(16, 42)
        col = rng.choice(["#dc2626", "#b91c1c", "#ef4444", "#991b1b"])
        blossoms.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}" opacity="0.88"/>')
    blossom_svg = "\n    ".join(blossoms)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="35%" stop-color="#fef3c7"/>
      <stop offset="68%" stop-color="#fdba74"/>
      <stop offset="80%" stop-color="#fb923c"/>
      <stop offset="100%" stop-color="#e5a97c"/>
    </linearGradient>
    <radialGradient id="sun" cx="76%" cy="77%" r="28%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="1"/>
      <stop offset="28%" stop-color="#fef08a" stop-opacity="0.95"/>
      <stop offset="65%" stop-color="#fb923c" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#fb923c" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.55"/>
      <stop offset="45%" stop-color="#cbd5e1" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#64748b" stop-opacity="0.95"/>
    </linearGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#sky)"/>
  <rect width="1080" height="1100" fill="url(#sun)"/>
  <!-- Distant soft mountains -->
  <path d="M0,1040 L180,965 L390,1020 L620,970 L890,1025 L1080,980 L1080,1060 L0,1060 Z" fill="#d97706" opacity="0.22"/>
  <!-- Mirror water surface -->
  <rect x="0" y="1055" width="1080" height="295" fill="url(#water)"/>
  <!-- Sun reflection column -->
  <ellipse cx="820" cy="1190" rx="85" ry="130" fill="#fef08a" opacity="0.52"/>
  <!-- Shore peninsula -->
  <path d="M0,1045 C260,1035 550,1042 785,1062 C640,1085 260,1085 0,1078 Z" fill="#27272a"/>
  <!-- Crimson tree trunk & branches -->
  <path d="M452,1055 L465,880 L430,815 M465,880 L505,810 M468,940 L420,860 M468,925 L525,855" stroke="#1c1917" stroke-width="14" stroke-linecap="round" fill="none"/>
  <g>
    {blossom_svg}
  </g>
  <!-- Water reflection of crimson tree & walker -->
  <g opacity="0.32" transform="translate(0, 2110) scale(1, -1)">
    <path d="M452,1055 L465,880" stroke="#1c1917" stroke-width="14"/>
    <ellipse cx="470" cy="810" rx="140" ry="95" fill="#dc2626"/>
    <rect x="698" y="965" width="14" height="82" fill="#18181b"/>
  </g>
  <!-- Solitary figure walking toward sunrise -->
  <g transform="translate(705,1048)" fill="#18181b">
    <circle cx="0" cy="-76" r="11"/>
    <path d="M-11,-62 L11,-62 L14,-25 L6,0 L-10,0 L-14,-28 Z"/>
  </g>
  {birds_svg}
</svg>"""


def _svg_saffron_ink(motif: str) -> str:
    """Vibrant warm amber-saffron editorial ink illustration."""
    if motif == "samurai":
        ink_art = """
  <g transform="translate(540,940)" stroke="#111111" stroke-linecap="round" stroke-linejoin="round">
    <path d="M-185,410 L-135,110 L-65,25 L-72,-95 L0,-185 L72,-95 L65,25 L135,110 L185,410 Z" fill="url(#hatch)" stroke-width="5"/>
    <path d="M-210,-50 L210,-165" stroke="#111111" stroke-width="10"/>
    <path d="M-80,-85 Q0,-125 80,-85" fill="#111111"/>
    <path d="M-40,-45 L-12,-38 M40,-45 L12,-38" stroke="#fbbf24" stroke-width="5"/>
  </g>"""
    else:
        # Sharp suited thinker / strategist portrait (Art by Naveen style)
        ink_art = """
  <g transform="translate(540,930)" stroke="#111111" stroke-linecap="round" stroke-linejoin="round">
    <!-- Suit shoulders & lapels -->
    <path d="M-255,420 L-220,175 C-190,115 -105,90 -48,80 L0,210 L48,80 C105,90 190,115 220,175 L255,420 Z" fill="url(#hatch)" stroke-width="5"/>
    <!-- White crisp shirt triangle + black bow tie -->
    <polygon points="-55,88 55,88 0,245" fill="#fde68a" stroke="#111111" stroke-width="4"/>
    <polygon points="-36,102 0,118 -36,134" fill="#111111"/>
    <polygon points="36,102 0,118 36,134" fill="#111111"/>
    <circle cx="0" cy="118" r="9" fill="#111111"/>
    <!-- Neck & portrait head -->
    <rect x="-42" y="20" width="84" height="78" fill="#f59e0b" stroke="#111111" stroke-width="4"/>
    <path d="M-92,-65 C-92,-175 92,-175 92,-65 C92,25 48,72 0,72 C-48,72 -92,25 -92,-65 Z" fill="#fbbf24" stroke="#111111" stroke-width="5"/>
    <!-- Hair & crosshatched shadow -->
    <path d="M-96,-72 C-98,-178 96,-195 98,-72 C68,-122 -58,-122 -96,-72 Z" fill="url(#hatch)" stroke-width="4"/>
    <!-- Sharp calm eyes & brows -->
    <path d="M-56,-56 L-18,-52 M18,-52 L56,-56" stroke-width="6"/>
    <ellipse cx="-36" cy="-38" rx="11" ry="6" fill="#111111"/>
    <ellipse cx="36" cy="-38" rx="11" ry="6" fill="#111111"/>
    <path d="M-12,5 L0,12 L12,5 M-24,34 Q0,40 24,34" stroke-width="4" fill="none"/>
    <!-- Hand raised pointing thoughtfully to temple -->
    <path d="M135,280 L115,65 L95,-35 L122,-40 L145,45 L175,90 L165,280 Z" fill="#fbbf24" stroke="#111111" stroke-width="5"/>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <radialGradient id="saffron" cx="50%" cy="46%" r="65%">
      <stop offset="0%" stop-color="#fbbf24"/>
      <stop offset="60%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#d97706"/>
    </radialGradient>
    <pattern id="hatch" width="12" height="12" patternTransform="rotate(42 0 0)" patternUnits="userSpaceOnUse">
      <rect width="12" height="12" fill="#27272a"/>
      <line x1="0" y1="0" x2="0" y2="12" stroke="#111111" stroke-width="5"/>
    </pattern>
  </defs>
  <rect width="1080" height="1350" fill="url(#saffron)"/>
  {ink_art}
</svg>"""


def _svg_cartoon_metaphor(motif: str) -> str:
    """9:16 Makoto Shinkai-style atmospheric sunset valley & luminous rays fallback art."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">
  <defs>
    <linearGradient id="shinkaiSky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0284c7"/>
      <stop offset="35%" stop-color="#38bdf8"/>
      <stop offset="68%" stop-color="#fed7aa"/>
      <stop offset="100%" stop-color="#f97316"/>
    </linearGradient>
    <radialGradient id="sunsetOrb" cx="50%" cy="54%" r="36%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="32%" stop-color="#fef08a" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#fb923c" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1920" fill="url(#shinkaiSky)"/>
  <rect width="1080" height="1450" fill="url(#sunsetOrb)"/>
  <ellipse cx="220" cy="420" rx="210" ry="48" fill="#ffffff" opacity="0.32"/>
  <ellipse cx="810" cy="340" rx="240" ry="52" fill="#ffffff" opacity="0.28"/>
  <path d="M0,1240 L260,960 L540,1160 L820,910 L1080,1190 L1080,1920 L0,1920 Z" fill="#1e293b" opacity="0.72"/>
  <path d="M0,1360 L340,1120 L620,1290 L920,1080 L1080,1260 L1080,1920 L0,1920 Z" fill="#0f172a"/>
  <g transform="translate(540,1090)" fill="#ffffff" opacity="0.9">
    <circle cx="0" cy="-42" r="14"/>
    <path d="M-16,-24 L16,-24 L20,38 L-20,38 Z"/>
  </g>
</svg>"""


def _svg_gold_spotlight(motif: str, rng: random.Random) -> str:
    """Cinematic dark-and-gold split/editorial spotlight artwork."""
    stars = "\n  ".join(
        f'<circle cx="{rng.randint(40,1040)}" cy="{rng.randint(40,860)}" r="{rng.uniform(1.2,3.4):.1f}" fill="#facc15" opacity="{rng.uniform(0.25,0.75):.2f}"/>'
        for _ in range(36)
    )
    if motif == "mentor_split":
        figure = """
  <!-- Dramatic left-side mentor portrait silhouette under warm rim light -->
  <defs>
    <radialGradient id="splitGlow" cx="26%" cy="42%" r="48%">
      <stop offset="0%" stop-color="#facc15" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="#78350f" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#050507" stop-opacity="1"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#splitGlow)"/>
  <g transform="translate(275,780)">
    <path d="M-240,570 L-205,170 C-170,85 -75,55 0,55 C85,55 180,95 210,185 L230,570 Z" fill="#0d0d11" stroke="#facc15" stroke-opacity="0.45" stroke-width="3"/>
    <circle cx="0" cy="-95" r="115" fill="#0d0d11" stroke="#facc15" stroke-opacity="0.55" stroke-width="3"/>
    <path d="M-65,-195 C-25,-235 65,-225 102,-155" stroke="#facc15" stroke-width="4" fill="none" opacity="0.65"/>
  </g>"""
    else:
        figure = """
  <!-- Dramatic night city / warrior rim-light scene -->
  <defs>
    <radialGradient id="goldAura" cx="50%" cy="32%" r="54%">
      <stop offset="0%" stop-color="#facc15" stop-opacity="0.55"/>
      <stop offset="48%" stop-color="#78350f" stop-opacity="0.32"/>
      <stop offset="100%" stop-color="#050507" stop-opacity="1"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#goldAura)"/>
  <g transform="translate(0,95)">
    <polygon points="80,680 80,310 175,310 175,680" fill="#0b0b0f" stroke="#facc15" stroke-opacity="0.35"/>
    <polygon points="200,680 200,200 320,200 320,680" fill="#08080c" stroke="#facc15" stroke-opacity="0.48"/>
    <polygon points="355,680 355,140 485,140 485,680" fill="#07070b" stroke="#facc15" stroke-opacity="0.55"/>
    <polygon points="600,680 600,120 735,120 735,680" fill="#07070b" stroke="#facc15" stroke-opacity="0.55"/>
    <polygon points="765,680 765,220 885,220 885,680" fill="#09090d" stroke="#facc15" stroke-opacity="0.45"/>
    <polygon points="910,680 910,300 995,300 995,680" fill="#0b0b0f" stroke="#facc15" stroke-opacity="0.35"/>
    <!-- Standing focal warrior/executive silhouette -->
    <path d="M465,680 L495,345 L540,295 L585,345 L615,680 Z" fill="#050507" stroke="#facc15" stroke-width="3"/>
    <circle cx="540" cy="255" r="36" fill="#050507" stroke="#facc15" stroke-width="3"/>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <rect width="1080" height="1350" fill="#050507"/>
  {figure}
  {stars}
</svg>"""


def _svg_monochrome_alpha(motif: str, accent: str, rng: random.Random) -> str:
    """Full-bleed high-contrast silver-monochrome storm wildlife / alpha poster."""
    mist = "\n  ".join(
        f'<ellipse cx="{rng.randint(150,930)}" cy="{rng.randint(250,1150)}" rx="{rng.randint(220,420)}" ry="{rng.randint(55,120)}" fill="#d4d4d8" opacity="{rng.uniform(0.05,0.14):.2f}"/>'
        for _ in range(10)
    )
    if motif == "wolf":
        subject = f"""
  <!-- Misty forest trees + wolf pack silhouettes -->
  <g fill="#09090b">
    <polygon points="90,1220 120,260 150,1220"/>
    <polygon points="210,1220 245,190 280,1220"/>
    <polygon points="810,1220 845,210 880,1220"/>
    <polygon points="940,1220 970,290 1000,1220"/>
  </g>
  <g transform="translate(540,610)" fill="#18181b" stroke="#e4e4e7" stroke-width="2.5">
    <polygon points="0,-275 105,-155 215,-245 190,-55 270,55 175,205 0,310 -175,205 -270,55 -190,-55 -215,-245 -105,-155"/>
    <polygon points="-110,-35 -35,-18 -65,12" fill="{accent}" stroke="none"/>
    <polygon points="110,-35 35,-18 65,12" fill="{accent}" stroke="none"/>
  </g>"""
    else:
        # Full-bleed scarred silver-monochrome lion / panther
        subject = f"""
  <g transform="translate(540,590)" fill="#18181b" stroke="#f4f4f5" stroke-opacity="0.45" stroke-width="2">
    <path d="M0,-380 C165,-380 315,-265 345,-95 C375,85 280,265 180,350 L0,430 L-180,350 C-280,265 -375,85 -345,-95 C-315,-265 -165,-380 0,-380 Z" fill="url(#mane)"/>
    <ellipse cx="0" cy="-20" rx="195" ry="225" fill="#27272a" stroke="#e4e4e7" stroke-opacity="0.5"/>
    <polygon points="-115,-70 -35,-48 -70,-24" fill="#fafafa" stroke="none"/>
    <polygon points="115,-70 35,-48 70,-24" fill="{accent}" stroke="none"/>
    <path d="M55,-165 L95,-95 L68,-10 L102,65" stroke="{accent}" stroke-width="6" fill="none" opacity="0.85"/>
    <polygon points="0,42 -42,88 42,88" fill="#09090b" stroke="#a1a1aa"/>
    <path d="M-75,138 Q0,175 75,138" stroke="#d4d4d8" stroke-width="5" fill="none"/>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <radialGradient id="storm" cx="50%" cy="38%" r="65%">
      <stop offset="0%" stop-color="#52525b"/>
      <stop offset="55%" stop-color="#18181b"/>
      <stop offset="100%" stop-color="#040406"/>
    </radialGradient>
    <radialGradient id="mane" cx="50%" cy="42%" r="55%">
      <stop offset="0%" stop-color="#3f3f46"/>
      <stop offset="70%" stop-color="#18181b"/>
      <stop offset="100%" stop-color="#09090b"/>
    </radialGradient>
  </defs>
  <rect width="1080" height="1350" fill="url(#storm)"/>
  {subject}
  {mist}
</svg>"""


def resolve_artwork_data_uri(
    config: AppConfig,
    theme_meta: dict[str, Any],
    seed: int,
    allow_remote_art: bool = True,
    cache_path: Path | None = None,
    prompt_override: str = "",
    fast_tier: bool = False,
) -> tuple[str, str]:
    """Return (data_uri, source_label) for the visual artwork of a card."""
    prompt = prompt_override.strip() or str(theme_meta.get("ai_prompt", "Dark dramatic lion portrait, high contrast, no text"))
    accent = str(theme_meta.get("accent", "#FF3B30"))
    motif = str(theme_meta.get("svg_motif", "lion"))
    layout_style = str(theme_meta.get("layout_style", "monochrome_alpha"))

    if allow_remote_art:
        image_bytes = (
            _try_cloudflare_flux(prompt, config.cloudflare_account_id, config.cloudflare_api_token, fast_tier=fast_tier)
            or _try_deepai(prompt, config.deepai_api_key)
            or _try_gemini_imagen(prompt, config.gemini_api_key)
            or _try_huggingface(prompt, config.hf_token)
            or _try_openai_image(prompt, config.openai_api_key)
            or _try_pollinations(prompt, config.pollinations_api_key, seed)
            or _try_composio_fal(prompt, config)
        )
        if image_bytes:
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(image_bytes)
            mime = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/jpeg"
            b64 = base64.b64encode(image_bytes).decode("ascii")
            return f"data:{mime};base64,{b64}", "ai_image"

    svg_markup = build_illustrated_svg(layout_style, motif, accent, seed)
    b64_svg = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64_svg}", f"illustrated_{layout_style}"
