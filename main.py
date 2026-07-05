import argparse
import logging
import sys
import time
from pathlib import Path

from config import SplitterConfig
from video_splitter import VideoSplitter
from ffmpeg_utils import FFmpegNotFoundError, FFmpegExecutionError


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Split a movie into numbered, text-overlaid short clips."
    )
    p.add_argument("--input", "-i", required=True, help="Path to the source movie file")
    p.add_argument("--output", "-o", default="./output", help="Output directory")
    p.add_argument("--duration", "-d", type=int, default=60, help="Seconds per part")
    p.add_argument("--prefix", default="movie_part", help="Output filename prefix")
    p.add_argument("--text-template", default="Part {n}",
                    help="Overlay text template, {n} = part number")
    p.add_argument("--position", choices=["top", "bottom", "center"], default="bottom")
    p.add_argument("--font-size", type=int, default=54)
    p.add_argument("--crf", type=int, default=18, help="Lower = higher quality (18-23 typical)")
    p.add_argument("--preset", default="veryfast",
                    choices=["ultrafast", "superfast", "veryfast", "faster",
                             "fast", "medium", "slow", "slower", "veryslow"])
    p.add_argument("--workers", type=int, default=4, help="Parallel ffmpeg jobs")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("movie_splitter")

    cfg = SplitterConfig(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        clip_duration=args.duration,
        filename_prefix=args.prefix,
        text_template=args.text_template,
        position=args.position,
        font_size=args.font_size,
        crf=args.crf,
        preset=args.preset,
        max_workers=args.workers,
        overwrite=args.overwrite,
    )

    if not cfg.input_path.exists():
        logger.error("Input file not found: %s", cfg.input_path)
        return 1

    splitter = VideoSplitter(cfg)

    start = time.time()
    try:
        outputs = splitter.run()
    except (FFmpegNotFoundError, FFmpegExecutionError, RuntimeError) as e:
        logger.error(str(e))
        return 1

    elapsed = time.time() - start
    logger.info(
        "Done: %d file(s) written to %s in %.1fs", len(outputs), cfg.output_dir, elapsed
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
