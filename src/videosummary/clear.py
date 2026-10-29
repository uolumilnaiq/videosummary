"""videosummary-clear: 清理指定视频的缓存。

用法：
    videosummary-clear <URL> [--transcript] [--all]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from videosummary.cache import CacheDir, cache_source


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="videosummary-clear",
        description="清理指定视频的缓存文件",
    )
    parser.add_argument("url", help="视频 URL")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--transcript", action="store_true",
        help="仅清理文字稿（transcript_*.txt）和参数化总结（summary_*.md），保留音频和字幕",
    )
    group.add_argument(
        "--all", action="store_true",
        help="清理全部缓存（音频 + 字幕 + 文字稿 + 总结），等同于删除整个缓存目录",
    )
    args = parser.parse_args()

    if not args.transcript and not args.all:
        parser.print_help()
        print("\n请指定 --transcript 或 --all", file=sys.stderr)
        sys.exit(1)

    cache = CacheDir(cache_source(args.url))
    if not cache.path.exists():
        print(f"缓存目录不存在：{cache.path}")
        return

    if args.all:
        import shutil
        shutil.rmtree(cache.path)
        print(f"✓ 已清理全部缓存：{cache.path}")
        return

    # --transcript：只删文字稿和总结，保留音频和字幕
    removed: list[Path] = []
    for pattern in ("transcript_*.txt", "summary_*.md", "summary.md", "meta.json"):
        for f in cache.path.glob(pattern):
            f.unlink()
            removed.append(f)

    if removed:
        for f in removed:
            print(f"  删除：{f.name}")
        print(f"✓ 已清理 {len(removed)} 个文件（保留音频和字幕）")
    else:
        print("无可清理的文字稿缓存")
