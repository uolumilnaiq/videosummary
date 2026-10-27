from videosummary.subtitle import passes_quality_probe, parse_subtitle_to_transcript

def _make_srt(segments: list[tuple[str, str, str]]) -> str:
    lines = []
    for i, (start, end, text) in enumerate(segments, 1):
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)

def test_probe_passes_dense_subtitle():
    segs = [(f"00:{i:02d}:00,000", f"00:{i:02d}:10,000", "这是一段正常字幕内容测试文字。")
            for i in range(10)]
    srt = _make_srt(segs)
    assert passes_quality_probe(srt, lang="zh", duration_seconds=600)

def test_probe_fails_too_sparse():
    segs = [(f"00:{i*5:02d}:00,000", f"00:{i*5:02d}:10,000", "内容。") for i in range(3)]
    srt = _make_srt(segs)
    assert not passes_quality_probe(srt, lang="zh", duration_seconds=900)

def test_probe_fails_too_short():
    segs = [("00:00:00,000", "00:00:05,000", "短。")]
    srt = _make_srt(segs)
    assert not passes_quality_probe(srt, lang="zh", duration_seconds=60)

def test_probe_fails_language_mismatch():
    """字幕语言与 --lang 不一致时探针失败"""
    segs = [(f"00:{i:02d}:00,000", f"00:{i:02d}:10,000",
             "This is a valid English subtitle segment with enough words.")
            for i in range(10)]
    srt = _make_srt(segs)
    assert not passes_quality_probe(srt, lang="zh", duration_seconds=600)

def test_parse_subtitle_to_transcript():
    segs = [
        ("00:00:00,000", "00:00:05,000", "大家好欢迎来到本期视频。"),
        ("00:00:15,000", "00:00:20,000", "今天我们聊 Claude Code。"),
    ]
    srt = _make_srt(segs)
    result = parse_subtitle_to_transcript(srt)
    assert "[00:00]" in result
    assert "[00:15]" in result
    assert "大家好" in result
