"""Content intelligence engine modeled after top 50 dark-motivation archetypes."""

from __future__ import annotations

import hashlib
import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ARCHETYPES_PATH, AppConfig, HISTORY_PATH, QUOTE_VAULT_PATH


@dataclass(frozen=True)
class SlideContent:
    """One visual card inside a single-image or carousel post."""

    quote: str
    accent: str
    badge: str = ""
    visual_theme: str = "dark_lion"
    image_prompt: str = ""


@dataclass(frozen=True)
class PostPlan:
    """Complete generated post payload ready for rendering and publishing."""

    slot: int
    archetype_id: int
    archetype_name: str
    post_type: str  # "single" or "carousel"
    caption: str
    slides: list[SlideContent] = field(default_factory=list)
    content_hash: str = ""
    source: str = "vault"


SLOT_PREFERENCES: dict[int, dict[str, Any]] = {
    1: {
        "post_type": "single",
        "tones": {"life_lessons", "self_respect", "comeback", "ambition"},
    },
    2: {
        "post_type": "carousel",
        "tones": {"rules_series", "life_lessons", "stoicism"},
    },
    3: {
        "post_type": "single",
        "tones": {"silent_power", "loyalty", "growth", "discipline"},
    },
    4: {
        "post_type": "single",
        "tones": {"savage_attitude", "cold_truth", "antihero_noir", "solitude", "resilience"},
    },
    5: {
        "post_type": "carousel",
        "tones": {"life_lessons", "rules_series", "growth", "self_respect"},
    },
}


def compute_hash(text: str) -> str:
    """Return a stable short SHA-256 fingerprint for deduplication."""
    normalized = " ".join(text.upper().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path, default: Any) -> Any:
    """Load JSON safely from disk, returning default if missing."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_history(history_path: Path = HISTORY_PATH) -> dict[str, Any]:
    """Load posted history tracking file."""
    return load_json(history_path, {"hashes": [], "posts": []})


def save_history(
    plan: PostPlan,
    post_result: dict[str, Any] | None = None,
    history_path: Path = HISTORY_PATH,
    max_items: int = 4000,
) -> None:
    """Persist a newly published post hash and summary to state history."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = load_history(history_path)
    hashes: list[str] = list(history.get("hashes", []))
    posts: list[dict[str, Any]] = list(history.get("posts", []))

    if plan.content_hash and plan.content_hash not in hashes:
        hashes.append(plan.content_hash)

    posts.append(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "slot": plan.slot,
            "archetype_id": plan.archetype_id,
            "archetype_name": plan.archetype_name,
            "post_type": plan.post_type,
            "source": plan.source,
            "content_hash": plan.content_hash,
            "headline": plan.slides[0].quote[:100] if plan.slides else "",
            "remote_result": post_result or {},
        }
    )

    history["hashes"] = hashes[-max_items:]
    history["posts"] = posts[-max_items:]
    with history_path.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)


def _pick_archetype(archetypes: list[dict[str, Any]], slot: int, rng: random.Random) -> dict[str, Any]:
    """Select an archetype aligned with the daily slot."""
    preferred_tones = SLOT_PREFERENCES.get(slot, {}).get("tones", set())
    candidates = [item for item in archetypes if item.get("tone") in preferred_tones]
    pool = candidates or archetypes
    return rng.choice(pool)


