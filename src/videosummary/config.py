import os
from pathlib import Path

from videosummary.errors import SummarizeError
from videosummary.keystore import Keystore

_KEY_NAME = "DEEPSEEK_API_KEY"
_KEYSTORE_DIR = Path.home() / ".ghdigest"


def get_api_key() -> str:
    # 优先从加密 keystore 读取，降级到环境变量
    ks = Keystore(_KEYSTORE_DIR)
    value = ks.load(_KEY_NAME) or os.environ.get(_KEY_NAME)
    if not value:
        raise SummarizeError(
            f"{_KEY_NAME} 未配置。请运行 videosummary-setup 存储 API Key。"
        )
    return value
