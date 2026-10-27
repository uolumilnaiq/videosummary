import pytest
from unittest.mock import patch
from videosummary.transcriber import MlxWhisperTranscriber
from videosummary.errors import TranscribeError

@patch("videosummary.transcriber.mlx_whisper")
def test_transcribe_returns_text_with_timestamps(mock_mlx):
    mock_mlx.transcribe.return_value = {
        "segments": [
            {"start": 0.0, "text": " 大家好"},
            {"start": 15.3, "text": " 欢迎来到本期视频"},
        ]
    }
    t = MlxWhisperTranscriber(model="medium", lang="zh", initial_prompt="")
    result = t.transcribe("/tmp/fake.mp3")
    assert "[00:00]" in result
    assert "[00:15]" in result
    assert "大家好" in result

@patch("videosummary.transcriber.mlx_whisper")
def test_transcribe_raises_on_empty_result(mock_mlx):
    mock_mlx.transcribe.return_value = {"segments": []}
    t = MlxWhisperTranscriber(model="medium", lang="zh", initial_prompt="")
    with pytest.raises(TranscribeError, match="空"):
        t.transcribe("/tmp/fake.mp3")

@patch("videosummary.transcriber.mlx_whisper")
def test_transcribe_raises_on_oom(mock_mlx):
    mock_mlx.transcribe.side_effect = MemoryError("OOM")
    t = MlxWhisperTranscriber(model="large-v3", lang="zh", initial_prompt="")
    with pytest.raises(TranscribeError, match="内存"):
        t.transcribe("/tmp/fake.mp3")
