"""videosummary-compare: 对比同一视频的字幕与多份 transcript。

用法：
    videosummary-compare <URL> [--lang zh|en] [--output FILE]
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

from videosummary.cache import CacheDir, _transcript_key


def _parse_segments(text: str) -> list[tuple[float, str]]:
    """把 '[HH:MM:SS] 或 [MM:SS] text' 格式解析为 (seconds, text) 列表。"""
    segments: list[tuple[float, str]] = []
    for line in text.splitlines():
        # 匹配 [HH:MM:SS] 或 [MM:SS]
        m = re.match(r"\[(?:(\d+):)?(\d{2}):(\d{2})\]\s*(.*)", line.strip())
        if m:
            h_str, mi_str, s_str, text_part = m.groups()
            h = int(h_str) if h_str else 0
            ts = h * 3600 + int(mi_str) * 60 + int(s_str)
            if text_part.strip():
                segments.append((float(ts), text_part.strip()))
    return segments


def _fmt_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _nearest(segments: list[tuple[float, str]], ts: float, window: float = 4.0) -> str:
    """找距离 ts 最近且在 window 秒内的片段。"""
    best: tuple[float, str] | None = None
    best_dist = window + 1
    for seg_ts, seg_text in segments:
        dist = abs(seg_ts - ts)
        if dist < best_dist:
            best_dist = dist
            best = (seg_ts, seg_text)
    return best[1] if best else ""


def build_comparison(url: str, lang: str) -> str:
    cache = CacheDir(url)

    # 收集所有可用版本
    versions: dict[str, list[tuple[float, str]]] = {}

    # 字幕
    sub_path = cache.path / f"subtitle_{lang}.txt"
    if sub_path.exists():
        segs = _parse_segments(sub_path.read_text(encoding="utf-8"))
        if segs:
            versions["字幕（官方）"] = segs

    # 所有 transcript_*.txt
    for p in sorted(cache.path.glob("transcript_*.txt")):
        key = p.stem.replace("transcript_", "")
        # 尝试匹配已知 key
        label = _label_for_key(key, lang)
        segs = _parse_segments(p.read_text(encoding="utf-8"))
        if segs:
            versions[label] = segs

    # 兜底：老格式 transcript.txt
    old = cache.path / "transcript.txt"
    if old.exists() and "transcript.txt" not in [p.name for p in cache.path.glob("transcript_*.txt")]:
        segs = _parse_segments(old.read_text(encoding="utf-8"))
        if segs and "旧版 transcript" not in versions:
            versions["旧版 transcript"] = segs

    if not versions:
        return f"# 对比失败\n\n缓存目录 `{cache.path}` 中没有找到任何 transcript。\n"

    # 以第一个版本的时间戳为主轴
    pivot_name, pivot_segs = next(iter(versions.items()))
    other_names = [n for n in versions if n != pivot_name]

    title = cache.read("title.txt") or url
    lines = [f"# 转录对比：{title}", ""]

    # 表头
    col_names = [pivot_name] + other_names
    header = "| 时间 | " + " | ".join(col_names) + " |"
    sep = "| --- | " + " | ".join(["---"] * len(col_names)) + " |"
    lines += [header, sep]

    for ts, text in pivot_segs:
        row_cells = [text]
        for name in other_names:
            row_cells.append(_nearest(versions[name], ts))
        # 转义 | 防止破坏 markdown 表格
        row_cells = [c.replace("|", "｜") for c in row_cells]
        lines.append(f"| {_fmt_ts(ts)} | " + " | ".join(row_cells) + " |")

    lines += ["", f"*缓存路径：`{cache.path}`*"]
    return "\n".join(lines)


def _label_for_key(key: str, lang: str) -> str:
    for model in ["tiny", "base", "small", "medium", "large-v3"]:
        for vad in [True, False]:
            if _transcript_key(model, lang, vad) == key:
                vad_str = "VAD开" if vad else "VAD关"
                return f"whisper-{model} {vad_str}"
    return f"transcript ({key})"


def main() -> None:
    parser = argparse.ArgumentParser(prog="videosummary-compare",
                                     description="对比同一视频的字幕与多份 transcript")
    parser.add_argument("url")
    parser.add_argument("--lang", default=None, choices=["zh", "en"])
    parser.add_argument("--output", default=None, metavar="FILE")
    args = parser.parse_args()

    if args.lang is None:
        args.lang = "zh" if ("bilibili.com" in args.url or "b23.tv" in args.url) else "en"

    md = build_comparison(args.url, args.lang)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"✓ 已保存：{args.output}")
    else:
        print(md)
