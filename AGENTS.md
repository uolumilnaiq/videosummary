# Repository Guidelines

## 项目结构与模块职责

这是 Python 3.11+ 的视频和音频转录、总结命令行项目。`src/videosummary/` 存放实现：`main.py` 编排主流程，`subtitle.py` 和 `transcriber.py` 处理转录，`summarizer.py` 调用 DeepSeek，`cache.py` 管理缓存。`tests/test_*.py` 与模块对应。`USAGE.md` 是使用手册；`output/` 是生成的文字稿和总结，不是源代码。

## 安装、运行与检查

在本目录运行以下命令。转录需要系统安装 `ffmpeg`、`ffprobe`；Apple Silicon 的 Whisper 引擎使用 `macos` 可选依赖。

```bash
uv sync --extra dev                 # 安装应用和测试依赖
uv sync --extra dev --extra macos   # Apple Silicon 转录环境
uv run videosummary --help          # 查看主命令选项
uv run --extra dev pytest -q        # 运行全部单元测试
uv run ruff check src tests         # 检查 Python 代码
uv build                            # 构建发行包
```

其他入口 `videosummary-setup`、`videosummary-update`、`videosummary-compare` 和 `videosummary-clear` 定义在 `pyproject.toml`；参数示例见 `USAGE.md`。

## 代码风格与命名

使用 4 空格缩进和类型标注，遵循现有模块的简洁 Python 写法。模块、函数和变量用 `snake_case`，类用 `PascalCase`，常量用大写下划线。改动只覆盖当前需求；提交前运行 Ruff。没有配置自动格式化或覆盖率门槛，不要自行声称检查已通过。

## 测试要求

测试使用 `pytest`，异步测试使用 `pytest-asyncio`。新增或修改行为时，在对应的 `tests/test_<module>.py` 中写 `test_<behavior>` 用例；对文件、环境变量及外部服务使用 `tmp_path`、`monkeypatch` 或 mock 隔离。先运行相关测试，再运行完整测试集；真实下载、Whisper 模型和 DeepSeek 调用需另行验证。

## 提交与 Pull Request

本目录既有提交使用 `feat:`、`fix:` 等前缀和简短祈使句；文档改动可用 `docs:`。PR 说明应写明目的、主要改动及验证命令；涉及 CLI 输出时附示例，涉及缺陷时附复现步骤或关联 issue。提交前检查暂存文件，不提交 API Key、`.env`、缓存、虚拟环境或 `output/` 中的个人内容。
