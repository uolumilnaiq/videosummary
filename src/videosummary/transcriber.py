from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol

try:
    import mlx_whisper
except ImportError:
    mlx_whisper = None  # type: ignore

from videosummary.errors import TranscribeError
from videosummary.tokens import format_timestamp

_BASE_PROMPT = "以下是普通话讲解，使用简体中文。Claude, Anthropic, Cursor, AI, GPT, LangChain, RAG, embedding"
_CHUNK_SEC = 10 * 60  # mlx-whisper 单次处理上限
_VAD_MERGE_GAP_SEC = 0.3


class Transcriber(Protocol):
    def transcribe(self, audio_path: str) -> str: ...


class MlxWhisperTranscriber:
    def __init__(self, model: str, lang: str, initial_prompt: str = "", vad: bool = True):
        self.model = model
        self.lang = lang
        self.vad = vad
        combined = f"{_BASE_PROMPT}, {initial_prompt}".strip(", ")
        self.initial_prompt = combined
        self.t_vad: float = 0.0
        self.t_transcribe: float = 0.0

    def transcribe(self, audio_path: str) -> str:
        if mlx_whisper is None:
            raise TranscribeError("mlx-whisper 未安装，仅支持 macOS Apple Silicon")

        audio_path = str(audio_path)

        if self.vad:
            t0 = time.time()
            vad_result = _apply_vad_chunked(audio_path, _CHUNK_SEC)
            self.t_vad = time.time() - t0
            if vad_result is not None:
                chunks, vad_tmp_dir = vad_result
                try:
                    t1 = time.time()
                    n = len(chunks)
                    lines: list[str] = []
                    for i, (chunk_path, offset_map) in enumerate(chunks, 1):
                        lines.append(self._transcribe_single(
                            chunk_path, offset_map, desc=f"[转录] 分块 {i}/{n}"
                        ))
                    self.t_transcribe = time.time() - t1
                    return "\n".join(lines)
                finally:
                    shutil.rmtree(vad_tmp_dir, ignore_errors=True)

        t0 = time.time()
        duration = _get_duration(audio_path)
        if duration and duration > _CHUNK_SEC:
            result = self._transcribe_chunked(audio_path)
        else:
            result = self._transcribe_single(audio_path)
        self.t_transcribe = time.time() - t0
        return result

    def _transcribe_single(self, audio_path: str,
                           offset_map: list[tuple[float, float, float]] | None = None,
                           desc: str = "[转录]") -> str:
        from tqdm import tqdm
        repo = f"mlx-community/whisper-{self.model}-mlx"
        # 转录时始终离线，避免每次向 HuggingFace 检查版本更新
        # 如需更新模型，运行 videosummary-update
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _kwargs = dict(
            path_or_hf_repo=repo,
            language=self.lang,
            initial_prompt=self.initial_prompt,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.0,
            logprob_threshold=-1.0,
        )
        with tqdm(total=None, desc=desc, unit="", bar_format="{desc} 运行中… {elapsed}", leave=True):
            try:
                result = mlx_whisper.transcribe(audio_path, **_kwargs)
            except MemoryError as e:
                raise TranscribeError(f"内存不足（OOM），请改用更小的模型：{e}") from e
            except Exception as e:
                raise TranscribeError(f"转录失败：{e}") from e

        segments = result.get("segments", [])
        if not segments:
            raise TranscribeError("转录结果为空，请检查音频文件")

        lines = []
        for s in segments:
            ts = _remap_timestamp(s["start"], offset_map) if offset_map else s["start"]
            text = s["text"].strip()
            if text:
                lines.append(f"[{format_timestamp(ts)}] {text}")
        return "\n".join(lines)

    def _transcribe_chunked(self, audio_path: str,
                            offset_map: list[tuple[float, float, float]] | None = None) -> str:
        transcripts = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            chunk_pattern = str(Path(tmp_dir) / "chunk_%03d.mp3")
            try:
                subprocess.run(
                    ["ffmpeg", "-i", audio_path, "-f", "segment",
                     "-segment_time", "600", "-c", "copy", chunk_pattern],
                    check=True, capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                raise TranscribeError(
                    f"ffmpeg 分段失败: {e.stderr.decode(errors='replace')}"
                ) from e
            chunks = sorted(Path(tmp_dir).glob("chunk_*.mp3"))
            chunk_offset = 0.0
            for i, chunk in enumerate(chunks, 1):
                dur = _get_duration(str(chunk)) or 0.0
                chunk_map = _slice_offset_map(offset_map, chunk_offset, chunk_offset + dur) if offset_map else None
                transcripts.append(self._transcribe_single(
                    str(chunk), chunk_map, desc=f"[转录] 分块 {i}/{len(chunks)}"
                ))
                chunk_offset += dur
        return "\n".join(transcripts)


def _load_audio_16k(audio_path: str):
    """用 ffmpeg 转成 16kHz mono WAV，再用 scipy 加载为 tensor，绕开 torchaudio 依赖。"""
    import torch
    import scipy.io.wavfile as wav_io
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1",
             "-f", "wav", wav_path],
            check=True, capture_output=True,
        )
        sr, data = wav_io.read(wav_path)
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        return torch.from_numpy(data)
    finally:
        Path(wav_path).unlink(missing_ok=True)


