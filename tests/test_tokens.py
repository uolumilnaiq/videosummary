from videosummary.tokens import count_tokens, split_by_tokens, format_timestamp

def test_count_tokens_english():
    text = "Hello world, this is a test sentence."
    n = count_tokens(text)
    assert 5 < n < 20

def test_count_tokens_chinese():
    text = "大家好，欢迎来到本期视频，今天我们聊 Claude Code。"
    n = count_tokens(text)
    assert 10 < n < 50

def test_split_returns_list_when_below_threshold():
    short = "这是一段很短的文字稿。" * 10
    chunks = split_by_tokens(short, max_tokens=15_000, overlap=500)
    assert len(chunks) == 1
    assert chunks[0] == short

def test_split_creates_multiple_chunks():
    line = "[00:01] " + "这是测试内容。" * 30 + "\n"
    long_text = line * 200
    chunks = split_by_tokens(long_text, max_tokens=500, overlap=50)
    assert len(chunks) > 1

def test_split_chunks_have_overlap():
    line = "[00:01] " + "词语 " * 50 + "\n"
    long_text = line * 50
    chunks = split_by_tokens(long_text, max_tokens=200, overlap=30)
    if len(chunks) >= 2:
        tail = chunks[0][-50:]
        assert any(word in chunks[1][:100] for word in tail.split()[:3])

def test_timestamp_format_no_invalid_seconds():
    assert format_timestamp(119.9) == "01:59"
    assert format_timestamp(60.0) == "01:00"
    assert format_timestamp(0.0) == "00:00"
