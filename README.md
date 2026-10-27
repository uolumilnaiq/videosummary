# VideoSummary

[简体中文](README.zh-CN.md) · [Detailed usage](USAGE.md)

VideoSummary is a Python command-line tool that turns YouTube and Bilibili videos, or local audio files, into timestamped transcripts and optional DeepSeek-generated notes. It uses available subtitles first and falls back to local `mlx-whisper` transcription. **The complete workflow is supported only on macOS with Apple Silicon.** Subtitle-only paths may run elsewhere, but other platforms are not supported or tested.

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
- `ffmpeg` and `ffprobe` on `PATH` (`brew install ffmpeg` on macOS).
- macOS on Apple Silicon for supported use; an internet connection to download Whisper weights and process video URLs.
- A DeepSeek API key for transcript cleanup and summaries. Transcription alone works without one.

## Install and configure

```bash
git clone https://github.com/uolumilnaiq/videosummary.git
cd videosummary
uv sync --extra macos
uv run videosummary-update --model medium
uv run videosummary-setup
```

`videosummary-update` downloads the default Whisper model once. `videosummary-setup` stores the API key locally in `~/.ghdigest/`; alternatively set `DEEPSEEK_API_KEY` in your environment. Skip the last step when using `--no-clean`.

## Use

```bash
# Local audio: transcript only, no DeepSeek request
uv run videosummary ./recording.m4a --no-clean

# Video URL: transcript, cleaned text, and summary
uv run videosummary 'https://www.youtube.com/watch?v=VIDEO_ID'

# Bilibili video: cleanup without a summary
uv run videosummary 'https://www.bilibili.com/video/BV_VIDEO_ID' --no-summary
```

The default `output/` directory contains `<title>_transcript.md` with timestamps and, when AI processing is enabled, `<title>.md` with cleaned text and a summary. Generated output, downloaded data, browser cookies, and API keys are excluded from Git. When AI processing is enabled, transcript text is sent to DeepSeek. Use only media that you are permitted to process.

For browser cookies, multi-part videos, model choices, cache controls, and the `videosummary-compare` / `videosummary-clear` commands, see [USAGE.md](USAGE.md).

## Develop

```bash
uv sync --extra dev --extra macos
uv run --extra dev pytest -q
uv run ruff check src tests
uv build
```

Source code is in `src/videosummary/`; unit tests are in `tests/`. See [AGENTS.md](AGENTS.md) for contribution guidance.

## License

MIT. See [LICENSE](LICENSE).
