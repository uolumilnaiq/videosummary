import sys

from videosummary.cache import CacheDir
from videosummary.clear import main


def test_clear_relative_local_file_uses_resolved_cache_path(tmp_path, monkeypatch):
    monkeypatch.setattr("videosummary.cache.CACHE_ROOT", tmp_path / "cache")
    audio = tmp_path / "recording.mp3"
    audio.write_bytes(b"audio")
    cache = CacheDir(str(audio.resolve()))
    cache.write_atomic("summary_deadbeef.md", "summary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["videosummary-clear", "recording.mp3", "--all"])
    main()

    assert not cache.path.exists()
