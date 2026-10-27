from videosummary.errors import FetchError, TranscribeError, SummarizeError

def test_fetch_error_is_exception():
    err = FetchError("视频不存在")
    assert isinstance(err, Exception)
    assert str(err) == "视频不存在"

def test_transcribe_error_is_exception():
    err = TranscribeError("OOM")
    assert isinstance(err, Exception)

def test_summarize_error_is_exception():
    err = SummarizeError("429 rate limit")
    assert isinstance(err, Exception)
