# VideoSummary

[English](README.md) · [详细使用手册](USAGE.md)

VideoSummary 是一个 Python 命令行工具，可将 YouTube、Bilibili 视频或本地音频转换为带时间戳的文字稿，并可调用 DeepSeek 整理文字稿、生成总结。工具优先使用可用字幕；没有合适字幕时，使用本地 `mlx-whisper` 转录。目前音频转录需要 Apple Silicon Mac。

## 环境要求

- Python 3.11 或更新版本，以及 [uv](https://docs.astral.sh/uv/)。
- `PATH` 中可用的 `ffmpeg` 和 `ffprobe`；macOS 可运行 `brew install ffmpeg`。
- 音频转录需要 Apple Silicon；下载 Whisper 权重和处理视频链接需要网络。
- AI 整理及总结需要 DeepSeek API Key；仅转录不需要。

## 安装与配置

```bash
git clone <你的仓库地址>
cd videosummary
uv sync --extra macos
uv run videosummary-update --model medium
uv run videosummary-setup
```

`videosummary-update` 下载默认 Whisper 模型。`videosummary-setup` 将 API Key 保存在本机 `~/.ghdigest/`；也可设置环境变量 `DEEPSEEK_API_KEY`。只使用 `--no-clean` 时，可以跳过 Key 配置。

## 使用示例

```bash
# 本地音频：只生成文字稿，不请求 DeepSeek
uv run videosummary ./recording.m4a --no-clean

# 视频链接：生成文字稿、整理稿和总结
uv run videosummary 'https://www.youtube.com/watch?v=VIDEO_ID'

# Bilibili：整理文字稿，但跳过总结
uv run videosummary 'https://www.bilibili.com/video/BV_VIDEO_ID' --no-summary
```

默认输出目录是 `output/`：`<标题>_transcript.md` 保存带时间戳的原始文字稿；开启 AI 处理时，`<标题>.md` 保存整理稿和总结。生成结果、下载数据、浏览器 Cookie 与 API Key 不应提交到 Git。开启 AI 处理时，文字稿内容会发送给 DeepSeek；请仅处理有权使用的媒体。

浏览器 Cookie、多 P 视频、模型选择、缓存控制，以及 `videosummary-compare`、`videosummary-clear` 等命令详见 [USAGE.md](USAGE.md)。

## 开发

```bash
uv sync --extra dev --extra macos
uv run --extra dev pytest -q
uv run ruff check src tests
uv build
```

源码位于 `src/videosummary/`，单元测试位于 `tests/`。贡献说明见 [AGENTS.md](AGENTS.md)。
