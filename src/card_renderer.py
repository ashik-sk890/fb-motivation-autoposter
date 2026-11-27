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


def _derive_page_branding(config: AppConfig, page_brand: str | None) -> tuple[str, str, str]:
    """Resolve clean display brand, initials monogram, and handle for each target Page."""
    effective_name = (page_brand or config.brand_name).strip()
    if page_brand and page_brand.strip():
        words = [w for w in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in effective_name).split() if w]
        derived_mono = "".join(w[0].upper() for w in words)[:4] or config.brand_monogram
        slug = "".join(ch.lower() for ch in effective_name if ch.isalnum())
        derived_handle = f"@{slug}" if slug else config.brand_handle
        mono = derived_mono if config.brand_monogram == "AP" else config.brand_monogram
        handle = derived_handle if config.brand_handle in ("@attitude__mindset", "@attitude__test") else config.brand_handle
        return effective_name, mono, handle
    return effective_name, config.brand_monogram, config.brand_handle


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
    raw_brand, raw_mono, raw_handle = _derive_page_branding(config, page_brand)
    brand_label = html.escape(raw_brand)
    handle = html.escape(raw_handle)
    monogram = html.escape(raw_mono)
    badge = html.escape(slide.badge)

    if layout_style == "paper_sketch":
        return _tpl_paper_sketch(slide, artwork_data_uri, brand_label, badge, is_ai_art=is_ai_art)
    if layout_style == "sunrise_metaphor":
        return _tpl_sunrise_metaphor(slide, artwork_data_uri, brand_label, badge)
    if layout_style == "saffron_editorial":
        return _tpl_saffron_editorial(slide, artwork_data_uri, brand_label, badge, is_ai_art=is_ai_art)
    if layout_style == "cartoon_metaphor":
        return _tpl_cartoon_metaphor(slide, artwork_data_uri, brand_label, badge)
    if layout_style == "pastel_viral":
        return _tpl_pastel_viral(slide, artwork_data_uri, brand_label, monogram, handle, badge, accent_color)
    if layout_style == "vibrant_magazine":
        return _tpl_vibrant_magazine(slide, artwork_data_uri, brand_label, monogram, handle, badge, accent_color)
    if layout_style == "gold_spotlight":
        return _tpl_gold_spotlight(slide, artwork_data_uri, brand_label, monogram, handle, badge, svg_motif)
    return _tpl_monochrome_alpha(slide, artwork_data_uri, accent_color, monogram, handle, badge)


