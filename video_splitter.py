"""
video_splitter.py
------------------
Core engine: takes a SplitterConfig, computes segment boundaries,
builds the correct ffmpeg command for each part (split + text overlay
in a single pass), and executes them - optionally in parallel.

Design notes:
- Splitting and text overlay happen in ONE ffmpeg call per part (not two
  passes) to avoid double re-encoding, which would degrade quality and
  waste time.
- Video is re-encoded (drawtext requires it) using CRF-based x264, which
  is visually lossless at crf<=18 and much smaller/faster than the
  source's original bitrate would suggest. Audio is stream-copied when
  possible to avoid any audio quality loss or extra processing time.
- Parallelism: each ffmpeg process is single-threaded-ish by default but
  can use multiple cores internally (x264 uses several threads per job).
  Running N jobs concurrently on a multi-core machine is generally the
  fastest configuration; max_workers should be tuned to (cpu_count / 2)
  as a starting point.
"""

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from config import SplitterConfig
from ffmpeg_utils import probe_video, run_ffmpeg, check_ffmpeg_installed

logger = logging.getLogger("movie_splitter")


@dataclass
class Segment:
    index: int          # 1-based part number
    start: float         # seconds
    duration: float      # seconds


class VideoSplitter:
    def __init__(self, cfg: SplitterConfig):
        self.cfg = cfg

    # ---------- Planning ----------

    def plan_segments(self, total_duration: float) -> list[Segment]:
        """Compute start/duration for every part, honoring a shorter last part."""
        n_parts = math.ceil(total_duration / self.cfg.clip_duration)
        segments = []
        for i in range(n_parts):
            start = i * self.cfg.clip_duration
            remaining = total_duration - start
            duration = min(self.cfg.clip_duration, remaining)
            if duration <= 0.05:  # skip negligible trailing sliver
                continue
            segments.append(Segment(index=i + 1, start=start, duration=duration))
        return segments

    # ---------- Command building ----------

    def _drawtext_position(self) -> str:
        """Return x/y expressions for the drawtext filter based on cfg.position."""
        m = self.cfg.margin
        if self.cfg.position == "bottom":
            return f"x=(w-text_w)/2:y=h-text_h-{m}"
        if self.cfg.position == "top":
            return f"x=(w-text_w)/2:y={m}"
        return "x=(w-text_w)/2:y=(h-text_h)/2"  # center

    def _build_command(self, segment: Segment, has_audio: bool) -> list[str]:
        cfg = self.cfg
        text = cfg.text_template.format(n=segment.index)
        # Escape characters ffmpeg's drawtext filter treats specially.
        safe_text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

        drawtext = (
            f"drawtext=fontfile='{cfg.font_path}':text='{safe_text}':"
            f"fontsize={cfg.font_size}:fontcolor={cfg.font_color}:"
            f"box=1:boxcolor={cfg.box_color}:boxborderw={cfg.box_border}:"
            f"{self._drawtext_position()}"
        )

        output_path = cfg.output_dir / f"{cfg.filename_prefix}_{segment.index}.mp4"

        cmd = ["ffmpeg", "-y" if cfg.overwrite else "-n"]

        if cfg.fast_seek:
            # Seek BEFORE -i: fast (keyframe-based seek), ideal for bulk processing.
            cmd += ["-ss", f"{segment.start:.3f}"]

        cmd += ["-i", str(cfg.input_path)]

        if not cfg.fast_seek:
            cmd += ["-ss", f"{segment.start:.3f}"]

        cmd += [
            "-t", f"{segment.duration:.3f}",
            "-vf", drawtext,
            "-c:v", cfg.video_codec,
            "-preset", cfg.preset,
            "-crf", str(cfg.crf),
        ]

        if has_audio:
            cmd += ["-c:a", cfg.audio_codec, "-b:a", cfg.audio_bitrate]
        else:
            cmd += ["-an"]

        cmd += ["-movflags", "+faststart", str(output_path)]
        return cmd

    # ---------- Execution ----------

    def run(self) -> list[Path]:
        check_ffmpeg_installed()
        self.cfg.output_dir.mkdir(parents=True, exist_ok=True)

        meta = probe_video(self.cfg.input_path)
        logger.info(
            "Source: %.1fs, %dx%d, %.2f fps, audio=%s",
            meta["duration"], meta["width"], meta["height"], meta["fps"], meta["has_audio"],
        )

        segments = self.plan_segments(meta["duration"])
        logger.info("Planned %d part(s) at %ds each", len(segments), self.cfg.clip_duration)

        outputs: list[Path] = []
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=self.cfg.max_workers) as pool:
            futures = {
                pool.submit(self._process_segment, seg, meta["has_audio"]): seg
                for seg in segments
            }
            for future in as_completed(futures):
                seg = futures[future]
                try:
                    path = future.result()
                    outputs.append(path)
                    logger.info("✔ Part %d done -> %s", seg.index, path.name)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"Part {seg.index}: {e}")
                    logger.error("✘ Part %d failed: %s", seg.index, e)

        if errors:
            raise RuntimeError(
                f"{len(errors)} of {len(segments)} part(s) failed:\n" + "\n".join(errors)
            )

        outputs.sort(key=lambda p: int(p.stem.split("_")[-1]))
        return outputs

    def _process_segment(self, segment: Segment, has_audio: bool) -> Path:
        cmd = self._build_command(segment, has_audio)
        run_ffmpeg(cmd)
        return self.cfg.output_dir / f"{self.cfg.filename_prefix}_{segment.index}.mp4"
