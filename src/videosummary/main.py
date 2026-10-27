from __future__ import annotations
import argparse
import asyncio
import copy
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
import yt_dlp
from tqdm import tqdm
from videosummary.cache import CacheDir
from videosummary.config import get_api_key
from videosummary.errors import FetchError, SummarizeError
from videosummary.subtitle import parse_subtitle_to_transcript, passes_quality_probe
from videosummary.summarizer import DeepSeekSummarizer
from videosummary.transcriber import MlxWhisperTranscriber


def _make_download_hook() -> tuple[callable, callable]:
    """返回 (hook, close)，hook 传给 yt-dlp progress_hooks。"""
    bar: tqdm | None = None

    def hook(d: dict) -> None:
        nonlocal bar
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if bar is None:
                bar = tqdm(total=total, unit="B", unit_scale=True,
                           unit_divisor=1024, desc="[下载]", leave=True)
            if total and bar.total != total:
                bar.total = total
                bar.refresh()
            bar.n = downloaded
            bar.refresh()
        elif status == "finished":
            if bar is not None:
                bar.n = bar.total or bar.n
                bar.refresh()
                bar.close()
                bar = None

    def close() -> None:
        nonlocal bar
        if bar is not None:
            bar.close()
            bar = None

    return hook, close


def sanitize_filename(title: str, max_bytes: int = 200) -> str:
    if not title:
        return "untitled"
    cleaned = re.sub(r'[/\\:*?"<>|\x00-\x1f]', "", title).strip() or "untitled"
    while len(cleaned.encode("utf-8")) > max_bytes:
        cleaned = cleaned[:-1]
    return cleaned


def prompt_multi_part(entries: list[dict], yes: bool) -> list[int]:
    if yes or not sys.stdin.isatty():
        print(f"[警告] 检测到多 P 视频（共 {len(entries)} P），非交互模式默认处理第 1 P。", file=sys.stderr)
        return [0]
    title = entries[0].get("playlist_title") or entries[0].get("title", "未知合集")
    print(f"\n检测到多 P 视频：《{title}》（共 {len(entries)} P）\n")
    print("  [1] 仅处理 P1（默认）  [2] 指定某一 P  [3] 全部处理  [4] 取消\n")
    choice = input("请输入选项 [1/2/3/4]: ").strip() or "1"
    if choice == "2":
        n = input(f"请输入编号（1-{len(entries)}）: ").strip()
        try:
            idx = int(n) - 1
            if 0 <= idx < len(entries):
                return [idx]
        except ValueError:
            pass
        return [0]
    elif choice == "3":
        return list(range(len(entries)))
    elif choice == "4":
        sys.exit(0)
    return [0]


