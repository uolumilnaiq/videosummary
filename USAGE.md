# videosummary 使用手册

YouTube / Bilibili 视频或本地音频文件转文字稿 + AI 整理 + AI 总结工具集。

**平台支持**：完整流程仅支持 Apple Silicon Mac 上的 macOS。纯字幕路径可能在其他系统运行，但未作为受支持平台验证。

---

## 安装

```bash
cd videosummary
uv pip install -e .
# macOS Apple Silicon 需额外安装转录引擎
uv pip install -e ".[macos]"
```

**系统依赖**：需要 `ffmpeg` 和 `ffprobe`（`brew install ffmpeg`）。

**首次配置 API Key**（加密存储，无需环境变量）：
```bash
videosummary-setup
```

---

## 命令一览

| 命令 | 用途 |
|------|------|
| `videosummary` | 转录视频/音频，AI 整理 + AI 总结 |
| `videosummary-setup` | 首次配置 DeepSeek API Key（加密存储） |
| `videosummary-update` | 下载或更新 Whisper 模型权重（需联网） |
| `videosummary-compare` | 对比同一视频的多份文字稿 |
| `videosummary-clear` | 清理指定视频的缓存 |

---

## videosummary

转录 YouTube / Bilibili 视频或本地音频文件，依次执行：转录 → AI 整理 → AI 总结，输出 Markdown 文件。

```
videosummary <URL|文件路径> [选项]
```

### 输出结构

每次运行生成两个文件：

| 文件 | 内容 | `--redo-ai` 时 |
|------|------|--------------|
| `{标题}.md` | AI 总结 + 整理后文字稿 | 重新生成 |
| `{标题}_transcript.md` | 原始带时间戳文字稿 | 保持不变 |

**`{标题}.md` 包含：**
1. **AI 总结**：核心摘要 + 关键要点（含时间戳）+ 一句话结论
2. **整理后文字稿**：去噪、断句修正、语义分段、翻译为简体中文的完整文章

**`--no-clean` 时**：只生成 `_transcript.md`，不生成 AI 文件。

### 选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--output DIR` | `./output` | 输出目录 |
| `--stdout` | 否 | 输出到终端而非文件 |
| `--lang zh\|en` | 自动推断 | 转录语言（bilibili→zh，其他→en） |
| `--model` | `medium` | Whisper 模型：`tiny` `base` `small` `medium` `large-v3` |
| `--no-clean` | 否 | 跳过 AI 整理和总结，仅输出原始文字稿 |
| `--no-summary` | 否 | 执行 AI 整理但跳过总结 |
| `--no-vad` | 否 | 禁用 VAD 语音活动检测预处理 |
| `--initial-prompt TEXT` | 空 | 追加到 Whisper 初始提示的额外文本 |
| `--redo-ai` | 否 | 仅跳过整理/总结缓存重新生成，**转录缓存不受影响** |
| `--no-cache` | 否 | 跳过文字稿/整理稿/总结缓存全部重新生成（音频和字幕仍复用） |
| `--clear-cache` | 否 | 清空该输入的全部缓存后退出 |
| `--cookies-from-browser` | `chrome` | 从浏览器读取 Cookie：`chrome` `firefox` `safari` `edge` |
| `--cookies FILE` | 无 | Netscape 格式 cookies.txt 文件路径 |
| `--part N` | 无 | 多 P 视频：处理第 N P |
| `--all-parts` | 否 | 多 P 视频：处理全部 P |
| `-y / --yes` | 否 | 非交互模式，多 P 时默认取第 1 P |

### 示例

```bash
# YouTube（默认英文，转录 + 整理 + 总结）
videosummary https://www.youtube.com/watch?v=xxxxx

# Bilibili（自动中文，跳过总结）
videosummary https://www.bilibili.com/video/BVxxxxx --no-summary

# 本地音频文件
videosummary /path/to/audio.mp3
videosummary ./recording.m4a --lang zh --no-summary
videosummary ~/Downloads/meeting.mp3 --model large-v3 --no-vad

# 仅转录，不调用 AI
videosummary <URL> --no-clean

# 重新整理和总结（不重新转录）
videosummary <URL> --no-cache

# 用大模型转录，输出到指定目录
videosummary <URL> --model large-v3 --output ~/Desktop/transcripts

# Bilibili / YouTube 需要登录（默认使用 Chrome Cookie）
videosummary <URL> --cookies-from-browser chrome
```

### 缓存机制

| 文件 | 缓存 key | 说明 |
|------|----------|------|
| `audio.mp3` | URL | 下载一次永久复用 |
| `subtitle_<lang>.txt` | URL + 语言 | 有官方字幕时优先使用，跳过转录 |
| `transcript_<hash>.txt` | URL + model + lang + vad | 参数不同分别缓存 |
| `cleaned_<hash>.txt` | URL + model + lang + vad | AI 整理结果 |
| `summary.md` | URL | AI 总结结果 |

