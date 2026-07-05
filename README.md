# Movie Splitter — Auto "Part N" Clip Generator

Splits a full movie into sequential, numbered short clips (Instagram-recap
style), overlaying "Part 1", "Part 2", ... on each, while preserving video
and audio quality.

## Why FFmpeg directly (not MoviePy)

| | MoviePy | Direct FFmpeg (this project) |
|---|---|---|
| Splitting | Decodes/re-encodes via Python, slow on long movies | Fast keyframe-based seeking |
| Text overlay | Re-encodes via Python frame loop | Single-pass `drawtext` filter, hardware-friendly |
| Audio | Often re-encoded, extra quality loss | Copied 1:1 when no re-mux needed, or re-encoded once at high bitrate |
| Speed on a 2hr movie / 60s parts (~120 clips) | Can take hours | Minutes, especially with parallel workers |

MoviePy is great for short, code-driven creative edits. For bulk-splitting
a full-length movie into 50+ parts, orchestrating FFmpeg directly from
Python gives you production-grade speed and quality control.

## Architecture

```
movie_splitter/
├── config.py           # SplitterConfig dataclass — every tunable in one place
├── ffmpeg_utils.py      # ffprobe/ffmpeg subprocess wrappers, error handling
├── video_splitter.py    # Core engine: plans segments, builds ffmpeg commands, runs them (parallel)
├── main.py              # CLI entry point (argparse)
├── requirements.txt
└── README.md
```

**Flow:**
1. `ffprobe` reads the movie's duration, resolution, fps, and whether it has audio.
2. `VideoSplitter.plan_segments()` computes `(start, duration)` for every part —
   the last part is automatically shorter if the movie doesn't divide evenly.
3. For each segment, one FFmpeg command does **both** the split and the text
   overlay in a single re-encode pass (avoids double-compression quality loss).
4. Jobs run concurrently via `ThreadPoolExecutor` (FFmpeg subprocesses release
   the GIL, so this parallelizes real CPU work across cores).
5. Outputs are named `movie_part_1.mp4`, `movie_part_2.mp4`, ... in your chosen
   output folder.

## Quality & Speed Choices

- **Video**: re-encoded with `libx264`, `-crf 18` (visually lossless — indistinguishable
  from source in blind tests) and `-preset veryfast` (good speed/size balance).
  Use `--preset slower --crf 16` if you want maximum quality and have time to spare,
  or `--preset ultrafast` for max throughput on a quick draft pass.
- **Audio**: re-encoded to AAC 192kbps by default (very high fidelity for social
  media use). If your source audio is already AAC and you want zero audio
  re-encoding, you can change `-c:a aac` to `-c:a copy` in `video_splitter.py`
  (only works if segment boundaries align with the audio's own keyframes,
  which usually isn't guaranteed for arbitrary cut points — hence AAC by default).
- **Seeking**: `-ss` is placed *before* `-i` (fast/keyframe seek). This is ~10-50x
  faster than seeking after `-i` and is the standard approach for bulk splitting.
  Because we always re-encode the segment anyway (for the text overlay), any
  minor keyframe-seek imprecision is corrected during encoding — you still get
  frame-accurate cut points in the output.
- **Parallelism**: `--workers N` runs N FFmpeg processes concurrently. Start
  with `N = cpu_count / 2` and tune upward/downward based on your machine's
  cores and disk I/O.

## Installation

```bash
# 1. Install FFmpeg (includes ffprobe)
# Ubuntu/Debian:
sudo apt update && sudo apt install -y ffmpeg

# macOS:
brew install ffmpeg

# Windows: download from https://ffmpeg.org/download.html and add to PATH

# 2. Clone/copy this project, then (optional) create a virtualenv
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. No third-party Python packages required (see requirements.txt)
```

## Usage

Basic:
```bash
python main.py --input movie.mp4 --output ./output --duration 60
```

All options:
```bash
python main.py \
  --input movie.mp4 \
  --output ./output \
  --duration 90 \
  --prefix movie_part \
  --text-template "Part {n}" \
  --position bottom \
  --font-size 54 \
  --crf 18 \
  --preset veryfast \
  --workers 4 \
  --overwrite \
  --verbose
```

| Flag | Default | Description |
|---|---|---|
| `--input / -i` | required | Path to source movie |
| `--output / -o` | `./output` | Output folder |
| `--duration / -d` | 60 | Seconds per part |
| `--prefix` | `movie_part` | Output filename prefix → `prefix_1.mp4`, `prefix_2.mp4`, ... |
| `--text-template` | `Part {n}` | Overlay text, `{n}` = part number |
| `--position` | `bottom` | `top`, `bottom`, or `center` |
| `--font-size` | 54 | Overlay font size |
| `--crf` | 18 | Lower = higher quality/larger file (typical range 16-23) |
| `--preset` | `veryfast` | x264 speed preset (`ultrafast`...`veryslow`) |
| `--workers` | 4 | Parallel FFmpeg jobs |
| `--overwrite` | off | Overwrite existing output files |
| `--verbose / -v` | off | Debug logging |

## Example Output

```
14:53:12 [INFO] Source: 200.0s, 640x360, 30.00 fps, audio=True
14:53:12 [INFO] Planned 4 part(s) at 60s each
14:53:24 [INFO] ✔ Part 4 done -> movie_part_4.mp4
14:53:39 [INFO] ✔ Part 1 done -> movie_part_1.mp4
14:53:39 [INFO] ✔ Part 3 done -> movie_part_3.mp4
14:53:40 [INFO] ✔ Part 2 done -> movie_part_2.mp4
14:53:40 [INFO] Done: 4 file(s) written to output in 27.7s
```

output/
├── movie_part_1.mp4  (60s, "Part 1" overlay)
├── movie_part_2.mp4  (60s, "Part 2" overlay)
├── movie_part_3.mp4  (60s, "Part 3" overlay)
└── movie_part_4.mp4  (20s, "Part 4" overlay — last part auto-shortened)

## Extending This

- **Vertical/9:16 cropping for Reels/Shorts**: add a `crop`/`scale` filter
  before `drawtext` in `_build_command()` (e.g. `crop=ih*9/16:ih`).
- **Custom fonts/branding**: point `--font-size`/`config.font_path` at your
  own `.ttf`, or add a logo overlay via a second `-i` + `overlay` filter.
- **Batch multiple movies**: loop this CLI over a folder of files, or wrap
  `VideoSplitter` in a small FastAPI service for a web-based tool.
- **GPU acceleration**: swap `-c:v libx264` for `-c:v h264_nvenc` (NVIDIA) or
  `h264_videotoolbox` (Mac) in `video_splitter.py` if you have compatible
  hardware — this can cut encode time significantly for very long movies.

## Legal Note

Only use this on content you own the rights to, or have explicit permission/
license to re-edit and redistribute (e.g. your own footage, licensed stock
content, or material under an open license). Splitting and reposting
copyrighted movies without authorization is a common source of takedowns
and account bans on social platforms, independent of this tool.
