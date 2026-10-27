class FetchError(Exception):
    """yt-dlp 下载失败：私密/区域锁/已删除/反爬"""

class TranscribeError(Exception):
    """mlx-whisper 转录失败：OOM / 模型加载失败"""

class SummarizeError(Exception):
    """DeepSeek API 失败：429 / 超时 / 鉴权"""