def _format_caption(
    vault: dict[str, Any],
    archetype: dict[str, Any],
    brand_name: str,
    raw_caption: str,
    lead: str,
    rng: random.Random,
) -> str:
    """Assemble an attitudeproblem7-style caption with spacer dots and hashtags."""
    style = archetype.get("caption_style", "savage_oneliner")
    templates = vault.get("cta_templates", {}).get(style) or ["{caption}\n. . . . . .\n{hashtags}"]
    template = rng.choice(templates)
    hashtags = " ".join(archetype.get("hashtags", ["#mindset", "#motivation", "#attitude"]))
    return template.format(
        brand=brand_name,
        caption=raw_caption.strip(),
        lead=lead.strip(),
        hashtags=hashtags,
    )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 20) -> dict[str, Any]:
    """Perform a minimal JSON HTTP POST using stdlib urllib."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_STYLE_HINTS: dict[str, str] = {
    "paper_sketch": "clean crisp black ink & charcoal pencil metaphor drawing isolated on pure solid blank white #FFFFFF paper background, zero dark/gray background shading, no text",
    "saffron_editorial": "minimalist crisp black crosshatched ink illustration isolated on pure solid blank white #FFFFFF paper background, lower-weighted composition, no dark edges, no text",
    "cartoon_metaphor": "bright sunny modern 2D flat vector comic metaphor illustration on crisp daylight sky blue/pastel background, joyful high-contrast colors, no text",
    "sunrise_metaphor": "radiant golden morning sunrise horizon landscape with luminous pastel sky upper half and vivid coral/emerald foreground contrast, no text",
    "pastel_viral": "bright trendy 2026 pastel 3D/vector daylight illustration with sky blue, warm peach, butter yellow, and vibrant coral accents, clean uplifting composition, no text",
    "vibrant_magazine": "bright golden-hour daylight editorial photograph-style scene with luminous turquoise, warm amber, and sunny sky tones, no dark gloomy black shadows, no text",
    "gold_spotlight": "bright golden-hour studio rim-lit portrait on warm sapphire/amber backdrop, high clarity, no text",
    "monochrome_alpha": "clean silver-gelatin editorial portrait with bright luminous highlights, no text",
}


def _generate_via_llm(
    config: AppConfig,
    archetype: dict[str, Any],
    post_type: str,
    used_hashes: set[str],
    visual_themes: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Attempt fresh high-CTR quote and visual prompt generation using Gemini or OpenAI."""
    slide_count = 4 if post_type == "carousel" else 1
    theme_map = visual_themes or {}
    if theme_map:
        theme_guide = "; ".join(
            f"{k} ({_STYLE_HINTS.get(str(v.get('layout_style', '')), str(v.get('label', '')))})"
            for k, v in theme_map.items()
        )
    else:
        theme_guide = "bright_pastel_path, vibrant_sunrise_pop, sunny_sky_growth, dark_eagle, dark_anime_moody, dark_anime_rain, noir_suit, dark_anime_warm"

    prompt = (
        f"Create an original viral high-CTR bright modern Facebook {post_type} post.\n"
        f"Theme: {archetype['name']} (tone: {archetype['tone']}).\n"
        f"Rules:\n"
        f"- Output strict JSON only, no markdown fences.\n"
        f"- Return object with keys: caption (1 crisp engaging sentence), lead (short phrase after 'Follow for '), "
        f"slides (array of {slide_count} objects with keys: quote, accent, badge, visual_theme, image_prompt).\n"
        f"- Each quote must be UPPERCASE, punchy, 8 to 20 words, strong self-respect/mindset/discipline hook.\n"
        f"- 'accent' MUST be an exact uppercase substring of 'quote' (2 to 5 impactful words to color highlight).\n"
        f"- 'visual_theme' MUST be one of the theme keys listed below.\n"
        f"- BRIGHT & TRENDY VISUAL RULE: Every visual MUST feel bright, eye-catching, modern, and vibrant (sunlit daylight, pastel sky, cream paper ink, warm saffron, or golden sunrise — NEVER dark gloomy pitch-black shadows!).\n"
        f"- 'image_prompt' MUST include a clear concrete visual SUBJECT + symbolic metaphor (e.g. eagle breaking away from perched birds, climber ascending sunlit stairs, suited chess strategist, red sunrise tree, golden lion in daylight, blooming sprout vs dry stone) rendered in the required medium/background style for your chosen visual_theme (never omit the subject; no text, no words, no watermark):\n"
        f"  Themes & required visual medium: {theme_guide}.\n"
        f"- For carousel slides, set badge to '01 / 04', '02 / 04', etc. For single post, badge is empty string.\n"
    )

    raw_text = ""
    try:
        if config.gemini_api_key:
            for model in ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"):
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={config.gemini_api_key}"
                )
                try:
                    resp = _post_json(
                        url,
                        {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
                        },
                        {"Content-Type": "application/json"},
                    )
                    raw_text = resp["candidates"][0]["content"]["parts"][0]["text"]
                    if raw_text:
                        break
                except (urllib.error.URLError, KeyError, IndexError, TimeoutError):
                    continue
        elif config.openai_api_key:
            resp = _post_json(
                "https://api.openai.com/v1/chat/completions",
                {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 1.0,
                },
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.openai_api_key}",
                },
            )
            raw_text = resp["choices"][0]["message"]["content"]
        else:
            return None

        if not raw_text:
            return None
        parsed = json.loads(raw_text)
        slides = parsed.get("slides", [])
        if not slides:
            return None
        fingerprint = compute_hash(" | ".join(s["quote"] for s in slides))
        if fingerprint in used_hashes:
            return None
        parsed["hash"] = fingerprint
        return parsed
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def _pick_from_vault(
    vault: dict[str, Any],
    archetype: dict[str, Any],
    post_type: str,
    used_hashes: set[str],
    brand_name: str,
    rng: random.Random,
) -> tuple[list[SlideContent], str, str, str, str] | None:
    """Pick an unused handcrafted single quote or carousel series from the vault."""
    theme = archetype.get("visual_theme", "dark_lion")

    if post_type == "carousel":
        carousels = list(vault.get("carousel_series", []))
        rng.shuffle(carousels)
        for item in carousels:
            combined = " | ".join(s["quote"] for s in item["slides"])
            h = compute_hash(combined)
            if h not in used_hashes:
                slides = [
                    SlideContent(
                        quote=s["quote"],
                        accent=s.get("accent", ""),
                        badge=s.get("badge", ""),
                        visual_theme=s.get("visual_theme") or item.get("visual_theme", theme),
                    )
                    for s in item["slides"]
                ]
                lead = item.get("series_title", "mindset rules every man should live by").lower()
                caption = item.get("caption_lead", "Follow {brand} for rules to live by.").format(brand=brand_name)
                return slides, caption, lead, h, "vault_carousel"
        return None

    singles = list(vault.get("single_quotes", []))
    tone_matches = [q for q in singles if q.get("tone") == archetype.get("tone")]
    ordered = tone_matches + [q for q in singles if q not in tone_matches]
    for item in ordered:
        h = compute_hash(item["quote"])
        if h not in used_hashes:
            slide = SlideContent(
                quote=item["quote"],
                accent=item.get("accent", ""),
                badge="",
                visual_theme=item.get("preferred_theme", theme),
            )
            return [slide], item.get("caption", ""), item.get("caption", ""), h, "vault_single"
    return None


