"""CLI entrypoint for rendering, previewing, and publishing daily multi-page Facebook posts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.card_renderer import render_slide_assets
from src.composio_publisher import list_managed_pages, publish_post, resolve_target_pages
from src.config import AppConfig, GENERATED_DIR, QUOTE_VAULT_PATH
from src.content_engine import PostPlan, SlideContent, build_post_plan, load_json, save_history
from src.music_engine import select_background_track
from src.video_engine import is_ffmpeg_available, render_video_from_cards


def resolve_slot(slot_arg: str, utc_now: datetime | None = None) -> int:
    """Resolve explicit slot '1'..'5' or 'auto' mapped cleanly across 4 daily UTC windows."""
    if slot_arg != "auto":
        slot = int(slot_arg)
        if slot not in (1, 2, 3, 4, 5):
            raise ValueError(f"Slot must be 1..5, got {slot}")
        return slot

    now = utc_now or datetime.now(timezone.utc)
    hour = now.hour
    if hour <= 6:
        return 1
    if hour <= 10:
        return 2
    if hour <= 14:
        return 3
    return 4


def _render_single_job(
    config: AppConfig,
    slot: int,
    page_id: str,
    page_name: str,
    output_dir: Path,
    allow_remote_art: bool,
    seed: int,
    extra_used_hashes: set[str],
    media_mode: str = "auto",
) -> dict[str, Any]:
    """Generate unique content and render card assets for one target Facebook Page."""
    plan = build_post_plan(
        config=config,
        slot=slot,
        seed=seed,
        extra_used_hashes=extra_used_hashes,
        brand_override=page_name or config.brand_name,
    )
    if plan.content_hash:
        extra_used_hashes.add(plan.content_hash)

    vault = load_json(QUOTE_VAULT_PATH, {})
    themes: dict[str, Any] = vault.get("visual_themes", {})
    rendered_cards: list[dict[str, Any]] = []
    image_paths: list[str] = []
    public_urls: list[str] = []
    cache_bust = int(time.time())
    safe_pid = "".join(ch for ch in page_id if ch.isalnum()) or "default"

    for idx, slide in enumerate(plan.slides, start=1):
        theme_meta = themes.get(slide.visual_theme, next(iter(themes.values()), {}))
        stem = f"p_{safe_pid}_s{slot}_c{idx}"
        assets = render_slide_assets(
            config=config,
            slide=slide,
            theme_meta=theme_meta,
            output_dir=output_dir,
            stem=stem,
            seed=seed + idx * 97,
            allow_remote_art=allow_remote_art,
            page_brand=page_name or config.brand_name,
            fast_tier=(idx > 1),
        )
        img_path = assets["image_path"]
        if img_path is not None:
            image_paths.append(str(img_path))
            if config.public_media_base_url:
                public_urls.append(f"{config.public_media_base_url}/{img_path.name}?v={cache_bust}")

        rendered_cards.append(
            {
                "index": idx,
                "badge": slide.badge,
                "quote": slide.quote,
                "accent": slide.accent,
                "visual_theme": slide.visual_theme,
                "layout_style": assets["layout_style"],
                "html_path": str(assets["html_path"]),
                "image_path": str(img_path) if img_path else "",
                "art_source": assets["art_source"],
                "rendered_via": assets["rendered_via"],
            }
        )

    video_path_str = ""
    video_public_url = ""
    music_meta: dict[str, Any] = {}
    if media_mode != "photo" and image_paths and is_ffmpeg_available():
        primary_style = rendered_cards[0]["layout_style"] if rendered_cards else "monochrome_alpha"
        track = select_background_track(
            layout_style=primary_style,
            seed=seed,
            allow_download=allow_remote_art,
        )
        audio_path = Path(track["path"]) if track else None
        if track:
            music_meta = {
                "title": track["title"],
                "category": track["category"],
                "license": track["license"],
                "source": track.get("source", "openlofi"),
            }
        mp4_out = output_dir / f"p_{safe_pid}_s{slot}.mp4"
        offset_sec = 0.0 if (track and track.get("source") == "custom") else 16.0
        built_mp4 = render_video_from_cards(
            image_paths=[Path(p) for p in image_paths],
            audio_path=audio_path,
            output_mp4=mp4_out,
            audio_offset_sec=offset_sec,
        )
        if built_mp4:
            video_path_str = str(built_mp4)
            if config.public_media_base_url:
                video_public_url = f"{config.public_media_base_url}/{built_mp4.name}?v={cache_bust}"

    return {
        "page_id": page_id,
        "page_name": page_name,
        "slot": plan.slot,
        "archetype_id": plan.archetype_id,
        "archetype_name": plan.archetype_name,
        "post_type": plan.post_type,
        "source": plan.source,
        "content_hash": plan.content_hash,
        "caption": plan.caption,
        "slides": [
            {
                "quote": s.quote,
                "accent": s.accent,
                "badge": s.badge,
                "visual_theme": s.visual_theme,
                "image_prompt": s.image_prompt,
            }
            for s in plan.slides
        ],
        "cards": rendered_cards,
        "image_paths": image_paths,
        "public_urls": public_urls,
        "video_path": video_path_str,
        "video_public_url": video_public_url,
        "music_track": music_meta,
    }


def generate_and_render(
    config: AppConfig,
    slot: int,
    output_dir: Path,
    allow_remote_art: bool = True,
    seed: int | None = None,
    pages: list[dict[str, str]] | None = None,
    media_mode: str = "auto",
) -> dict[str, Any]:
    """Generate distinct posts & cards for every target Facebook Page on the slot."""
    if pages is None:
        if config.composio_api_key:
            pages = resolve_target_pages(config)
        else:
            pages = [{"id": config.facebook_page_id or "preview", "name": config.brand_name}]

    base_seed = seed if seed is not None else int(time.time() * 1000)
    extra_used_hashes: set[str] = set()
    jobs: list[dict[str, Any]] = []

    for page_idx, page in enumerate(pages):
        job = _render_single_job(
            config=config,
            slot=slot,
            page_id=page["id"],
            page_name=page.get("name", config.brand_name),
            output_dir=output_dir,
            allow_remote_art=allow_remote_art,
            seed=base_seed + page_idx * 1009,
            extra_used_hashes=extra_used_hashes,
            media_mode=media_mode,
        )
        job["account"] = page.get("account", "")
        jobs.append(job)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "slot": slot,
        "pages_count": len(jobs),
        "jobs": jobs,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _plan_from_job(job: dict[str, Any]) -> PostPlan:
    """Reconstruct PostPlan from a job entry inside manifest.json."""
    slides = [
        SlideContent(
            quote=s["quote"],
            accent=s.get("accent", ""),
            badge=s.get("badge", ""),
            visual_theme=s.get("visual_theme", "dark_lion"),
            image_prompt=s.get("image_prompt", ""),
        )
        for s in job["slides"]
    ]
    return PostPlan(
        slot=int(job["slot"]),
        archetype_id=int(job["archetype_id"]),
        archetype_name=str(job["archetype_name"]),
        post_type=str(job["post_type"]),
        caption=str(job["caption"]),
        slides=slides,
        content_hash=str(job["content_hash"]),
        source=str(job["source"]),
    )


def _publish_manifest_jobs(config: AppConfig, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish every page job in manifest.json and persist deduplication history."""
    jobs = manifest.get("jobs") or [manifest]
    results: list[dict[str, Any]] = []
    for job in jobs:
        plan = _plan_from_job(job)
        image_paths = [Path(p) for p in job.get("image_paths", []) if p]
        public_urls = job.get("public_urls") or None
        target_page_id = str(job.get("page_id") or "").strip() or None
        target_account = str(job.get("account") or "").strip() or None
        video_path = Path(job["video_path"]) if job.get("video_path") else None
        video_public_url = str(job.get("video_public_url") or "").strip() or None
        try:
            pub_res = publish_post(
                config=config,
                plan=plan,
                image_paths=image_paths,
                public_urls=public_urls,
                target_page_id=target_page_id,
                account=target_account,
                video_path=video_path,
                video_public_url=video_public_url,
            )
            save_history(plan=plan, post_result=pub_res, max_items=config.max_history_items)
            results.append({"page_id": target_page_id, "page_name": job.get("page_name"), "status": "ok", **pub_res})
        except Exception as exc:
            results.append({"page_id": target_page_id, "page_name": job.get("page_name"), "status": "error", "error": str(exc)})
    return results


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run generation, style preview, or Composio multi-page publishing."""
    parser = argparse.ArgumentParser(description="Multi-Page Modern Motivation Facebook Autoposter")
    parser.add_argument("--slot", default="auto", help="Daily post slot: 1..4 (or 5) or 'auto'")
    parser.add_argument("--output-dir", default=str(GENERATED_DIR / "latest"), help="Output folder")
    parser.add_argument("--render-only", action="store_true", help="Generate and render cards without posting")
    parser.add_argument("--publish-manifest", default="", help="Publish all jobs in a rendered manifest.json")
    parser.add_argument("--dry-run", action="store_true", help="Render cards and print payload without posting")
    parser.add_argument("--preview-all", action="store_true", help="Render preview gallery across all 6 modern visual styles")
    parser.add_argument("--offline-art", action="store_true", help="Use built-in illustrated SVGs without network calls")
    parser.add_argument("--media-mode", default="auto", choices=["auto", "video", "photo"], help="Output format: video (with music), photo, or auto")
    parser.add_argument("--list-pages", action="store_true", help="List Facebook Pages connected in Composio")
    args = parser.parse_args(argv)

    config = AppConfig.from_env()
    allow_remote = not args.offline_art

    if args.list_pages:
        pages = list_managed_pages(config)
        print(json.dumps(pages, indent=2, ensure_ascii=False))
        return 0

    if args.preview_all:
        preview_dir = GENERATED_DIR / "preview_styles"
        vault = load_json(QUOTE_VAULT_PATH, {})
        themes = vault.get("visual_themes", {})
        sample_specs = [
            ("paper_sketch_bird", "dark_eagle", SlideContent("NEVER BE AN OPTION. BE THE PRIORITY OR BE ALONE.", "PRIORITY", "", "dark_eagle")),
            ("paper_sketch_mind", "dark_anime_moody", SlideContent("YOU WILL NEVER BE FREE UNTIL YOU FREE YOURSELF FROM THE PRISON OF YOUR OWN FALSE THOUGHTS.", "PRISON OF YOUR OWN FALSE THOUGHTS.", "", "dark_anime_moody")),
            ("sunrise_metaphor", "dark_anime_rain", SlideContent("People never see what they did to you — they only blame how you reacted.", "BLAME HOW YOU REACTED", "SAD BUT TRUE", "dark_anime_rain")),
            ("saffron_editorial", "noir_suit", SlideContent("Be smart, notice everything but act like you know nothing.", "act like you know nothing.", "", "noir_suit")),
            ("cartoon_metaphor", "dark_anime_warm", SlideContent("YOUR EFFORTS ARE NOT WASTED. YOU GAVE THEM TO THE WRONG PERSON.", "WRONG PERSON.", "", "dark_anime_warm")),
            ("gold_spotlight_split", "shadow_boxer", SlideContent("FOCUS ON YOUR OWN JOURNEY. COMPARE ONLY TO WHO YOU WERE YESTERDAY.", "YOUR OWN JOURNEY.", "MY ADVICE", "shadow_boxer")),
            ("monochrome_alpha", "dark_lion", SlideContent("WHEN THE DECISION IS MADE, NEVER LOOK BACK.", "NEVER LOOK BACK.", "", "dark_lion")),
        ]
        rendered = []
        for idx, (slug, theme_key, slide) in enumerate(sample_specs, start=1):
            res = render_slide_assets(
                config=config,
                slide=slide,
                theme_meta=themes[theme_key],
                output_dir=preview_dir,
                stem=slug,
                seed=900 + idx,
                allow_remote_art=allow_remote,
            )
            rendered.append({"style": slug, "html_path": str(res["html_path"])})
        print(json.dumps(rendered, indent=2, ensure_ascii=False))
        return 0

    if args.publish_manifest:
        manifest_path = Path(args.publish_manifest)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if args.dry_run:
            print(json.dumps({"dry_run": True, "manifest": manifest}, indent=2, ensure_ascii=False))
            return 0
        results = _publish_manifest_jobs(config, manifest)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 1 if all(r["status"] == "error" for r in results) else 0

    slot = resolve_slot(args.slot)
    manifest = generate_and_render(
        config=config,
        slot=slot,
        output_dir=Path(args.output_dir),
        allow_remote_art=allow_remote,
        media_mode=args.media_mode,
    )

    if args.render_only or args.dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    results = _publish_manifest_jobs(config, manifest)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 1 if all(r["status"] == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
