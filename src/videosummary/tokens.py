import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


def split_by_tokens(text: str, max_tokens: int = 15_000, overlap: int = 500,
                    trim_to_sentence: bool = True) -> list[str]:
    tokens = _enc.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    if not trim_to_sentence:
        # 直接按 token 边界切，无级联风险
        step = max(max_tokens - overlap, 1)
        return [
            _enc.decode(tokens[i: i + max_tokens])
            for i in range(0, len(tokens), step)
        ]

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_text = _enc.decode(tokens[start:end])

        for sep in ("。\n", "\n\n", "。", "\n"):
            idx = chunk_text.rfind(sep)
            if idx > len(chunk_text) // 2:
                chunk_text = chunk_text[: idx + len(sep)]
                break

        chunks.append(chunk_text)
        consumed = len(_enc.encode(chunk_text))
        if consumed <= overlap:
            start = end
        else:
            start += consumed - overlap

    return chunks