缓存位置：`~/.cache/videosummary/<url-hash>/`

---

## videosummary-setup

首次使用前运行，将 DeepSeek API Key 加密存储到本地（`~/.ghdigest/keystore.enc`）。

```bash
videosummary-setup
```

与 `findsomegithubcode` 共用同一加密存储，Key 只需配置一次。

---

## videosummary-update

下载或更新 Whisper 模型权重（需联网）。日常转录完全离线运行，不再自动检查更新。

```bash
videosummary-update                   # 更新 medium（默认）
videosummary-update --model large-v3  # 更新指定模型
videosummary-update --all             # 更新全部模型
```

| 模型 | 说明 |
|------|------|
| `tiny` | 最快，准确率低，适合测试 |
| `base` | 快速粗转录 |
| `small` | 均衡 |
| `medium` | **默认**，中文效果好 |
| `large-v3` | 最准，速度最慢 |

---

## videosummary-compare

对比同一视频的字幕与多份文字稿，输出时间戳对齐的 Markdown 对照表。

```
videosummary-compare <URL> [选项]
```

### 选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--lang zh\|en` | 自动推断 | 字幕语言 |
| `--output FILE` | 标准输出 | 保存对照表到文件 |

### 示例

```bash
videosummary-compare <URL> --output compare.md
```

---

## videosummary-clear

清理指定视频或本地文件的缓存。

```
videosummary-clear <URL|文件路径> --transcript | --all
```

### 选项

| 选项 | 说明 |
|------|------|
| `--transcript` | 仅清理文字稿、整理稿、总结，**保留音频和字幕** |
| `--all` | 清理全部缓存 |

### 示例

```bash
# 重新整理和总结（保留已下载音频和转录）
videosummary-clear <URL> --transcript
videosummary <URL>

# 完全清空重来
videosummary-clear <URL> --all
videosummary <URL>
```

---

## 技术实现

### 整体架构

```
输入（URL / 本地文件）
    │
    ▼
[main.py] 入口与流程编排
    ├─ 本地文件 → _process_local()
    └─ 网络 URL → process_video()
           │
           ├─ yt-dlp          字幕检测 → subtitle.py（SRT/VTT 解析 + 质量探测）
           │                  音频下载 → audio.mp3（bestaudio + FFmpegExtractAudio）
           │
           ├─ transcriber.py  语音转文字
           │     ├─ VAD 路径（默认）
           │     │    ├─ silero-vad 检测所有语音段
           │     │    ├─ 合并间隔 <0.3s 的相邻段
           │     │    ├─ 按 10min 分桶 → 每桶一次 ffmpeg concat（inpoint/outpoint）
           │     │    │    → chunk_000.mp3, chunk_001.mp3, ...（无静音）
           │     │    │    offset_map: [(concat_start, orig_start, duration), ...]
           │     │    └─ mlx-whisper 串行转录每个 chunk
           │     ├─ 非 VAD 路径（--no-vad）
           │     │    └─ 超过 10min → ffmpeg 按时间分段 → mlx-whisper 串行转录
           │     └─ 时间戳重映射（chunk 内时间 → 原始视频时间）
           │
           ├─ summarizer.py   AI 处理（DeepSeek API）
           │     ├─ clean()   整理文字稿（去噪/断句/分段/中文翻译）
           │     └─ summarize()  生成总结
           │           ├─ 短文本（<600k tokens）→ 单次调用
           │           └─ 长文本 → Map-Reduce（并发 map + 递归 reduce）
           │
           └─ cache.py        缓存管理（~/.cache/videosummary/<url-hash>/）
```

### 核心组件

| 模块 | 职责 | 关键技术 |
|------|------|---------|
| `transcriber.py` | 语音转文字 | silero-vad + mlx-whisper + ffmpeg |
| `summarizer.py` | AI 整理 + 总结 | DeepSeek API (deepseek-chat) + httpx + Map-Reduce |
| `cache.py` | 缓存读写 | SHA256 签名 + 原子写入 |
| `config.py` + `keystore.py` | API Key 管理 | Fernet 对称加密（cryptography 库） |
| `subtitle.py` | 字幕解析 | SRT/VTT → 带时间戳文字稿 |
| `tokens.py` | Token 计算 | tiktoken（cl100k_base） |
| `main.py` | 流程编排 + CLI | asyncio + argparse + tqdm |

### 关键依赖

