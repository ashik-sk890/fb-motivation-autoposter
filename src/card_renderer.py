"""Modern multi-style HTML/CSS + Playwright/Pillow renderer matching viral Facebook cards."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.art_engine import resolve_artwork_data_uri
from src.config import AppConfig
from src.content_engine import SlideContent


def _highlight_html(text: str, accent_phrase: str, highlight_class: str = "accent") -> str:
    """Escape text safely and wrap any matching accent substring in a styled span."""
    clean_text = text.strip()
    clean_accent = accent_phrase.strip()
    if clean_accent and clean_accent.upper() in clean_text.upper():
        idx = clean_text.upper().index(clean_accent.upper())
        before = html.escape(clean_text[:idx])
        mid = html.escape(clean_text[idx : idx + len(clean_accent)])
        after = html.escape(clean_text[idx + len(clean_accent) :])
        return f'{before}<span class="{highlight_class}">{mid}</span>{after}'
    return html.escape(clean_text)


def _scale_font(text: str, large: int = 58, medium: int = 48, compact: int = 40) -> int:
    """Choose responsive font size based on quote character length."""
    n = len(text.strip())
    if n <= 54:
        return large
    if n <= 92:
        return medium
    return compact


def build_card_html(
    config: AppConfig,
    slide: SlideContent,
    artwork_data_uri: str,
    accent_color: str = "#FF3B30",
    layout_style: str = "monochrome_alpha",
    svg_motif: str = "lion",
    page_brand: str | None = None,
    is_ai_art: bool = False,
) -> str:
    """Render self-contained 1080x1350 HTML tailored to one of 6 modern viral visual styles."""
    brand_label = html.escape(page_brand or config.brand_name)
    handle = html.escape(config.brand_handle)
    monogram = html.escape(config.brand_monogram)
    badge = html.escape(slide.badge)

    if layout_style == "paper_sketch":
        return _tpl_paper_sketch(slide, artwork_data_uri, brand_label, badge, is_ai_art=is_ai_art)
    if layout_style == "sunrise_metaphor":
        return _tpl_sunrise_metaphor(slide, artwork_data_uri, brand_label, badge)
    if layout_style == "saffron_editorial":
        return _tpl_saffron_editorial(slide, artwork_data_uri, brand_label, badge, is_ai_art=is_ai_art)
    if layout_style == "cartoon_metaphor":
        return _tpl_cartoon_metaphor(slide, artwork_data_uri, brand_label, badge)
    if layout_style == "gold_spotlight":
        return _tpl_gold_spotlight(slide, artwork_data_uri, brand_label, monogram, handle, badge, svg_motif)
    return _tpl_monochrome_alpha(slide, artwork_data_uri, accent_color, monogram, handle, badge)


def _tpl_paper_sketch(slide: SlideContent, art_uri: str, brand: str, badge: str, is_ai_art: bool = False) -> str:
    """Textured sketchbook paper + dark handwritten/serif ink + crimson swoosh."""
    quote_txt = slide.quote.strip().title() if len(slide.quote) > 35 else slide.quote.strip()
    q_html = _highlight_html(quote_txt, slide.accent, "red-accent")
    font_px = _scale_font(quote_txt, large=62, medium=52, compact=44)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    art_layer_css = (
        f'.art-inset {{ position: absolute; left: 56px; right: 56px; top: 430px; bottom: 84px; background: url("{art_uri}") center/contain no-repeat; mix-blend-mode: multiply; -webkit-mask-image: radial-gradient(ellipse at center, black 62%, transparent 98%); mask-image: radial-gradient(ellipse at center, black 62%, transparent 98%); }}'
        if is_ai_art
        else f'.card {{ background: #eeeae0 url("{art_uri}") center/cover no-repeat; }}'
    )
    art_div = '<div class="art-inset"></div>' if is_ai_art else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,600;0,700;1,600&family=Patrick+Hand&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; background: #eeeae0; font-family: 'Patrick Hand', 'Lora', Georgia, serif; color: #18181b; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: radial-gradient(circle at 50% 48%, #f3efe6 55%, #d6cfc0 100%); }}
  {art_layer_css}
  .top-text {{ position: absolute; top: 88px; left: 86px; right: 86px; text-align: center; }}
  .pill {{ display: inline-block; margin-bottom: 18px; padding: 6px 22px; border: 2px solid #dc2626; border-radius: 999px; color: #dc2626; font-family: Arial, sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 3px; }}
  .quote {{ font-size: {font_px}px; line-height: 1.28; font-weight: 600; color: #1c1917; letter-spacing: 0.4px; }}
  .red-accent {{ color: #dc2626; text-decoration: underline; text-decoration-color: rgba(220,38,38,0.68); text-underline-offset: 10px; text-decoration-thickness: 4px; }}
  .divider {{ margin: 28px auto 0; width: 280px; height: 18px; display: flex; align-items: center; justify-content: center; gap: 12px; color: #44403c; font-size: 20px; }}
  .line {{ flex: 1; height: 2px; background: #44403c; opacity: 0.55; }}
  .brand {{ position: absolute; bottom: 38px; left: 0; right: 0; text-align: center; font-family: 'Lora', Georgia, serif; font-size: 22px; color: #44403c; letter-spacing: 1px; opacity: 0.78; }}
</style></head><body>
  <div class="card">
    {art_div}
    <div class="top-text">
      {badge_html}
      <div class="quote">{q_html}</div>
      <div class="divider"><span class="line"></span><span>◆</span><span class="line"></span></div>
    </div>
    <div class="brand">{brand}</div>
  </div>
</body></html>"""


