"""
config.py
---------
Central configuration for the Movie Splitter pipeline.
Keeping all tunables in one dataclass makes the tool easy to
extend (e.g. add a web UI or CLI flags) without touching core logic.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SplitterConfig:
    # Input / output
    input_path: Path
    output_dir: Path
    clip_duration: int = 60          # seconds per part
    filename_prefix: str = "movie_part"

    # Text overlay styling
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_size: int = 54
    font_color: str = "white"
    box_color: str = "black@0.55"
    box_border: int = 18
    text_template: str = "Part {n}"
    position: str = "bottom"          # "bottom" | "top" | "center"
    margin: int = 60                  # px from edge (for top/bottom)

    # Encoding (quality/speed tradeoff)
    video_codec: str = "libx264"
    crf: int = 18                     # lower = higher quality (18 ~ visually lossless)
    preset: str = "veryfast"          # x264 speed preset
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

    # Performance
    max_workers: int = 4              # parallel ffmpeg processes
    fast_seek: bool = True            # -ss before -i (fast, keyframe-approx)

    # Behavior
    overwrite: bool = False

    def __post_init__(self):
        self.input_path = Path(self.input_path)
        self.output_dir = Path(self.output_dir)
        if self.clip_duration <= 0:
            raise ValueError("clip_duration must be > 0 seconds")
        if self.position not in ("bottom", "top", "center"):
            raise ValueError("position must be 'bottom', 'top', or 'center'")