| 库 | 版本要求 | 用途 |
|----|---------|------|
| `yt-dlp` | ≥2024.1.1 | 视频/音频下载、字幕提取、Cookie 支持 |
| `mlx-whisper` | ≥0.3.0（macOS only） | Apple Silicon 本地语音识别 |
| `silero-vad` | — | 语音活动检测，过滤静音段 |
| `httpx` | ≥0.27.0 | 异步 HTTP 调用 DeepSeek API |
| `tiktoken` | ≥0.7.0 | token 数量估算（Map-Reduce 分块依据） |
| `cryptography` | ≥42.0.0 | Fernet 加密存储 API Key |
| `tqdm` | ≥4.66.0 | 下载/VAD/转录进度条 |
| `ffmpeg` / `ffprobe` | 系统依赖 | 音频格式转换、分段、时长探测 |

### VAD 时间戳映射

VAD 路径中，每个 chunk 是多段原始语音拼接而成（静音已去除），Whisper 输出的时间戳是 **chunk 内部**的时间，需要通过 `offset_map` 还原为**原始视频**时间：

```
offset_map 每项：(concat_start, orig_start, duration)
_remap_timestamp(ts) → 在 offset_map 中找到所属区间 → orig_start + (ts - concat_start)
```

每个 chunk 独立持有自己的 offset_map，分块之间时间戳互不干扰。

### 缓存控制策略

| 参数 | 转录缓存 | 整理缓存 | 总结缓存 | 音频/字幕 |
|------|---------|---------|---------|---------|
| 无（默认） | 命中则复用 | 命中则复用 | 命中则复用 | 命中则复用 |
| `--redo-ai` | 命中则复用 ✓ | 强制重跑 | 强制重跑 | 命中则复用 |
| `--no-cache` | 强制重跑 | 强制重跑 | 强制重跑 | 命中则复用 |

### AI 流水线

```
原始文字稿
    │
    ▼
clean()   _CLEAN_PROMPT  去噪/断句/分段/中文翻译（信达雅）
    │
    ├─ token 计算：tiktoken cl100k_base 估算
    │     注意：DeepSeek tokenizer 对中文的计数约为 cl100k 的 2 倍
    │     因此分块阈值以 cl100k 为单位时需留出足够余量
    │
    ├─ tokens ≤ 60k  → 单次调用
    └─ tokens > 60k  → split_by_tokens(max=60k, overlap=0, trim_to_sentence=False)
            │  按 token 边界直切，不做句尾对齐（避免递归级联问题）
            │  每块 cl100k 60k tokens ≈ DeepSeek 120k tokens
            │  输出上限 131,072 tokens，留 ~11k 余量
            └─ 顺序调用 API，结果拼接（"\n\n" 分隔）
    │
    ▼
整理后文字稿
    │
    ▼
summarize()
    ├─ tokens < 600k → 单次 _SINGLE_PROMPT
    └─ tokens ≥ 600k → Map-Reduce
            ├─ split_by_tokens(200k, overlap=1000) → N 个 chunk
            ├─ 并发（Semaphore=5）map 每个 chunk → _MAP_PROMPT
            └─ reduce → _REDUCE_PROMPT（token 仍超 200k 则递归，最多 3 层）
```

**为什么 clean() 不用 trim_to_sentence？**

`split_by_tokens` 默认会在每块末尾寻找句号/换行符对齐，确保切割位置在句尾。但这会导致每块末尾剩余少量内容（tail）：tail 的 token 数 < overlap 时，`start` 不前进，形成微小步长，产生数千个 1-token 的碎块（级联 bug）。clean() 的输入是带时间戳的短行文字稿，不依赖语义边界，因此关闭 trim_to_sentence，按 token 边界直切即可。

### API Key 存储

API Key 通过 Fernet 对称加密存储在 `~/.ghdigest/keystore.enc`，主密钥在 `~/.ghdigest/master.key`（本地生成，不上传）。与 `findsomegithubcode` 共用同一存储，同一台机器只需配置一次。

---

## 常见场景

### 对比不同模型转录效果

```bash
videosummary <URL> --no-clean --model medium
videosummary <URL> --no-clean --model large-v3
videosummary-compare <URL> --output compare.md
```

### 只要整理后的文章，不要总结

```bash
videosummary <URL> --no-summary
```

### 转录已完成，只重跑 AI 整理和总结（网络恢复后）

```bash
videosummary /path/to/audio.mp3 --redo-ai
```

### 本地录音文件处理

```bash
videosummary ~/recordings/meeting.mp3 --lang zh
```

### Bilibili 需要登录

```bash
# 先在 Chrome 登录 Bilibili，再运行（默认已使用 Chrome Cookie）
videosummary https://www.bilibili.com/video/BVxxxxx
```