def _tpl_paper_sketch(slide: SlideContent, art_uri: str, brand: str, badge: str, is_ai_art: bool = False) -> str:
    """Full-screen 9:16 sketchbook paper + dark handwritten/serif ink + crimson swoosh."""
    quote_txt = slide.quote.strip().title() if len(slide.quote) > 35 else slide.quote.strip()
    q_html = _highlight_html(quote_txt, slide.accent, "red-accent")
    font_px = _scale_font(quote_txt, large=64, medium=54, compact=46)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    art_layer_css = (
        f'.art-inset {{ position: absolute; left: 24px; right: 24px; top: 580px; bottom: 210px; background: url("{art_uri}") center/112% no-repeat; mix-blend-mode: multiply; filter: contrast(1.22) brightness(1.08); -webkit-mask-image: radial-gradient(ellipse 66% 64% at 50% 50%, black 52%, transparent 92%); mask-image: radial-gradient(ellipse 66% 64% at 50% 50%, black 52%, transparent 92%); }}'
        if is_ai_art
        else f'.card {{ background: #faf6ee url("{art_uri}") center/cover no-repeat; }}'
    )
    art_div = '<div class="art-inset"></div>' if is_ai_art else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,600;0,700;1,600&family=Patrick+Hand&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #faf6ee; font-family: 'Patrick Hand', 'Lora', Georgia, serif; color: #18181b; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: radial-gradient(circle at 50% 45%, #fffdf8 52%, #efe8d8 100%); }}
  {art_layer_css}
  .top-text {{ position: absolute; top: 195px; left: 76px; right: 76px; text-align: center; }}
  .pill {{ display: inline-block; margin-bottom: 18px; padding: 6px 22px; border: 2px solid #dc2626; border-radius: 999px; color: #dc2626; font-family: Arial, sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 3px; }}
  .quote {{ font-size: {font_px}px; line-height: 1.28; font-weight: 600; color: #1c1917; letter-spacing: 0.4px; }}
  .red-accent {{ color: #dc2626; text-decoration: underline; text-decoration-color: rgba(220,38,38,0.72); text-underline-offset: 10px; text-decoration-thickness: 4px; }}
  .divider {{ margin: 30px auto 0; width: 280px; height: 18px; display: flex; align-items: center; justify-content: center; gap: 12px; color: #44403c; font-size: 20px; }}
  .line {{ flex: 1; height: 2px; background: #44403c; opacity: 0.55; }}
  .brand {{ position: absolute; bottom: 185px; left: 0; right: 0; text-align: center; font-family: 'Lora', Georgia, serif; font-size: 22px; color: #44403c; letter-spacing: 1px; opacity: 0.8; }}
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
    """Full-bleed 9:16 golden sunrise cinema poster above Facebook Reels caption zone."""
    headline = badge or "TRUTH"
    body_text = slide.quote.strip().upper()
    q_html = _highlight_html(body_text, slide.accent, "sun-accent")
    font_px = _scale_font(body_text, large=56, medium=48, compact=41)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #0a0c14; font-family: 'Montserrat', Arial, sans-serif; color: #ffffff; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #0a0c14 url("{art_uri}") center center/cover no-repeat; }}
  .scrim {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(8,10,18,0.12) 0%, rgba(8,10,18,0.0) 18%, rgba(8,10,18,0.0) 46%, rgba(8,10,18,0.78) 68%, rgba(6,8,14,0.96) 100%); }}
  .panel {{ position: absolute; left: 58px; right: 118px; bottom: 385px; display: flex; flex-direction: column; align-items: flex-start; }}
  .headline {{ padding: 7px 22px; border-radius: 999px; background: #ef4444; color: #ffffff; font-size: 19px; font-weight: 900; letter-spacing: 3px; margin-bottom: 18px; }}
  .quote {{ font-family: 'Anton', 'Montserrat', sans-serif; font-size: {font_px + 4}px; line-height: 1.16; letter-spacing: 0.8px; color: #ffffff; text-shadow: 0 6px 24px rgba(0,0,0,0.95); }}
  .sun-accent {{ color: #fde047; }}
  .brand {{ margin-top: 18px; font-size: 18px; font-weight: 800; letter-spacing: 2.5px; text-transform: uppercase; color: rgba(255,255,255,0.88); }}
</style></head><body>
  <div class="card">
    <div class="scrim"></div>
    <div class="panel">
      <div class="headline">{headline}</div>
      <div class="quote">{q_html}</div>
      <div class="brand">{brand}</div>
    </div>
  </div>
</body></html>"""


def _tpl_saffron_editorial(slide: SlideContent, art_uri: str, brand: str, badge: str, is_ai_art: bool = False) -> str:
    """Full-screen 9:16 vibrant saffron editorial ink canvas."""
    quote_txt = slide.quote.strip().capitalize()
    q_html = _highlight_html(quote_txt, slide.accent, "ink-emphasis")
    font_px = _scale_font(quote_txt, large=64, medium=54, compact=46)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    art_layer_css = (
        f'.art-inset {{ position: absolute; left: 32px; right: 32px; top: 610px; bottom: 180px; background: url("{art_uri}") center bottom/contain no-repeat; mix-blend-mode: multiply; filter: contrast(1.2) brightness(1.07); -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 100%); mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 100%); }}'
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
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; font-family: 'Lora', Georgia, serif; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: radial-gradient(circle at 50% 42%, #fde047 0%, #fbbf24 52%, #f59e0b 100%); }}
  {art_layer_css}
  .top-text {{ position: absolute; top: 205px; left: 78px; right: 78px; text-align: center; }}
  .pill {{ display: inline-block; margin-bottom: 16px; padding: 6px 20px; border: 2px solid #111111; border-radius: 999px; font-family: Arial, sans-serif; font-weight: 800; font-size: 19px; letter-spacing: 3px; color: #111111; }}
  .quote {{ font-size: {font_px}px; line-height: 1.26; font-weight: 700; color: #111111; text-shadow: 0 2px 14px rgba(251,191,36,0.55); }}
  .ink-emphasis {{ text-decoration: underline; text-decoration-thickness: 4px; text-underline-offset: 8px; }}
  .sig {{ position: absolute; left: 60px; bottom: 205px; font-style: italic; font-size: 20px; font-weight: 700; color: #111111; background: rgba(251, 191, 36, 0.9); padding: 5px 16px; border-radius: 999px; }}
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
    """Full-bleed 9:16 Pixar/Shinkai 3D animated cinema poster with edge-free Reels typography."""
    quote_txt = slide.quote.strip().upper()
    q_html = _highlight_html(quote_txt, slide.accent, "blue-accent")
    font_px = _scale_font(quote_txt, large=56, medium=48, compact=41)
    badge_html = f'<div class="pill">{badge}</div>' if badge else '<div class="pill">INSIGHT</div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #0a101d; font-family: 'Montserrat', Arial, sans-serif; color: #ffffff; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #0a101d url("{art_uri}") center center/cover no-repeat; }}
  .scrim {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(10,16,29,0.12) 0%, rgba(10,16,29,0.0) 18%, rgba(10,16,29,0.0) 46%, rgba(10,16,29,0.78) 68%, rgba(7,11,20,0.96) 100%); }}
  .banner {{ position: absolute; bottom: 385px; left: 58px; right: 118px; display: flex; flex-direction: column; align-items: flex-start; }}
  .pill {{ display: inline-block; margin-bottom: 16px; padding: 7px 20px; background: #0284c7; color: #ffffff; border-radius: 999px; font-size: 18px; font-weight: 900; letter-spacing: 3px; }}
  .quote {{ font-family: 'Anton', 'Montserrat', sans-serif; font-size: {font_px + 4}px; line-height: 1.16; letter-spacing: 0.8px; color: #ffffff; text-shadow: 0 6px 26px rgba(0,0,0,0.95); }}
  .blue-accent {{ color: #fde047; }}
  .brand {{ margin-top: 18px; font-size: 18px; font-weight: 800; letter-spacing: 2.5px; text-transform: uppercase; color: rgba(255,255,255,0.88); }}
</style></head><body>
  <div class="card">
    <div class="scrim"></div>
    <div class="banner">
      {badge_html}
      <div class="quote">{q_html}</div>
      <div class="brand">{brand}</div>
    </div>
  </div>
</body></html>"""


def _tpl_pastel_viral(
    slide: SlideContent,
    art_uri: str,
    brand: str,
    monogram: str,
    handle: str,
    badge: str,
    accent_color: str,
) -> str:
    """Full-bleed 9:16 edge-to-edge cinematic scene with glowing highlights & Reels-safe typography."""
    quote_txt = slide.quote.strip().upper()
    q_html = _highlight_html(quote_txt, slide.accent, "cine-accent")
    font_px = _scale_font(quote_txt, large=58, medium=48, compact=41)
    hi = accent_color if accent_color and accent_color != "#111111" else "#FACC15"
    badge_html = f'<div class="pill">{badge}</div>' if badge else '<div class="pill">MINDSET</div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@700;800;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #070b14; font-family: 'Montserrat', Arial, sans-serif; color: #ffffff; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #070b14 url("{art_uri}") center center/cover no-repeat; }}
  .cinema-scrim {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(7,11,20,0.12) 0%, rgba(7,11,20,0.0) 18%, rgba(7,11,20,0.0) 46%, rgba(7,11,20,0.78) 68%, rgba(5,8,16,0.96) 100%); }}
  .panel {{ position: absolute; left: 58px; right: 118px; bottom: 385px; display: flex; flex-direction: column; align-items: flex-start; }}
  .top-tag {{ display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }}
  .pill {{ padding: 7px 20px; background: {hi}; color: #ffffff; border-radius: 999px; font-size: 18px; font-weight: 900; letter-spacing: 3px; box-shadow: 0 6px 20px rgba(0,0,0,0.35); }}
  .seal {{ width: 48px; height: 48px; border-radius: 50%; border: 2px solid #facc15; background: rgba(7,11,20,0.72); color: #facc15; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 900; }}
  .quote {{ font-family: 'Anton', 'Montserrat', sans-serif; font-size: {font_px + 4}px; line-height: 1.15; letter-spacing: 0.8px; color: #ffffff; text-transform: uppercase; text-shadow: 0 6px 26px rgba(0,0,0,0.95); }}
  .cine-accent {{ color: #fde047; }}
  .bar {{ width: 220px; height: 5px; border-radius: 4px; background: linear-gradient(90deg, {hi}, #fde047); margin: 20px 0 12px; }}
  .brand {{ font-size: 18px; font-weight: 800; letter-spacing: 2.5px; color: rgba(255,255,255,0.88); text-transform: uppercase; text-shadow: 0 2px 10px rgba(0,0,0,0.9); }}
</style></head><body>
  <div class="card">
    <div class="cinema-scrim"></div>
    <div class="panel">
      <div class="top-tag">{badge_html}<span class="seal">{monogram}</span></div>
      <div class="quote">{q_html}</div>
      <div class="bar"></div>
      <div class="brand">{brand}</div>
    </div>
  </div>
</body></html>"""


def _tpl_vibrant_magazine(
    slide: SlideContent,
    art_uri: str,
    brand: str,
    monogram: str,
    handle: str,
    badge: str,
    accent_color: str,
) -> str:
    """Full-bleed 9:16 ultra-vibrant cinema poster positioned cleanly above Reels overlays."""
    quote_txt = slide.quote.strip().upper()
    q_html = _highlight_html(quote_txt, slide.accent, "mag-accent")
    font_px = _scale_font(quote_txt, large=58, medium=48, compact=41)
    hi = accent_color if accent_color and accent_color != "#111111" else "#F97316"
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@700;800;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #090d16; font-family: 'Montserrat', Arial, sans-serif; color: #ffffff; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #090d16 url("{art_uri}") center center/cover no-repeat; }}
  .cine-fade {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(9,13,22,0.12) 0%, rgba(9,13,22,0.0) 18%, rgba(9,13,22,0.0) 46%, rgba(9,13,22,0.78) 68%, rgba(6,9,16,0.96) 100%); }}
  .panel {{ position: absolute; left: 58px; right: 118px; bottom: 385px; text-align: left; display: flex; flex-direction: column; align-items: flex-start; }}
  .pill {{ margin-bottom: 14px; padding: 7px 22px; background: {hi}; color: #ffffff; border-radius: 999px; font-size: 18px; font-weight: 800; letter-spacing: 3px; }}
  .quote {{ font-family: 'Anton', 'Montserrat', sans-serif; font-size: {font_px + 4}px; line-height: 1.16; color: #ffffff; text-transform: uppercase; letter-spacing: 0.8px; text-shadow: 0 6px 24px rgba(0,0,0,0.95); }}
  .mag-accent {{ color: #fde047; }}
  .bar {{ width: 280px; max-width: 80%; height: 4px; border-radius: 4px; background: linear-gradient(90deg, #fde047, {hi}, transparent); margin: 20px 0 14px; }}
  .sig-row {{ display: flex; align-items: center; gap: 14px; font-size: 18px; font-weight: 800; color: rgba(255,255,255,0.88); letter-spacing: 2px; text-transform: uppercase; }}
  .seal {{ width: 48px; height: 48px; border-radius: 50%; border: 2px solid #fde047; background: rgba(9,13,22,0.85); color: #fde047; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 900; }}
</style></head><body>
  <div class="card">
    <div class="cine-fade"></div>
    <div class="panel">
      {badge_html}
      <div class="quote">{q_html}</div>
      <div class="bar"></div>
      <div class="sig-row"><span class="seal">{monogram}</span><span>{brand}</span></div>
    </div>
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
    """Split or bottom-overlay dark-and-gold editorial poster (9:16 Reels full-view)."""
    q_html = _highlight_html(slide.quote.strip().upper(), slide.accent, "gold")
    font_px = _scale_font(slide.quote, large=60, medium=50, compact=42)
    badge_html = f'<div class="pill">{badge}</div>' if badge else ""

    if motif == "mentor_split":
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #050507; color: #ffffff; font-family: 'Montserrat', Arial, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #050507 url("{art_uri}") center/cover no-repeat; }}
  .right-fade {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(5,5,7,0.12) 0%, rgba(5,5,7,0.45) 54%, rgba(5,5,7,0.92) 74%, #050507 100%); }}
  .col {{ position: absolute; left: 64px; right: 112px; bottom: 235px; display: flex; flex-direction: column; justify-content: flex-end; }}
  .eyebrow {{ font-size: 26px; font-weight: 800; letter-spacing: 3px; color: #facc15; text-transform: uppercase; margin-bottom: 18px; border-bottom: 3px solid #facc15; padding-bottom: 10px; display: inline-block; align-self: flex-start; }}
  .quote {{ font-size: {font_px}px; line-height: 1.24; font-weight: 900; color: #ffffff; text-transform: uppercase; text-shadow: 0 4px 20px rgba(0,0,0,0.9); }}
  .gold {{ color: #facc15; }}
  .attr {{ margin-top: 28px; font-size: 22px; font-style: italic; font-weight: 700; color: rgba(255,255,255,0.85); }}
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
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #050507; color: #ffffff; font-family: 'Anton', 'Montserrat', Impact, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #050507 url("{art_uri}") center top/cover no-repeat; }}
  .grad {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.35) 52%, rgba(0,0,0,0.9) 74%, #050507 100%); }}
  .content {{ position: absolute; left: 64px; right: 104px; bottom: 235px; text-align: center; display: flex; flex-direction: column; align-items: center; }}
  .pill {{ margin-bottom: 18px; padding: 6px 22px; border: 2px solid #facc15; border-radius: 999px; color: #facc15; font-family: 'Montserrat', sans-serif; font-size: 20px; font-weight: 900; letter-spacing: 4px; }}
  .quote {{ font-size: {font_px + 4}px; line-height: 1.18; letter-spacing: 1px; color: #ffffff; text-transform: uppercase; text-shadow: 0 4px 20px rgba(0,0,0,0.9); }}
  .gold {{ color: #facc15; }}
  .gold-bar {{ width: 520px; max-width: 85%; height: 3px; background: linear-gradient(90deg, transparent, #facc15, transparent); margin: 24px 0 18px; }}
  .seal {{ width: 82px; height: 82px; border-radius: 50%; border: 3px solid #facc15; display: flex; align-items: center; justify-content: center; font-family: 'Montserrat', sans-serif; font-weight: 900; font-size: 24px; color: #facc15; background: rgba(5,5,7,0.88); letter-spacing: 2px; }}
  .handle {{ margin-top: 12px; font-family: 'Montserrat', sans-serif; font-size: 17px; font-weight: 700; letter-spacing: 3px; color: rgba(255,255,255,0.72); text-transform: uppercase; }}
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
    """Full-bleed 9:16 monochrome/storm alpha wildlife & warrior poster."""
    q_html = _highlight_html(slide.quote.strip().upper(), slide.accent, "accent")
    font_px = _scale_font(slide.quote, large=64, medium=54, compact=46)
    badge_html = f'<div class="badge" style="border-color:{accent_color};color:{accent_color};">{badge}</div>' if badge else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=1080, initial-scale=1.0" />
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@600;700&family=Montserrat:wght@700;800&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #040406; color: #ffffff; font-family: 'Oswald', Impact, sans-serif; }}
  .card {{ position: relative; width: 1080px; height: 1920px; background: #040406 url("{art_uri}") center/cover no-repeat; }}
  .vignette {{ position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.25) 50%, rgba(0,0,0,0.82) 74%, rgba(0,0,0,0.96) 100%); }}
  .content {{ position: absolute; left: 64px; right: 104px; bottom: 235px; text-align: center; display: flex; flex-direction: column; align-items: center; }}
  .monogram {{ font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 5px; padding: 4px 16px; border-top: 1px solid rgba(255,255,255,0.45); border-bottom: 1px solid rgba(255,255,255,0.45); margin-bottom: 16px; }}
  .badge {{ margin-bottom: 14px; font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 20px; letter-spacing: 4px; padding: 6px 20px; border: 2px solid; border-radius: 999px; background: rgba(0,0,0,0.68); }}
  .quote {{ font-size: {font_px}px; line-height: 1.20; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; text-shadow: 0 6px 26px rgba(0,0,0,0.98); }}
  .accent {{ color: {accent_color}; }}
  .handle {{ margin-top: 22px; font-family: 'Montserrat', sans-serif; font-size: 16px; font-weight: 700; letter-spacing: 3.5px; color: rgba(255,255,255,0.62); text-transform: uppercase; }}
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
    fast_tier: bool = False,
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
        prompt_override=slide.image_prompt,
        fast_tier=fast_tier,
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
