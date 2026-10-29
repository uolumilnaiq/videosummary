import tomllib
from pathlib import Path


def test_macos_transcription_extra_declares_vad_runtime_dependencies():
    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    dependencies = project["project"]["optional-dependencies"]["macos"]
    names = {item.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0] for item in dependencies}

    assert {"mlx-whisper", "silero-vad", "numpy", "scipy"} <= names