def _synthesize_combinatorial(
    vault: dict[str, Any],
    archetype: dict[str, Any],
    post_type: str,
    used_hashes: set[str],
    rng: random.Random,
) -> tuple[list[SlideContent], str, str, str, str]:
    """Generate a guaranteed-unique quote or 4-card series from modular components."""
    parts = vault["combinatorial_parts"]
    openers: list[str] = parts["openers"]
    pivots: list[str] = parts["pivots"]
    closers: list[str] = parts["closers"]
    theme = archetype.get("visual_theme", "dark_lion")

    def make_one() -> tuple[str, str]:
        opener = rng.choice(openers)
        pivot = rng.choice(pivots)
        closer = rng.choice(closers)
        full = f"{opener} {pivot} {closer}"
        return full, closer

    if post_type == "carousel":
        for _ in range(50):
            slides: list[SlideContent] = []
            seen_local: set[str] = set()
            for idx in range(1, 5):
                q, accent = make_one()
                while q in seen_local:
                    q, accent = make_one()
                seen_local.add(q)
                slides.append(
                    SlideContent(
                        quote=q,
                        accent=accent,
                        badge=f"RULE #{idx:02d}",
                        visual_theme=theme,
                    )
                )
            h = compute_hash(" | ".join(s.quote for s in slides))
            if h not in used_hashes:
                return (
                    slides,
                    f"{archetype['name']} — save these rules.",
                    "timeless discipline & self-respect rules.",
                    h,
                    "combinatorial_carousel",
                )

    for _ in range(200):
        q, accent = make_one()
        h = compute_hash(q)
        if h not in used_hashes:
            return (
                [SlideContent(quote=q, accent=accent, badge="", visual_theme=theme)],
                "Keep your standards high and your circle honest.",
                "daily attitude & mindset fuel.",
                h,
                "combinatorial_single",
            )

    # Final safety net if all combinations were somehow exhausted after years
    q, accent = make_one()
    salt = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return (
        [SlideContent(quote=q, accent=accent, badge="", visual_theme=theme)],
        "Stay relentless.",
        "daily mindset reminders.",
        compute_hash(f"{q}:{salt}"),
        "combinatorial_fallback",
    )


