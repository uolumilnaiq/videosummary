from videosummary.main import (
    build_ai_markdown,
    build_transcript_markdown,
    prompt_multi_part,
    sanitize_filename,
)

def test_sanitize_filename_removes_reserved_chars():
    result = sanitize_filename('Python: 入门/进阶 "教程" <完整版>')
    for ch in r'/\:*?"<>|':
        assert ch not in result

def test_sanitize_filename_truncates_long():
    assert len(sanitize_filename("很长的标题" * 50).encode("utf-8")) <= 200

def test_sanitize_filename_fallback_on_empty():
    assert len(sanitize_filename("")) > 0

def test_prompt_multi_part_non_interactive(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert prompt_multi_part([{"title": "P1"}, {"title": "P2"}], yes=False) == [0]

def test_build_output_markdown():
    metadata = dict(title="测试视频", url="https://youtube.com/watch?v=abc",
                    duration="00:10:00", transcribe_method="mlx-whisper (medium)")
    transcript = build_transcript_markdown(**metadata, transcript="[00:00] 大家好")
    notes = build_ai_markdown(**metadata, cleaned="整理后的内容",
                              summary="## 核心摘要\n摘要内容")
    assert "测试视频" in transcript and "[00:00] 大家好" in transcript
    assert "核心摘要" in notes and "整理后的内容" in notes

def test_sanitize_filename_multi_part_naming():
    filename = f"{sanitize_filename('Python从入门到精通')}_P{1:02d}_{sanitize_filename('Python环境安装')}.md"
    assert filename == "Python从入门到精通_P01_Python环境安装.md"

def test_partial_success_filename_suffix(tmp_path):
    import argparse
    args = argparse.Namespace(stdout=False, output=str(tmp_path), no_summary=False)
    summary = None
    suffix = ".transcript.md" if (not args.no_summary and summary is None) else ".md"
    assert (sanitize_filename("测试视频") + suffix).endswith(".transcript.md")
