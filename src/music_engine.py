"""Royalty-free CC0 background music selector matched to post mood and visual style."""

from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from src.config import ROOT_DIR


OPENLOFI_CATALOG_URL = "https://raw.githubusercontent.com/btahir/open-lofi/main/catalog.json"
OPENLOFI_ZIP_URL = "https://github.com/btahir/open-lofi/releases/latest/download/openlofi.zip"
CUSTOM_MUSIC_DIR = ROOT_DIR / "assets" / "music"

LAYOUT_TO_CATEGORIES: dict[str, tuple[str, ...]] = {
    "monochrome_alpha": ("late-night", "hybrid", "ambient-lofi"),
    "gold_spotlight": ("late-night", "hybrid", "activities"),
    "paper_sketch": ("ambient-lofi", "activities", "seasonal-weather"),
    "sunrise_metaphor": ("seasonal-weather", "ambient-lofi", "soul-rnb"),
    "saffron_editorial": ("jazzhop", "hybrid", "late-night"),
    "cartoon_metaphor": ("chillhop", "activities", "funk-soul"),
}


def get_music_cache_dir() -> Path:
    """Return persistent cache directory for extracted CC0 music tracks."""
    explicit = os.getenv("MUSIC_CACHE_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return Path.home() / ".cache" / "openlofi"


def ensure_openlofi_cache(cache_dir: Path | None = None, max_tracks: int = 166) -> list[Path]:
    """Download and extract CC0 OpenLo-Fi MP3 tracks if cache is empty."""
    target_dir = cache_dir or get_music_cache_dir()
    existing = sorted(target_dir.rglob("*.mp3"))
    if existing:
        return existing

    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "openlofi.zip"
    try:
        req = urllib.request.Request(OPENLOFI_ZIP_URL, headers={"User-Agent": "AttitudeAutoposter/1.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, zip_path.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)

        cat_req = urllib.request.Request(OPENLOFI_CATALOG_URL, headers={"User-Agent": "AttitudeAutoposter/1.0"})
        catalog = json.loads(urllib.request.urlopen(cat_req, timeout=20).read().decode("utf-8"))
        (target_dir / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        cat_by_file = {
            str(t["filename"]): str(t.get("category", "misc"))
            for t in catalog.get("tracks", [])
            if t.get("filename")
        }

        extracted = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".mp3"):
                    continue
                base = Path(member.filename).name
                category = cat_by_file.get(base, Path(member.filename).parent.name or "misc")
                dest = target_dir / category / base
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, dest.open("wb") as dst:
                    dst.write(src.read())
                extracted += 1
                if extracted >= max_tracks:
                    break
    except (urllib.error.URLError, zipfile.BadZipFile, TimeoutError, OSError):
        return sorted(target_dir.rglob("*.mp3"))
    finally:
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)

    return sorted(target_dir.rglob("*.mp3"))


def select_background_track(
    layout_style: str,
    seed: int,
    allow_download: bool = True,
    cache_dir: Path | None = None,
    custom_dir: Path = CUSTOM_MUSIC_DIR,
) -> dict[str, Any] | None:
    """Select a mood-matched royalty-free MP3 track from custom assets or OpenLo-Fi cache."""
    rng = random.Random(seed)
    preferred_cats = LAYOUT_TO_CATEGORIES.get(layout_style, ("late-night", "ambient-lofi"))
    custom_tracks = sorted(custom_dir.rglob("*.mp3")) if custom_dir.exists() else []
    if custom_tracks:
        mood_custom = [p for p in custom_tracks if p.parent.name in preferred_cats]
        chosen = rng.choice(mood_custom or custom_tracks)
        return {
            "path": chosen,
            "title": chosen.stem.replace("-", " ").title(),
            "category": chosen.parent.name if chosen.parent != custom_dir else "custom",
            "license": "user_provided",
        }

    target_dir = cache_dir or get_music_cache_dir()
    tracks = sorted(target_dir.rglob("*.mp3"))
    if not tracks and allow_download:
        tracks = ensure_openlofi_cache(target_dir)

    if not tracks:
        return None

    preferred_cats = LAYOUT_TO_CATEGORIES.get(layout_style, ("late-night", "ambient-lofi"))
    mood_pool = [p for p in tracks if p.parent.name in preferred_cats]
    chosen = rng.choice(mood_pool or tracks)
    return {
        "path": chosen,
        "title": chosen.stem.replace("-", " ").title(),
        "category": chosen.parent.name,
        "license": "CC0-1.0",
    }
