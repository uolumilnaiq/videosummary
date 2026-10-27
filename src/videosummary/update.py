"""videosummary-update：从 HuggingFace 拉取最新 Whisper 模型权重。"""
from __future__ import annotations
import argparse
import sys


_MODELS = ["tiny", "base", "small", "medium", "large-v3"]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="videosummary-update",
        description="下载或更新 mlx-whisper 模型权重（需要联网）",
    )
    parser.add_argument(
        "--model", choices=_MODELS, default="medium",
        help="要更新的模型（默认 medium）",
    )
    parser.add_argument(
        "--all", action="store_true", dest="all_models",
        help="更新全部模型",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[错误] huggingface_hub 未安装", file=sys.stderr)
        sys.exit(1)

    models = _MODELS if args.all_models else [args.model]
    for model in models:
        repo = f"mlx-community/whisper-{model}-mlx"
        print(f"[更新] {repo} …")
        try:
            path = snapshot_download(repo_id=repo)
            print(f"  ✓ 已保存：{path}")
        except Exception as e:
            print(f"  ✗ 失败：{e}", file=sys.stderr)
            sys.exit(1)
