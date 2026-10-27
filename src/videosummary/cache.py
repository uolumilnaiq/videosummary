import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

CACHE_ROOT = Path.home() / ".cache" / "videosummary"

_ALLOWED_QUERY = {"v", "p", "bvid"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
        return f"https://www.youtube.com/watch?v={video_id}"

    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in qs.items() if k in _ALLOWED_QUERY}
    clean_query = urlencode({k: v[0] for k, v in sorted(filtered.items())})
    clean = parsed._replace(query=clean_query, fragment="")
    return urlunparse(clean)


def _url_hash(url: str) -> str:
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _transcript_key(model: str, lang: str, vad: bool) -> str:
    raw = f"{model}:{lang}:vad={vad}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


class CacheDir:
    def __init__(self, url: str):
        self.url = url
        self.path = CACHE_ROOT / _url_hash(url)
        self.path.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.path / "meta.json"

    def _read_meta(self) -> dict:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _write_meta(self, meta: dict) -> None:
        self.write_atomic("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    def has_audio(self) -> bool:
        return (self.path / "audio.mp3").exists()

    def audio_path(self) -> Path:
        return self.path / "audio.mp3"

    def has_transcript(self, model: str, lang: str, vad: bool) -> bool:
        key = _transcript_key(model, lang, vad)
        return (self.path / f"transcript_{key}.txt").exists()

    def read_transcript(self, model: str, lang: str, vad: bool) -> str | None:
        key = _transcript_key(model, lang, vad)
        p = self.path / f"transcript_{key}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def has_cleaned(self, model: str, lang: str, vad: bool) -> bool:
        key = _transcript_key(model, lang, vad)
        return (self.path / f"cleaned_{key}.txt").exists()

    def read_cleaned(self, model: str, lang: str, vad: bool) -> str | None:
        key = _transcript_key(model, lang, vad)
        p = self.path / f"cleaned_{key}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def write_cleaned(self, cleaned: str, model: str, lang: str, vad: bool) -> None:
        key = _transcript_key(model, lang, vad)
        self.write_atomic(f"cleaned_{key}.txt", cleaned)

    def write_transcript(self, transcript: str, model: str, lang: str, vad: bool) -> None:
        key = _transcript_key(model, lang, vad)
        self.write_atomic(f"transcript_{key}.txt", transcript)
        meta = self._read_meta()
        meta["last_transcript_key"] = key
        meta["last_transcript_params"] = {"model": model, "lang": lang, "vad": vad}
        self._write_meta(meta)

    def init_meta(self, url: str, model: str, lang: str) -> None:
        import yt_dlp as _yt
        try:
            import mlx_whisper as _mlx
            mlx_ver = getattr(_mlx, "__version__", "unknown")
        except ImportError:
            mlx_ver = "not_installed"
        meta = self._read_meta()
        meta.update({
            "schema_version": 2,
            "url": url,
            "model": model,
            "lang": lang,
            "ytdlp_version": _yt.version.__version__,
            "mlx_whisper_version": mlx_ver,
        })
        self._write_meta(meta)

    # ── 兼容旧接口 ──────────────────────────────────────────────────────────
    def mark_done(self, stage: str) -> None:
        meta = self._read_meta()
        meta.setdefault("done", [])
        if stage not in meta["done"]:
            meta["done"].append(stage)
        self._write_meta(meta)

    def is_done(self, stage: str) -> bool:
        return stage in self._read_meta().get("done", [])

    def is_valid_for(self, model: str, lang: str) -> bool:
        meta = self._read_meta()
        return meta.get("model") == model and meta.get("lang") == lang

    def write_atomic(self, filename: str, content: str) -> None:
        target = self.path / filename
        fd, tmp_path = tempfile.mkstemp(dir=self.path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def read(self, filename: str) -> str | None:
        p = self.path / filename
        return p.read_text(encoding="utf-8") if p.exists() else None