def build_post_plan(
    config: AppConfig,
    slot: int,
    seed: int | None = None,
    history_path: Path = HISTORY_PATH,
    extra_used_hashes: set[str] | None = None,
    brand_override: str | None = None,
) -> PostPlan:
    """Create a complete, non-repeating post plan for the requested daily slot (1..5)."""
    if slot not in SLOT_PREFERENCES:
        raise ValueError(f"Slot must be between 1 and 5, got {slot}")

    rng = random.Random(seed)
    archetypes_data = load_json(ARCHETYPES_PATH, {"archetypes": []})
    archetypes: list[dict[str, Any]] = archetypes_data["archetypes"]
    vault = load_json(QUOTE_VAULT_PATH, {})
    history = load_history(history_path)
    used_hashes: set[str] = set(history.get("hashes", []))
    if extra_used_hashes:
        used_hashes.update(extra_used_hashes)

    effective_brand = brand_override or config.brand_name
    archetype = _pick_archetype(archetypes, slot, rng)
    post_type = SLOT_PREFERENCES[slot]["post_type"]

    visual_themes = vault.get("visual_themes") or {}
    valid_themes = list(visual_themes.keys())
    llm_data = _generate_via_llm(config, archetype, post_type, used_hashes, visual_themes=visual_themes)
    if llm_data:
        theme = archetype.get("visual_theme", "dark_lion")
        slides = [
            SlideContent(
                quote=str(s["quote"]).upper().strip(),
                accent=str(s.get("accent", "")).upper().strip(),
                badge=str(s.get("badge", "")).upper().strip(),
                visual_theme=s.get("visual_theme") if s.get("visual_theme") in valid_themes else theme,
                image_prompt=str(s.get("image_prompt", "")).strip(),
            )
            for s in llm_data["slides"]
        ]
        raw_caption = str(llm_data.get("caption", "")).strip()
        lead = str(llm_data.get("lead", "daily mindset rules.")).strip()
        content_hash = llm_data["hash"]
        source = "llm_live"
    else:
        picked = _pick_from_vault(vault, archetype, post_type, used_hashes, effective_brand, rng)
        if picked:
            slides, raw_caption, lead, content_hash, source = picked
        else:
            slides, raw_caption, lead, content_hash, source = _synthesize_combinatorial(
                vault, archetype, post_type, used_hashes, rng
            )

    formatted_caption = _format_caption(vault, archetype, effective_brand, raw_caption, lead, rng)

    return PostPlan(
        slot=slot,
        archetype_id=int(archetype["id"]),
        archetype_name=str(archetype["name"]),
        post_type=post_type,
        caption=formatted_caption,
        slides=slides,
        content_hash=content_hash,
        source=source,
    )
