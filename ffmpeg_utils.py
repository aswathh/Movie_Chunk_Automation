"""
ffmpeg_utils.py
---------------
Thin, dependency-free wrappers around the ffmpeg / ffprobe CLI tools.
We shell out directly instead of using a Python binding (e.g. ffmpeg-python)
to keep full control over performance flags and avoid an extra abstraction
layer that can hide errors.
"""

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegNotFoundError(RuntimeError):
    pass


class FFmpegExecutionError(RuntimeError):
    pass


def check_ffmpeg_installed() -> None:
    """Fail fast with a clear message if ffmpeg/ffprobe aren't on PATH."""
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise FFmpegNotFoundError(
                f"'{binary}' not found on PATH. Install FFmpeg first "
                f"(see README installation steps)."
            )


def probe_video(path: Path) -> dict:
    """
    Return key metadata about the input video: duration (s), width, height,
    fps, has_audio. Raises FFmpegExecutionError on failure (e.g. corrupt file).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegExecutionError(f"ffprobe failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise FFmpegExecutionError("No video stream found in input file.")

    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    if duration <= 0:
        raise FFmpegExecutionError("Could not determine video duration.")

    # fps may be like "30000/1001"
    fps_raw = video_stream.get("r_frame_rate", "0/1")
    num, _, den = fps_raw.partition("/")
    fps = round(float(num) / float(den), 2) if den and float(den) != 0 else 0.0

    return {
        "duration": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "has_audio": audio_stream is not None,
    }


def run_ffmpeg(cmd: list) -> None:
    """Execute an ffmpeg command, raising with captured stderr on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegExecutionError(
            f"ffmpeg command failed (exit {result.returncode}):\n"
            f"{' '.join(cmd)}\n--- stderr ---\n{result.stderr[-2000:]}"
        )
