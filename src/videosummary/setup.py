"""videosummary-setup: 交互式存储 API Key 到加密 keystore。"""
from __future__ import annotations
import getpass
from pathlib import Path

from videosummary.keystore import Keystore

_KEYSTORE_DIR = Path.home() / ".ghdigest"
_KEYS = {
    "DEEPSEEK_API_KEY": "DeepSeek API Key（用于 AI 整理和总结）",
}


def main() -> None:
    ks = Keystore(_KEYSTORE_DIR)
    print(f"API Key 将加密存储于 {_KEYSTORE_DIR}/keystore.enc\n")
    for key_name, description in _KEYS.items():
        current = ks.load(key_name)
        hint = "（已存储，直接回车跳过）" if current else "（必填）"
        value = getpass.getpass(f"{description} {hint}: ").strip()
        if value:
            ks.store(key_name, value)
            print(f"✓ {key_name} 已保存")
        elif current:
            print(f"  {key_name} 保持不变")
        else:
            print(f"  {key_name} 未设置，跳过")
    print("\n完成。运行 videosummary <URL> 开始使用。")
