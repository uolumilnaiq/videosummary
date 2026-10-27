import os
import pytest
from unittest.mock import patch
from videosummary.config import get_api_key
from videosummary.errors import SummarizeError
from videosummary.keystore import Keystore


@pytest.fixture(autouse=True)
def isolated_keystore(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.config._KEYSTORE_DIR", tmp_path)

def test_get_api_key_from_env():
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-123"}):
        assert get_api_key() == "sk-test-123"

def test_get_api_key_raises_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SummarizeError, match="DEEPSEEK_API_KEY"):
            get_api_key()

def test_get_api_key_prefers_keystore_over_env(tmp_path, monkeypatch):
    Keystore(tmp_path).store("DEEPSEEK_API_KEY", "sk-from-keystore")
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-env"}):
        assert get_api_key() == "sk-from-keystore"