def _tpl_sunrise_metaphor(slide: SlideContent, art_uri: str, brand: str, badge: str) -> str:
    """Bright golden sunrise + bold red headline + dark clean truth text over landscape."""
    headline = badge or "HARD TRUTH"
    body_text = slide.quote.strip().capitalize()
    q_html = _highlight_html(body_text, slide.accent, "bold-mark")
    font_px = _scale_font(body_text, large=46, medium=40, compact=35)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; font-family: 'Montserrat', Arial, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: url("{art_uri}") center/cover no-repeat; }}
  .top-box {{ position: absolute; top: 88px; left: 78px; right: 78px; text-align: center; }}
  .headline {{ font-size: 74px; font-weight: 900; color: #dc2626; letter-spacing: 1px; margin-bottom: 26px; text-shadow: 0 2px 12px rgba(255,255,255,0.65); }}
  .quote {{ font-size: {font_px}px; line-height: 1.44; font-weight: 700; color: #18181b; text-shadow: 0 1px 10px rgba(255,255,255,0.75); }}
  .bold-mark {{ color: #991b1b; font-weight: 900; }}
  .brand {{ position: absolute; bottom: 26px; left: 0; right: 0; text-align: center; font-size: 18px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: rgba(255,255,255,0.82); text-shadow: 0 2px 8px rgba(0,0,0,0.8); }}
</style></head><body>
  <div class="card">
    <div class="top-box">
      <div class="headline">{headline}</div>
      <div class="quote">{q_html}</div>
    </div>
    <div class="brand">{brand}</div>
  </div>
</body></html>"""


def _tpl_saffron_editorial(slide: SlideContent, art_uri: str, brand: str, badge: str, is_ai_art: bool = False) -> str:
    """Vibrant warm saffron-orange editorial ink card (Art by Naveen style)."""
    quote_txt = slide.quote.strip().capitalize()
    q_html = _highlight_html(quote_txt, slide.accent, "ink-emphasis")
    font_px = _scale_font(quote_txt, large=62, medium=54, compact=46)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    art_layer_css = (
        f'.art-inset {{ position: absolute; left: 60px; right: 60px; top: 430px; bottom: 40px; background: url("{art_uri}") center bottom/contain no-repeat; mix-blend-mode: multiply; -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 18%, black 100%); mask-image: linear-gradient(to bottom, transparent 0%, black 18%, black 100%); }}'
        if is_ai_art
        else f'.card {{ background: #f59e0b url("{art_uri}") center/cover no-repeat; }}'
    )
    art_div = '<div class="art-inset"></div>' if is_ai_art else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@600;700&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; font-family: 'Lora', Georgia, serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: radial-gradient(circle at 50% 46%, #fbbf24 0%, #f59e0b 60%, #d97706 100%); }}
  {art_layer_css}
  .top-text {{ position: absolute; top: 96px; left: 86px; right: 86px; text-align: center; }}
  .pill {{ display: inline-block; margin-bottom: 16px; padding: 6px 20px; border: 2px solid #111111; border-radius: 999px; font-family: Arial, sans-serif; font-weight: 800; font-size: 19px; letter-spacing: 3px; color: #111111; }}
  .quote {{ font-size: {font_px}px; line-height: 1.26; font-weight: 700; color: #111111; text-shadow: 0 2px 14px rgba(251,191,36,0.55); }}
  .ink-emphasis {{ text-decoration: underline; text-decoration-thickness: 4px; text-underline-offset: 8px; }}
  .sig {{ position: absolute; right: 32px; bottom: 24px; font-style: italic; font-size: 20px; font-weight: 700; color: #111111; background: rgba(251, 191, 36, 0.88); padding: 4px 14px; border-radius: 999px; }}
</style></head><body>
  <div class="card">
    {art_div}
    <div class="top-text">
      {badge_html}
      <div class="quote">{q_html}</div>
    </div>
    <div class="sig">{brand}</div>
  </div>
</body></html>"""


def _tpl_cartoon_metaphor(slide: SlideContent, art_uri: str, brand: str, badge: str) -> str:
    """Clean daylight comic metaphor card (Stick Wisdom 44K reaction pattern)."""
    quote_txt = slide.quote.strip().upper()
    q_html = _highlight_html(quote_txt, slide.accent, "blue-accent")
    font_px = _scale_font(quote_txt, large=48, medium=42, compact=36)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; font-family: 'Montserrat', Arial, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: #e2e8f0 url("{art_uri}") center/cover no-repeat; }}
  .banner {{ position: absolute; top: 56px; left: 60px; right: 60px; background: rgba(255,255,255,0.92); border: 3px solid #0f172a; border-radius: 22px; padding: 30px 36px; text-align: center; box-shadow: 0 10px 28px rgba(15,23,42,0.12); }}
  .pill {{ display: inline-block; margin-bottom: 12px; padding: 5px 18px; background: #0f172a; color: #ffffff; border-radius: 999px; font-size: 18px; font-weight: 800; letter-spacing: 3px; }}
  .quote {{ font-size: {font_px}px; line-height: 1.24; font-weight: 900; color: #0f172a; }}
  .blue-accent {{ color: #dc2626; }}
  .brand {{ position: absolute; bottom: 24px; left: 0; right: 0; text-align: center; font-size: 18px; font-weight: 800; letter-spacing: 3px; color: #1e293b; opacity: 0.78; }}
</style></head><body>
  <div class="card">
    <div class="banner">
      {badge_html}
      <div class="quote">{q_html}</div>
    </div>
    <div class="brand">{brand}</div>
  </div>
</body></html>"""


def _tpl_gold_spotlight(
    slide: SlideContent,
    art_uri: str,
    brand: str,
    monogram: str,
    handle: str,
    badge: str,
    motif: str,
) -> str:
    """Split or bottom-overlay dark-and-gold editorial poster (Live Motivation / MC style)."""
    q_html = _highlight_html(slide.quote.strip().upper(), slide.accent, "gold")
    font_px = _scale_font(slide.quote, large=56, medium=48, compact=40)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""

    if motif == "mentor_split":
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; background: #050507; color: #ffffff; font-family: 'Montserrat', Arial, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: #050507 url("{art_uri}") center/cover no-repeat; }}
  .right-fade {{ position: absolute; inset: 0; background: linear-gradient(90deg, rgba(5,5,7,0.08) 0%, rgba(5,5,7,0.72) 44%, rgba(5,5,7,0.97) 56%, #050507 100%); }}
  .col {{ position: absolute; top: 180px; bottom: 140px; left: 480px; right: 64px; display: flex; flex-direction: column; justify-content: center; }}
  .eyebrow {{ font-size: 28px; font-weight: 800; letter-spacing: 3px; color: #facc15; text-transform: uppercase; margin-bottom: 18px; border-bottom: 3px solid #facc15; padding-bottom: 12px; display: inline-block; }}
  .quote {{ font-size: {font_px}px; line-height: 1.24; font-weight: 900; color: #ffffff; text-transform: uppercase; }}
  .gold {{ color: #facc15; }}
  .attr {{ margin-top: 38px; font-size: 24px; font-style: italic; font-weight: 700; color: rgba(255,255,255,0.82); }}
</style></head><body>
  <div class="card">
    <div class="right-fade"></div>
    <div class="col">
      <div class="eyebrow">{badge or 'DAILY MINDSET'}</div>
      <div class="quote">“{q_html}”</div>
      <div class="attr">— {brand}</div>
    </div>
  </div>
</body></html>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; background: #050507; color: #ffffff; font-family: 'Anton', 'Montserrat', Impact, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: #050507 url("{art_uri}") center top/cover no-repeat; }}
  .grad {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.35) 45%, rgba(0,0,0,0.92) 64%, #050507 75%); }}
  .content {{ position: absolute; left: 68px; right: 68px; bottom: 72px; text-align: center; display: flex; flex-direction: column; align-items: center; }}
  .pill {{ margin-bottom: 18px; padding: 6px 22px; border: 2px solid #facc15; border-radius: 999px; color: #facc15; font-family: 'Montserrat', sans-serif; font-size: 20px; font-weight: 900; letter-spacing: 4px; }}
  .quote {{ font-size: {font_px + 4}px; line-height: 1.18; letter-spacing: 1px; color: #ffffff; text-transform: uppercase; text-shadow: 0 4px 20px rgba(0,0,0,0.9); }}
  .gold {{ color: #facc15; }}
  .gold-bar {{ width: 640px; max-width: 90%; height: 3px; background: linear-gradient(90deg, transparent, #facc15, transparent); margin: 26px 0 18px; }}
  .seal {{ width: 96px; height: 96px; border-radius: 50%; border: 3px solid #facc15; display: flex; align-items: center; justify-content: center; font-family: 'Montserrat', sans-serif; font-weight: 900; font-size: 28px; color: #facc15; background: rgba(5,5,7,0.88); letter-spacing: 2px; }}
  .handle {{ margin-top: 12px; font-family: 'Montserrat', sans-serif; font-size: 17px; font-weight: 700; letter-spacing: 3px; color: rgba(255,255,255,0.65); text-transform: uppercase; }}
</style></head><body>
  <div class="card">
    <div class="grad"></div>
    <div class="content">
      {badge_html}
      <div class="quote">{q_html}</div>
      <div class="gold-bar"></div>
      <div class="seal">{monogram}</div>
      <div class="handle">{handle}</div>
    </div>
  </div>
</body></html>"""


def _tpl_monochrome_alpha(
    slide: SlideContent,
    art_uri: str,
    accent_color: str,
    monogram: str,
    handle: str,
    badge: str,
) -> str:
    """Full-bleed monochrome/storm alpha wildlife & warrior poster (Alpha Male Aesthetics style)."""
    q_html = _highlight_html(slide.quote.strip().upper(), slide.accent, "accent")
    font_px = _scale_font(slide.quote, large=64, medium=54, compact=46)
    badge_html = f'<div class="badge" style="border-color:{accent_color};color:{accent_color};">{badge}</div>' if badge else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@600;700&family=Montserrat:wght@700;800&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1350px; overflow: hidden; background: #040406; color: #ffffff; font-family: 'Oswald', Impact, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1350px; background: #040406 url("{art_uri}") center/cover no-repeat; }}
  .vignette {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(0,0,0,0.06) 0%, rgba(0,0,0,0.22) 50%, rgba(0,0,0,0.82) 74%, rgba(0,0,0,0.96) 100%); }}
  .content {{ position: absolute; left: 72px; right: 72px; bottom: 86px; text-align: center; display: flex; flex-direction: column; align-items: center; }}
  .monogram {{ font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 5px; padding: 4px 16px; border-top: 1px solid rgba(255,255,255,0.45); border-bottom: 1px solid rgba(255,255,255,0.45); margin-bottom: 16px; }}
  .badge {{ margin-bottom: 14px; font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 4px; padding: 6px 20px; border: 2px solid; border-radius: 999px; background: rgba(0,0,0,0.68); }}
  .quote {{ font-size: {font_px}px; line-height: 1.20; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; text-shadow: 0 6px 26px rgba(0,0,0,0.98); }}
  .accent {{ color: {accent_color}; }}
  .handle {{ margin-top: 22px; font-family: 'Montserrat', sans-serif; font-size: 16px; font-weight: 700; letter-spacing: 3.5px; color: rgba(255,255,255,0.52); text-transform: uppercase; }}
</style></head><body>
  <div class="card">
    <div class="vignette"></div>
    <div class="content">
      <div class="monogram">{monogram}</div>
      {badge_html}
      <div class="quote">{q_html}</div>
      <div class="handle">{handle}</div>
    </div>
  </div>
</body></html>"""


def _render_html_with_playwright(html_path: Path, image_path: Path, width: int, height: int) -> bool:
    """Render an HTML file to a JPEG image using headless Chromium via Playwright."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=25000)
            page.evaluate(
                "() => Promise.race([document.fonts ? document.fonts.ready : Promise.resolve(), new Promise(r => setTimeout(r, 4000))])"
            )
            page.screenshot(path=str(image_path), type="jpeg", quality=93)
        finally:
            browser.close()
    return image_path.exists() and image_path.stat().st_size > 10_000


def _render_fallback_with_pillow(
    config: AppConfig,
    slide: SlideContent,
    image_path: Path,
    accent_color: str,
) -> bool:
    """Render a clean card directly with Pillow when Playwright is unavailable."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError:
        return False

    w, h = config.image_width, config.image_height
    img = Image.new("RGB", (w, h), (10, 10, 14))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    words = slide.quote.upper().split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 26 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    y_pos = h // 2 - (len(lines) * 22)
    for line in lines:
        color = accent_color if slide.accent and slide.accent.upper() in line else "#FFFFFF"
        draw.text((w // 2, y_pos), line, fill=color, anchor="mm", font=font)
        y_pos += 44

    img.save(image_path, format="JPEG", quality=92)
    return True


def render_slide_assets(
    config: AppConfig,
    slide: SlideContent,
    theme_meta: dict[str, Any],
    output_dir: Path,
    stem: str,
    seed: int,
    allow_remote_art: bool = True,
    page_brand: str | None = None,
) -> dict[str, Any]:
    """Generate artwork + HTML + rendered JPEG image (when Chromium/Pillow is available)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    accent_color = str(theme_meta.get("accent", "#FF3B30"))
    layout_style = str(theme_meta.get("layout_style", "monochrome_alpha"))
    svg_motif = str(theme_meta.get("svg_motif", "lion"))
    art_cache_path = output_dir / f"{stem}_art.jpg"
    art_uri, art_source = resolve_artwork_data_uri(
        config=config,
        theme_meta=theme_meta,
        seed=seed,
        allow_remote_art=allow_remote_art,
        cache_path=art_cache_path,
    )

    html_content = build_card_html(
        config=config,
        slide=slide,
        artwork_data_uri=art_uri,
        accent_color=accent_color,
        layout_style=layout_style,
        svg_motif=svg_motif,
        page_brand=page_brand,
        is_ai_art=(art_source == "ai_image"),
    )
    html_path = output_dir / f"{stem}.html"
    html_path.write_text(html_content, encoding="utf-8")

    image_path = output_dir / f"{stem}.jpg"
    rendered_via = "html_only"
    if _render_html_with_playwright(html_path, image_path, config.image_width, config.image_height):
        rendered_via = "playwright_chromium"
    elif _render_fallback_with_pillow(config, slide, image_path, accent_color):
        rendered_via = "pillow_fallback"

    return {
        "html_path": html_path,
        "image_path": image_path if image_path.exists() else None,
        "art_source": art_source,
        "layout_style": layout_style,
        "rendered_via": rendered_via,
    }
