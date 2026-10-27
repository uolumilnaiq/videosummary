import os
import pytest
from videosummary.cache import CacheDir, normalize_url

def test_normalize_url_strips_tracking():
    url = "https://www.youtube.com/watch?v=abc123&t=120s&utm_source=share"
    assert normalize_url(url) == "https://www.youtube.com/watch?v=abc123"

def test_normalize_url_keeps_bilibili_p():
    url = "https://www.bilibili.com/video/BV1xxx?p=3&from=search"
    assert normalize_url(url) == "https://www.bilibili.com/video/BV1xxx?p=3"

def test_normalize_url_youtu_be():
    url = "https://youtu.be/abc123?si=xyz"
    assert normalize_url(url) == "https://www.youtube.com/watch?v=abc123"

def test_cache_dir_creates_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path)
    cache = CacheDir("https://www.youtube.com/watch?v=abc123")
    assert cache.path.exists()

def test_cache_atomic_write(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path)
    cache = CacheDir("https://www.youtube.com/watch?v=abc123")
    cache.write_atomic("transcript.txt", "hello world")
    assert (cache.path / "transcript.txt").read_text() == "hello world"
    assert not list(cache.path.glob("*.tmp"))

def test_cache_meta_stage_tracking(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path)
    cache = CacheDir("https://www.youtube.com/watch?v=abc123")
    assert not cache.is_done("transcript")
    cache.mark_done("transcript")
    assert cache.is_done("transcript")

def test_cache_version_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path)
    cache = CacheDir("https://www.youtube.com/watch?v=abc123")
    cache.init_meta("https://www.youtube.com/watch?v=abc123", model="medium", lang="zh")
    assert cache.is_valid_for(model="medium", lang="zh")
    assert not cache.is_valid_for(model="large-v3", lang="zh")

def test_cache_atomic_write_cleans_tmp_on_error(tmp_path, monkeypatch):
    """ENOSPC 等写入错误时 .tmp 文件应被清理"""
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path)
    cache = CacheDir("https://www.youtube.com/watch?v=abc123")
    def bad_fdopen(fd, *args, **kwargs):
        os.close(fd)
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(os, "fdopen", bad_fdopen)
    with pytest.raises(OSError):
        cache.write_atomic("transcript.txt", "content")
    assert not list(cache.path.glob("*.tmp"))
