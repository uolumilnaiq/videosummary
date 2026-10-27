from __future__ import annotations
import asyncio
import re
import httpx
from videosummary.errors import SummarizeError
from videosummary.tokens import count_tokens, split_by_tokens

_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
_MODEL = "deepseek-chat"  # deepseek-v4-flash: 1M context, 384K output
_THRESHOLD = 600_000      # summarize 分块阈值
_REDUCE_THRESHOLD = 200_000
_CHUNK_SIZE = 200_000
_CLEAN_CHUNK_SIZE = 60_000   # DeepSeek tokenizer 约为 cl100k 的 2x，60k cl100k ≈ 120k DS tokens，输出留余量
_OVERLAP = 1_000
_MAX_CONCURRENCY = 5
_MAX_RETRIES = 3
_MAX_REDUCE_DEPTH = 3

_CLEAN_PROMPT = """你是专业的视频内容编辑。以下是由 Whisper 自动识别的视频文字稿，包含时间戳标记和可能的识别错误。

请将其整理为一篇流畅的文章：
1. **去除噪声**：删除明显的幻觉内容（如大量重复的词：AI AI AI 或 agent agent agent）
2. **去除时间戳**：删除所有 [mm:ss] 标记
3. **修正断句**：将零碎短句合并为完整自然的句子
4. **语义分段**：按话题自动分段，每段之间空一行
5. **翻译**：若原文为英文或其他语言，翻译为简体中文，要求信达雅；专有名词（人名、产品名、技术术语等）可保留原文
6. **保持原意**：不改写内容，不添加未提及的信息

直接输出整理后的文章正文，不要加任何标题或说明。

文字稿：
{transcript}"""

_SINGLE_PROMPT = """你是专业的视频内容分析师。请对以下视频文字稿进行总结，**输出必须为简体中文**。输出格式严格为：

## 核心摘要
（2-3 句话概括主要内容）

## 关键要点
- 要点1 [mm:ss]
- 要点2 [mm:ss]

## 一句话结论
（最核心的 takeaway）

要求：每个关键要点末尾用 [mm:ss] 标注对应原视频时间戳（必须是文字稿中实际出现的时间戳）。关键要点总数不超过 15 条。

文字稿：
{transcript}"""

_MAP_PROMPT = """以下是一段视频文字稿的片段（第 {i}/{n} 段，时间范围 {start}-{end}）。
请提炼这一段的核心要点（最多 5 条 bullet），保留时间戳，**输出必须为简体中文**。
不要给最终结论，只做事实性提炼。

文字稿：
{chunk}"""

_REDUCE_PROMPT = """以下是一个视频按时间顺序的分段要点。请整合成最终总结，**输出必须为简体中文**，格式：

## 核心摘要
## 关键要点（按 [mm:ss] 升序排列，总数不超过 15 条）
## 一句话结论

分段要点：
{summaries}"""

_TS_PATTERN = re.compile(r"\[(\d{2}:\d{2})\]")


def _validate_timestamps(summary: str, transcript: str) -> str:
    valid_ts = set(_TS_PATTERN.findall(transcript))
    return _TS_PATTERN.sub(lambda m: m.group(0) if m.group(1) in valid_ts else "", summary)


class _TokenBucket:
    def __init__(self):
        self._delay = 0.0

    async def acquire(self):
        if self._delay > 0:
            await asyncio.sleep(self._delay)

    def slow_down(self):
        self._delay = min(self._delay + 2.0, 30.0)

    def reset(self):
        self._delay = max(0.0, self._delay - 0.5)


class DeepSeekSummarizer:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._bucket = _TokenBucket()
        self._sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def clean(self, transcript: str) -> str:
        # 按 _CLEAN_CHUNK_SIZE 分块，确保每块输出不超过 max_tokens
        if count_tokens(transcript) <= _CLEAN_CHUNK_SIZE:
            return await self._call_api(_CLEAN_PROMPT.format(transcript=transcript))
        chunks = split_by_tokens(transcript, _CLEAN_CHUNK_SIZE, 0, trim_to_sentence=False)
        n = len(chunks)
        results = []
        for i, chunk in enumerate(chunks, 1):
            print(f"[整理] 分块 {i}/{n}…")
            results.append(await self._call_api(_CLEAN_PROMPT.format(transcript=chunk)))
        return "\n\n".join(results)

    async def summarize(self, transcript: str) -> str:
        if count_tokens(transcript) < _THRESHOLD:
            raw = await self._call_api(_SINGLE_PROMPT.format(transcript=transcript))
        else:
            raw = await self._map_reduce(transcript)
        return _validate_timestamps(raw, transcript)

    async def _map_reduce(self, transcript: str, _depth: int = 0) -> str:
        chunks = split_by_tokens(transcript, _CHUNK_SIZE, _OVERLAP)
        n = len(chunks)

        async def map_chunk(i: int, chunk: str) -> str:
            lines = chunk.split("\n")
            start = lines[0][:7] if lines else "?"
            end = lines[-1][:7] if lines else "?"
            return await self._call_api(_MAP_PROMPT.format(i=i+1, n=n, start=start, end=end, chunk=chunk))

        sub_summaries = await asyncio.gather(*[map_chunk(i, c) for i, c in enumerate(chunks)])
        joined = "\n\n".join(sub_summaries)

        if count_tokens(joined) >= _REDUCE_THRESHOLD and _depth < _MAX_REDUCE_DEPTH:
            return await self._map_reduce(joined, _depth=_depth + 1)

        return await self._call_api(_REDUCE_PROMPT.format(summaries=joined))

    async def _call_api(self, prompt: str) -> str:
        async with self._sem:
            await self._bucket.acquire()
            for attempt in range(_MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.post(
                            _DEEPSEEK_URL,
                            headers={"Authorization": f"Bearer {self._api_key}"},
                            json={"model": _MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 131072},
                        )
                    if resp.status_code == 429:
                        self._bucket.slow_down()
                        await asyncio.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    self._bucket.reset()
                    choice = resp.json()["choices"][0]
                    if choice.get("finish_reason") == "length":
                        raise SummarizeError("输出被截断（finish_reason=length），请减小分块大小")
                    return choice["message"]["content"]
                except httpx.HTTPStatusError as e:
                    if attempt == _MAX_RETRIES - 1:
                        raise SummarizeError(f"DeepSeek API 错误：{e}") from e
                    await asyncio.sleep(2 ** attempt)
                except SummarizeError:
                    raise
                except Exception as e:
                    if attempt == _MAX_RETRIES - 1:
                        raise SummarizeError(f"请求失败：{e}") from e
                    await asyncio.sleep(2 ** attempt)
            raise SummarizeError("DeepSeek API 重试耗尽")