def _remap_timestamp(ts: float, offset_map: list[tuple[float, float, float]]) -> float:
    """把拼接音频里的时间戳映射回原始视频时间。
    offset_map 每项：(concat_start, original_start, duration)
    """
    for concat_start, orig_start, duration in offset_map:
        if concat_start <= ts < concat_start + duration:
            return orig_start + (ts - concat_start)
    # 超出最后一段时追加
    if offset_map:
        last_concat, last_orig, last_dur = offset_map[-1]
        return last_orig + (ts - last_concat)
    return ts


def _slice_offset_map(offset_map: list[tuple[float, float, float]],
                      chunk_start: float, chunk_end: float) -> list[tuple[float, float, float]]:
    """从完整 offset_map 中切出属于某个 chunk 的部分，并调整 concat_start 为相对偏移。"""
    result = []
    for concat_start, orig_start, duration in offset_map:
        seg_end = concat_start + duration
        if seg_end <= chunk_start or concat_start >= chunk_end:
            continue
        clipped_start = max(concat_start, chunk_start)
        clipped_end = min(seg_end, chunk_end)
        result.append((clipped_start - chunk_start, orig_start + (clipped_start - concat_start),
                        clipped_end - clipped_start))
    return result


def _apply_vad_chunked(
    audio_path: str,
    chunk_sec: float = _CHUNK_SEC,
) -> tuple[list[tuple[str, list[tuple[float, float, float]]]], str] | None:
    """VAD + 分块一体化：直接产出按 chunk_sec 分组的 (音频路径, offset_map) 列表。
    省去 speech_only.mp3 中间文件和二次 split pass。失败返回 None 降级。
    """
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps
    except ImportError:
        return None

    tmp_dir: Path | None = None
    try:
        model = load_silero_vad()
        wav = _load_audio_16k(audio_path)
        timestamps = get_speech_timestamps(wav, model, return_seconds=True)
        if not timestamps:
            return None

        # 合并间隔过小的相邻段
        merged: list[tuple[float, float]] = []
        for seg in timestamps:
            start, end = seg["start"], seg["end"]
            if merged and start - merged[-1][1] < _VAD_MERGE_GAP_SEC:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))

        total_speech = sum(e - s for s, e in merged)
        total_orig = merged[-1][1] if merged else 1
        print(f"[VAD] 语音段 {len(merged)} 个，语音占比 {total_speech / total_orig:.0%}，"
              f"语音时长 {total_speech / 60:.1f} 分钟")

        tmp_dir = Path(tempfile.mkdtemp(prefix="vad_"))
        chunks: list[tuple[str, list[tuple[float, float, float]]]] = []

        # 按 chunk_sec 分桶：将语音段分组，每组累积时长不超过 chunk_sec
        bucket: list[tuple[float, float]] = []
        bucket_dur = 0.0

        escaped_path = audio_path.replace("\\", "\\\\").replace("'", "\\'")

        # 预算分块总数（用于进度显示）
        estimated_chunks = max(1, int(total_speech / chunk_sec) + (1 if total_speech % chunk_sec else 0))

        def _flush_bucket(segs: list[tuple[float, float]], idx: int) -> None:
            bucket_speech = sum(e - s for s, e in segs)
            print(f"[VAD] 生成分块 {idx + 1}/{estimated_chunks}（{bucket_speech / 60:.1f} 分钟语音，{len(segs)} 段）…")
            concat_list = tmp_dir / f"chunk_{idx:03d}_concat.txt"
            lines = [f"file '{escaped_path}'\ninpoint {s}\noutpoint {e}" for s, e in segs]
            concat_list.write_text("\n".join(lines), encoding="utf-8")
            out = tmp_dir / f"chunk_{idx:03d}.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(concat_list), "-c", "copy", str(out)],
                check=True, capture_output=True,
            )
            # 构建该 chunk 的 offset_map（concat_start 相对 chunk 内部）
            offset_map: list[tuple[float, float, float]] = []
            cursor = 0.0
            for s, e in segs:
                dur = e - s
                offset_map.append((cursor, s, dur))
                cursor += dur
            chunks.append((str(out), offset_map))

        for orig_start, orig_end in merged:
            dur = orig_end - orig_start
            if bucket and bucket_dur + dur > chunk_sec:
                _flush_bucket(bucket, len(chunks))
                bucket = []
                bucket_dur = 0.0
            bucket.append((orig_start, orig_end))
            bucket_dur += dur

        if bucket:
            _flush_bucket(bucket, len(chunks))

        if not chunks:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        if len(chunks) > 1:
            print(f"[VAD] 分块完成，共 {len(chunks)} 块，开始转录…")
        return chunks, str(tmp_dir)

    except Exception as e:
        print(f"[VAD] 处理失败，降级为原始音频：{e}")
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return None


def _get_duration(audio_path: str) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
