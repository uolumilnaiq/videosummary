import re
from videosummary.tokens import format_timestamp

_SRT_BLOCK = re.compile(
    r"\d+\n(\d{2}:\d{2}:\d{2})[,.](\d{3}) --> (\d{2}:\d{2}:\d{2})[,.](\d{3})\n(.*?)(?=\n\n|\Z)",
    re.DOTALL,
)


def _parse_time(hms: str, ms: str) -> float:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _count_chars(srt: str) -> int:
    return sum(len(m.group(5).strip()) for m in _SRT_BLOCK.finditer(srt))


def _segment_count(srt: str) -> int:
    return len(_SRT_BLOCK.findall(srt))


def _detect_language_mismatch(srt: str, lang: str) -> bool:
    """返回 True 表示语言不匹配（应回退 whisper）"""
    if lang != "zh":
        return False  # 目前只检测 zh 的不一致
    all_text = " ".join(m.group(5).strip() for m in _SRT_BLOCK.finditer(srt))
    if not all_text:
        return False
    ascii_letters = sum(1 for c in all_text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in all_text if c.isalpha())
    if total_letters == 0:
        return False
    ascii_ratio = ascii_letters / total_letters
    return ascii_ratio > 0.5


def passes_quality_probe(srt: str, lang: str, duration_seconds: float) -> bool:
    if duration_seconds <= 0:
        return False
    seg_count = _segment_count(srt)
    density = seg_count / (duration_seconds / 60)
    if density < 1:
        return False
    if _count_chars(srt) < 100:
        return False
    if _detect_language_mismatch(srt, lang):
        return False
    return True


def parse_subtitle_to_transcript(srt: str) -> str:
    lines = []
    for m in _SRT_BLOCK.finditer(srt):
        start_sec = _parse_time(m.group(1), m.group(2))
        text = m.group(5).strip().replace("\n", " ")
        lines.append(f"[{format_timestamp(start_sec)}] {text}")
    return "\n".join(lines)