def _header(title: str, url: str, duration: str, transcribe_method: str) -> list[str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [f"# {title}", "", f"> 来源：{url}", f"> 时长：{duration}",
            f"> 转录方式：{transcribe_method}", f"> 生成时间：{now}", "", "---"]


def build_transcript_markdown(title: str, url: str, duration: str, transcribe_method: str,
                               transcript: str) -> str:
    parts = _header(title, url, duration, transcribe_method)
    parts += ["", "## 原始文字稿", "", transcript]
    return "\n".join(parts)


def build_ai_markdown(title: str, url: str, duration: str, transcribe_method: str,
                      cleaned: str | None, summary: str | None) -> str:
    parts = _header(title, url, duration, transcribe_method)
    if summary:
        parts += ["", "## AI 总结", "", summary, "", "---"]
    if cleaned:
        parts += ["", "## 整理后文字稿", "", cleaned]
    return "\n".join(parts)


def _seconds_to_hms(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


def _print_timing(phases: list[tuple[str, float]]) -> None:
    total = sum(t for _, t in phases)
    width = max(len(name) for name, _ in phases)
    print("\n" + "─" * 36)
    print("  耗时统计")
    for name, t in phases:
        label = f"  {name}:".ljust(width + 4)
        print(f"{label}{_fmt_elapsed(t)}")
    print("  " + "─" * 32)
    print(f"  {'总计:'.ljust(width + 2)}{_fmt_elapsed(total)}")
    print("─" * 36)


def _write_outputs(args: argparse.Namespace, base_name: str,
                   title: str, url: str, duration: str, transcribe_method: str,
                   transcript: str, cleaned: str | None, summary: str | None,
                   write_transcript: bool = True) -> None:
    """写两个输出文件。write_transcript=False 时跳过转录文件（--redo-ai 重试场景）。"""
    if args.stdout:
        if write_transcript:
            print(build_transcript_markdown(title, url, duration, transcribe_method, transcript))
        if cleaned or summary:
            print(build_ai_markdown(title, url, duration, transcribe_method, cleaned, summary))
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if write_transcript:
        t_file = out_dir / (base_name + "_transcript.md")
        t_file.write_text(
            build_transcript_markdown(title, url, duration, transcribe_method, transcript),
            encoding="utf-8",
        )
        print(f"✓ 转录文件：{t_file}")

    if cleaned or summary:
        ai_file = out_dir / (base_name + ".md")
        ai_file.write_text(
            build_ai_markdown(title, url, duration, transcribe_method, cleaned, summary),
            encoding="utf-8",
        )
        print(f"✓ AI 整理：{ai_file}")


async def _process_local(audio_path: Path, args: argparse.Namespace) -> None:
    """处理本地音频文件，跳过下载和字幕步骤。"""
    from videosummary.transcriber import _get_duration
    vad_enabled = not args.no_vad
    transcriber = MlxWhisperTranscriber(
        model=args.model, lang=args.lang,
        initial_prompt=args.initial_prompt or "", vad=vad_enabled,
    )
    title = audio_path.stem
    duration_sec = _get_duration(str(audio_path)) or 0.0
    cache = CacheDir(str(audio_path.resolve()))

    skip_ai_cache = args.no_cache or args.redo_ai

    # --redo-ai 时如果当前参数没有缓存，自动回退到上次转录参数
    _model, _lang, _vad = args.model, args.lang, vad_enabled
    if args.redo_ai and not cache.has_transcript(_model, _lang, _vad):
        last = (cache.read("meta.json") or "")
        import json as _json
        try:
            last_params = _json.loads(last).get("last_transcript_params", {})
            if last_params:
                _model = last_params.get("model", _model)
                _lang = last_params.get("lang", _lang)
                _vad = last_params.get("vad", _vad)
                print(f"[--redo-ai] 使用上次转录参数：model={_model} lang={_lang} vad={_vad}")
        except Exception:
            pass

    t_vad = t_transcribe = t_clean = t_summary = 0.0

    if cache.has_transcript(_model, _lang, _vad) and not args.no_cache:
        transcript = cache.read_transcript(_model, _lang, _vad)
        print("[缓存] transcript 命中")
    else:
        print(f"[转录] 本地文件：{audio_path}")
        transcript = transcriber.transcribe(str(audio_path))
        t_vad = transcriber.t_vad
        t_transcribe = transcriber.t_transcribe
        cache.write_transcript(transcript, args.model, args.lang, vad_enabled)
        cache.write_atomic("title.txt", title)
        cache.write_atomic("duration.txt", str(duration_sec))
        cache.write_atomic("transcribe_method.txt", f"mlx-whisper ({args.model})")

    transcribe_method = f"mlx-whisper ({args.model})"
    cleaned = None
    summary = None

    if not args.no_clean:
        summarizer = DeepSeekSummarizer(api_key=get_api_key())
        if cache.has_cleaned(_model, _lang, _vad) and not skip_ai_cache:
            cleaned = cache.read_cleaned(_model, _lang, _vad)
            print("[缓存] 整理稿命中")
        else:
            try:
                print("[整理] 正在用 AI 整理文字稿…")
                t0 = time.time()
                cleaned = await summarizer.clean(transcript)
                t_clean = time.time() - t0
                cache.write_cleaned(cleaned, _model, _lang, _vad)
            except SummarizeError as e:
                print(f"[警告] 整理失败：{e}", file=sys.stderr)

        if not args.no_summary:
            source = cleaned or transcript
            if cache.is_done("summary") and not skip_ai_cache:
                summary = cache.read("summary.md")
                print("[缓存] 总结命中")
            else:
                try:
                    print("[总结] 正在生成 AI 总结…")
                    t0 = time.time()
                    summary = await summarizer.summarize(source)
                    t_summary = time.time() - t0
                    cache.write_atomic("summary.md", summary)
                    cache.mark_done("summary")
                except SummarizeError as e:
                    print(f"[警告] 总结失败：{e}", file=sys.stderr)

    _write_outputs(
        args, base_name=sanitize_filename(title),
        title=title, url=str(audio_path.resolve()),
        duration=_seconds_to_hms(duration_sec),
        transcribe_method=transcribe_method,
        transcript=transcript, cleaned=cleaned, summary=summary,
        write_transcript=not args.redo_ai,
    )

    phases: list[tuple[str, float]] = []
    if t_vad:
        phases.append(("VAD + 切片", t_vad))
    if t_transcribe:
        phases.append(("转文字", t_transcribe))
    if t_clean:
        phases.append(("AI 整理", t_clean))
    if t_summary:
        phases.append(("AI 总结", t_summary))
    if phases:
        _print_timing(phases)


async def process_video(url: str, args: argparse.Namespace) -> None:
    # ── 本地文件模式 ──────────────────────────────────────────────────────────
    local_path = Path(url) if not url.startswith(("http://", "https://")) else None
    if local_path and local_path.exists():
        return await _process_local(local_path, args)

    cache = CacheDir(url)
    vad_enabled = not args.no_vad
    transcriber = MlxWhisperTranscriber(model=args.model, lang=args.lang, initial_prompt=args.initial_prompt or "", vad=vad_enabled)
    transcribe_method = "unknown"

    t_download = t_vad = t_transcribe = t_clean = t_summary = 0.0

    # ── transcript 缓存：按 model+lang+vad 签名，命中则直接用 ──────────────
    if cache.has_transcript(args.model, args.lang, vad_enabled) and not args.no_cache:
        transcript = cache.read_transcript(args.model, args.lang, vad_enabled)
        transcribe_method = cache.read("transcribe_method.txt") or "cached"
        title = cache.read("title.txt") or "untitled"
        duration_sec = float(cache.read("duration.txt") or "0")
        print(f"[缓存] transcript 命中（model={args.model}, lang={args.lang}, vad={vad_enabled}）")
    else:
        _is_bilibili = "bilibili.com" in url or "b23.tv" in url
        ydl_opts: dict = {"quiet": True, "no_warnings": True, "socket_timeout": 60}
        if _is_bilibili:
            ydl_opts["http_headers"] = {
                "Referer": "https://www.bilibili.com",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
        else:
            ydl_opts["remote_components"] = ["ejs:github"]
        ydl_opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
        if getattr(args, "cookies", None):
            ydl_opts["cookiefile"] = args.cookies

        # ── 视频元信息（字幕检测需要） ────────────────────────────────────
        title = cache.read("title.txt") or ""
        duration_sec = float(cache.read("duration.txt") or "0")
        subtitle_text = None

        # 字幕缓存：只看 lang，与 STT 参数无关
        cached_sub = cache.path / f"subtitle_{args.lang}.txt"
        cached_sub_method = cache.path / f"subtitle_{args.lang}_method.txt"
        if cached_sub.exists():
            subtitle_text = cached_sub.read_text(encoding="utf-8")
            transcribe_method = cached_sub_method.read_text(encoding="utf-8") if cached_sub_method.exists() else "人工字幕"
            print(f"[缓存] 字幕命中（lang={args.lang}）")
        else:
            # 需要 extract_info 才能拿字幕列表和元信息
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                raise FetchError(f"视频信息获取失败：{e}") from e
            title = info.get("title", "untitled")
            duration_sec = info.get("duration", 0)
            cache.write_atomic("title.txt", title)
            cache.write_atomic("duration.txt", str(duration_sec))

            for lang_code, sub_list in info.get("subtitles", {}).items():
                if not lang_code.startswith(args.lang[:2]):
                    continue
                for sub in sub_list:
                    if sub.get("ext") in ("srt", "vtt"):
                        sub_opts = {**ydl_opts, "writesubtitles": True, "subtitleslangs": [lang_code],
                                    "skip_download": True, "outtmpl": str(cache.path / "sub.%(ext)s")}
                        with yt_dlp.YoutubeDL(sub_opts) as ydl:
                            ydl.download([url])
                        for f in cache.path.glob("sub.*"):
                            srt_content = f.read_text(encoding="utf-8")
                            if passes_quality_probe(srt_content, lang=args.lang, duration_seconds=duration_sec):
                                subtitle_text = parse_subtitle_to_transcript(srt_content)
                                transcribe_method = f"人工字幕 ({lang_code})"
                                cached_sub.write_text(subtitle_text, encoding="utf-8")
                                cached_sub_method.write_text(transcribe_method, encoding="utf-8")
                            f.unlink()
                        break
                if subtitle_text:
                    break

        # ── 音频缓存：只看 URL，下载一次永久复用 ─────────────────────────
        if not subtitle_text:
            if not cache.has_audio():
                if not title:
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                        title = info.get("title", "untitled")
                        duration_sec = info.get("duration", 0)
                        cache.write_atomic("title.txt", title)
                        cache.write_atomic("duration.txt", str(duration_sec))
                    except Exception as e:
                        raise FetchError(f"视频信息获取失败：{e}") from e
                outtmpl = str(cache.path / "audio.%(ext)s")
                dl_hook, dl_close = _make_download_hook()
                dl_opts = {**ydl_opts, "format": "bestaudio/best", "outtmpl": outtmpl,
                           "socket_timeout": 60,
                           "progress_hooks": [dl_hook],
                           "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]}
                t0 = time.time()
                try:
                    with yt_dlp.YoutubeDL(dl_opts) as ydl:
                        ydl.download([url])
                finally:
                    dl_close()
                t_download = time.time() - t0
                if not cache.has_audio():
                    raise FetchError(f"音频下载失败：未找到 mp3，目录内容：{list(cache.path.iterdir())}")
                print(f"[下载] 音频已保存：{cache.audio_path()}")
            else:
                print("[缓存] 音频命中，跳过下载")

            transcript = transcriber.transcribe(str(cache.audio_path()))
            t_vad = transcriber.t_vad
            t_transcribe = transcriber.t_transcribe
            transcribe_method = f"mlx-whisper ({args.model})"
        else:
            transcript = subtitle_text

        cache.write_transcript(transcript, args.model, args.lang, vad_enabled)
        cache.write_atomic("transcribe_method.txt", transcribe_method)
        if not cache.read("title.txt"):
            cache.write_atomic("title.txt", title)
        if not cache.read("duration.txt"):
            cache.write_atomic("duration.txt", str(duration_sec))

    title = cache.read("title.txt") or "untitled"
    duration_sec = float(cache.read("duration.txt") or "0")

    skip_ai_cache = args.no_cache or args.redo_ai
    cleaned = None
    summary = None

    if not args.no_clean:
        summarizer = DeepSeekSummarizer(api_key=get_api_key())

        # ── 整理步骤 ──────────────────────────────────────────────────────────
        if cache.has_cleaned(args.model, args.lang, vad_enabled) and not skip_ai_cache:
            cleaned = cache.read_cleaned(args.model, args.lang, vad_enabled)
            print("[缓存] 整理稿命中")
        else:
            try:
                print("[整理] 正在用 AI 整理文字稿…")
                t0 = time.time()
                cleaned = await summarizer.clean(transcript)
                t_clean = time.time() - t0
                cache.write_cleaned(cleaned, args.model, args.lang, vad_enabled)
            except SummarizeError as e:
                print(f"[警告] 整理失败：{e}，跳过整理步骤。", file=sys.stderr)

        # ── 总结步骤 ──────────────────────────────────────────────────────────
        if not args.no_summary:
            source = cleaned or transcript
            if cache.is_done("summary") and not skip_ai_cache:
                summary = cache.read("summary.md")
                print("[缓存] 总结命中")
            else:
                try:
                    print("[总结] 正在生成 AI 总结…")
                    t0 = time.time()
                    summary = await summarizer.summarize(source)
                    t_summary = time.time() - t0
                    cache.write_atomic("summary.md", summary)
                    cache.mark_done("summary")
                except SummarizeError as e:
                    print(f"[警告] 总结失败：{e}，仅输出文字稿。", file=sys.stderr)

    base_name = getattr(args, "_multi_part_prefix", None) or sanitize_filename(title)
    _write_outputs(
        args, base_name=base_name,
        title=title, url=url,
        duration=_seconds_to_hms(duration_sec),
        transcribe_method=transcribe_method,
        transcript=transcript, cleaned=cleaned, summary=summary,
        write_transcript=not args.redo_ai,
    )

    phases: list[tuple[str, float]] = []
    if t_download:
        phases.append(("下载", t_download))
    if t_vad:
        phases.append(("VAD + 切片", t_vad))
    if t_transcribe:
        phases.append(("转文字", t_transcribe))
    if t_clean:
        phases.append(("AI 整理", t_clean))
    if t_summary:
        phases.append(("AI 总结", t_summary))
    if phases:
        _print_timing(phases)


def main() -> None:
    parser = argparse.ArgumentParser(prog="videosummary", description="YouTube/Bilibili 视频转文字稿 + DeepSeek AI 总结")
    parser.add_argument("url")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--output", default="./output", metavar="DIR")
    parser.add_argument("--no-clean", action="store_true",
                        help="跳过 AI 整理步骤（同时跳过总结），仅输出原始文字稿")
    parser.add_argument("--no-summary", action="store_true",
                        help="执行 AI 整理但跳过总结")
    parser.add_argument("--lang", default=None, choices=["zh", "en"],
                        help="转录语言（默认：bilibili→zh，youtube→en）")
    parser.add_argument("--model", default="medium", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--cookies-from-browser", default="chrome", metavar="BROWSER", choices=["chrome", "firefox", "safari", "edge"])
    parser.add_argument("--cookies", metavar="FILE", help="Netscape 格式 cookies.txt 文件路径")
    parser.add_argument("--initial-prompt", metavar="TEXT")
    parser.add_argument("--part", type=int, metavar="N")
    parser.add_argument("--all-parts", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--redo-ai", action="store_true",
                        help="跳过整理/总结缓存重新生成（转录缓存不受影响）")
    parser.add_argument("--no-vad", action="store_true", help="禁用 VAD 预处理（默认开启）")
    parser.add_argument("--clear-cache", action="store_true")
    args = parser.parse_args()

    # 根据 URL 自动推断默认语言
    if args.lang is None:
        args.lang = "zh" if ("bilibili.com" in args.url or "b23.tv" in args.url) else "en"

    print(
        f"[参数] url={args.url}\n"
        f"       lang={args.lang}  model={args.model}  vad={'off' if args.no_vad else 'on'}\n"
        f"       cookies-from-browser={args.cookies_from_browser}  cookies={args.cookies}\n"
        f"       no-clean={args.no_clean}  no-summary={args.no_summary}  no-cache={args.no_cache}\n"
        f"       output={args.output}"
    )

    if args.clear_cache:
        cache = CacheDir(args.url)
        shutil.rmtree(cache.path, ignore_errors=True)
        print(f"已清理缓存：{cache.path}")
        return

    # 本地文件：直接处理，跳过 yt-dlp
    _local = Path(args.url) if not args.url.startswith(("http://", "https://")) else None
    if _local:
        if not _local.exists():
            print(f"[错误] 文件不存在：{_local}", file=sys.stderr)
            sys.exit(1)
        asyncio.run(process_video(args.url, args))
        return

    _is_bilibili = "bilibili.com" in args.url or "b23.tv" in args.url
    ydl_opts: dict = {"quiet": True, "no_warnings": True, "socket_timeout": 60, "format": "bestaudio/best"}
    if _is_bilibili:
        ydl_opts["http_headers"] = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
    else:
        ydl_opts["remote_components"] = ["ejs:github"]
    ydl_opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.cookies:
        ydl_opts["cookiefile"] = args.cookies
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(args.url, download=False)
    except Exception as e:
        msg = str(e)
        if "Sign in" in msg or "bot" in msg or "cookies" in msg.lower() or "no longer valid" in msg:
            print(f"[错误] Cookie 失效或需要登录，请重新导出 cookies.txt：{msg}", file=sys.stderr)
        elif "format" in msg.lower():
            print(f"[错误] 无可用格式（可能是 Cookie 失效或网络问题）：{msg}", file=sys.stderr)
        else:
            print(f"[错误] 视频信息获取失败：{msg}", file=sys.stderr)
        sys.exit(1)

    entries = info.get("entries")
    if entries and len(entries) > 1 and not args.part and not args.all_parts:
        indices = prompt_multi_part(list(entries), yes=args.yes)
    elif args.part:
        indices = [args.part - 1]
    elif args.all_parts:
        indices = list(range(len(entries))) if entries else [0]
    else:
        indices = [0] if entries else None

    if indices is None:
        asyncio.run(process_video(args.url, args))
    else:
        playlist_title = entries[0].get("playlist_title") or info.get("title", "playlist")
        async def process_all() -> None:
            for idx in indices:
                entry = entries[idx]
                part_args = copy.copy(args)
                part_args._multi_part_prefix = (
                    f"{sanitize_filename(playlist_title)}"
                    f"_P{idx+1:02d}_"
                    f"{sanitize_filename(entry.get('title', f'P{idx+1}'))}"
                )
                await process_video(
                    entry.get("webpage_url") or entry.get("url"),
                    part_args,
                )
        asyncio.run(process_all())


if __name__ == "__main__":
    main()
