import pytest
from unittest.mock import AsyncMock, patch
from videosummary.summarizer import DeepSeekSummarizer
from videosummary.errors import SummarizeError
from videosummary.tokens import count_tokens

SHORT_TRANSCRIPT = "[00:00] 这是一段很短的文字稿。\n[00:15] 内容简短，不需要分块。"

LONG_TRANSCRIPT = "\n".join(
    f"[{i:02d}:00] " + "这是一段较长的内容，用于测试分块逻辑。" * 20
    for i in range(200)
)

@pytest.fixture
def summarizer():
    return DeepSeekSummarizer(api_key="sk-test")

@pytest.mark.asyncio
async def test_summarize_short_calls_api_once(summarizer):
    with patch.object(summarizer, "_call_api", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "## 核心摘要\n测试摘要\n## 关键要点\n- 要点\n## 一句话结论\n结论"
        result = await summarizer.summarize(SHORT_TRANSCRIPT)
        assert mock_call.call_count == 1
        assert "核心摘要" in result

@pytest.mark.asyncio
async def test_summarize_long_calls_api_multiple_times(summarizer, monkeypatch):
    tokens = count_tokens(LONG_TRANSCRIPT)
    monkeypatch.setattr("videosummary.summarizer._THRESHOLD", tokens - 1)
    monkeypatch.setattr("videosummary.summarizer._CHUNK_SIZE", tokens // 2)
    monkeypatch.setattr("videosummary.summarizer._OVERLAP", 0)
    with patch.object(summarizer, "_call_api", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "- 要点 [01:00]"
        await summarizer.summarize(LONG_TRANSCRIPT)
        assert mock_call.call_count > 1

@pytest.mark.asyncio
async def test_summarize_raises_on_api_error(summarizer):
    with patch.object(summarizer, "_call_api", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = SummarizeError("429 rate limit")
        with pytest.raises(SummarizeError):
            await summarizer.summarize(SHORT_TRANSCRIPT)

@pytest.mark.asyncio
async def test_timestamps_validated(summarizer):
    transcript = "[00:00] 大家好。\n[01:00] 欢迎。"
    fake_response = "## 核心摘要\n摘要\n## 关键要点\n- 要点 [99:99]\n## 一句话结论\n结论"
    with patch.object(summarizer, "_call_api", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = fake_response
        result = await summarizer.summarize(transcript)
        assert "[99:99]" not in result

@pytest.mark.asyncio
async def test_recursive_reduce_triggered(summarizer, monkeypatch):
    """超过 reduce 阈值时递归整理分段要点。"""
    monkeypatch.setattr("videosummary.summarizer._THRESHOLD", 1)
    monkeypatch.setattr("videosummary.summarizer._REDUCE_THRESHOLD", 10)
    big_sub_summary = "- 要点 [01:00]\n" * 3
    call_count = 0

    async def mock_api(prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        if "片段" in prompt:
            return big_sub_summary
        return "## 核心摘要\n摘要\n## 关键要点\n- 要点 [01:00]\n## 一句话结论\n结论"

    with patch("videosummary.summarizer.split_by_tokens",
               return_value=["[00:00] 内容", "[01:00] 内容"]), \
         patch.object(summarizer, "_call_api", side_effect=mock_api):
        long_transcript = "\n".join(
            f"[{i:02d}:00] " + "内容 " * 200 for i in range(200)
        )
        await summarizer.summarize(long_transcript)
        assert call_count > 2
