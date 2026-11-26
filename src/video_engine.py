"""FFmpeg video generator turning static/carousel cards + background music into MP4 posts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def is_ffmpeg_available() -> bool:
    """Return True if ffmpeg binary is installed on PATH."""
    return shutil.which("ffmpeg") is not None


def _build_single_card_cmd(
    image_path: Path,
    audio_path: Path | None,
    output_mp4: Path,
    duration_sec: float = 8.0,
    audio_offset_sec: float = 16.0,
) -> list[str]:
    """Assemble ffmpeg command for an animated 1080x1350 card with smooth zoom and audio."""
    frames = max(int(duration_sec * 30), 60)
    fade_out_start = max(duration_sec - 1.0, 1.0)
    video_filter = (
        f"[0:v]scale=1160:1450,"
        f"zoompan=z='min(zoom+0.00045,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1350:fps=30,format=yuv420p[v]"
    )

    if audio_path and audio_path.exists():
        audio_filter = (
            f"[1:a]afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.1f}:d=1.0,"
            f"loudnorm=I=-15:TP=-1.5:LRA=11[a]"
        )
        return [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-ss",
            f"{audio_offset_sec:.1f}",
            "-t",
            f"{duration_sec:.1f}",
            "-i",
            str(audio_path),
            "-filter_complex",
            f"{video_filter};{audio_filter}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_mp4),
        ]

    # Ambient fallback audio if no track is available
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-f",
        "lavfi",
        "-t",
        f"{duration_sec:.1f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex",
        video_filter,
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_mp4),
    ]


def _build_slideshow_cmd(
    image_paths: list[Path],
    audio_path: Path | None,
    output_mp4: Path,
    slide_duration_sec: float = 3.5,
    audio_offset_sec: float = 16.0,
) -> list[str]:
    """Assemble ffmpeg command stitching multiple carousel cards into a single MP4 with music."""
    total_dur = slide_duration_sec * len(image_paths)
    fade_out_start = max(total_dur - 1.2, 1.0)
    cmd = ["ffmpeg", "-y"]
    scale_parts: list[str] = []
    concat_inputs: list[str] = []

    for idx, img in enumerate(image_paths):
        cmd.extend(["-loop", "1", "-t", f"{slide_duration_sec:.1f}", "-i", str(img)])
        scale_parts.append(f"[{idx}:v]scale=1080:1350:force_original_aspect_ratio=decrease,pad=1080:1350:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{idx}]")
        concat_inputs.append(f"[v{idx}]")

    video_chain = ";".join(scale_parts) + f";{''.join(concat_inputs)}concat=n={len(image_paths)}:v=1:a=0,format=yuv420p[v]"

    if audio_path and audio_path.exists():
        audio_idx = len(image_paths)
        cmd.extend(["-ss", f"{audio_offset_sec:.1f}", "-t", f"{total_dur:.1f}", "-i", str(audio_path)])
        audio_chain = (
            f"[{audio_idx}:a]afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_start:.1f}:d=1.2,"
            f"loudnorm=I=-15:TP=-1.5:LRA=11[a]"
        )
        cmd.extend(["-filter_complex", f"{video_chain};{audio_chain}", "-map", "[v]", "-map", "[a]"])
    else:
        audio_idx = len(image_paths)
        cmd.extend(["-f", "lavfi", "-t", f"{total_dur:.1f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
        cmd.extend(["-filter_complex", video_chain, "-map", "[v]", "-map", f"{audio_idx}:a"])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_mp4),
        ]
    )
    return cmd


def render_video_from_cards(
    image_paths: list[Path],
    audio_path: Path | None,
    output_mp4: Path,
    audio_offset_sec: float = 16.0,
) -> Path | None:
    """Render a 1080x1350 H.264/AAC MP4 from one or more JPEG cards and an audio track."""
    if not image_paths or not is_ffmpeg_available():
        return None

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if len(image_paths) == 1:
        cmd = _build_single_card_cmd(
            image_path=image_paths[0],
            audio_path=audio_path,
            output_mp4=output_mp4,
            audio_offset_sec=audio_offset_sec,
        )
    else:
        cmd = _build_slideshow_cmd(
            image_paths=image_paths,
            audio_path=audio_path,
            output_mp4=output_mp4,
            audio_offset_sec=audio_offset_sec,
        )

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180)
    if proc.returncode != 0 and audio_path and audio_offset_sec > 0:
        # Retry with offset=0 in case track is shorter than audio_offset_sec
        retry_cmd = (
            _build_single_card_cmd(image_paths[0], audio_path, output_mp4, audio_offset_sec=0.0)
            if len(image_paths) == 1
            else _build_slideshow_cmd(image_paths, audio_path, output_mp4, audio_offset_sec=0.0)
        )
        proc = subprocess.run(retry_cmd, capture_output=True, text=True, check=False, timeout=180)

    if proc.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 20_000:
        return output_mp4
    return None
