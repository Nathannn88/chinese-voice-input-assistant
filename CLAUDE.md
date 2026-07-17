# 中文语音转文字助手

本仓库的权威开发与复刻说明位于 [AGENTS.md](AGENTS.md)。开始工作前请完整阅读该文件。

核心约束：

- 仅支持 Windows 10/11；
- Whisper large-v3 必须通过 NVIDIA GPU + CUDA + float16 推理，不回退 CPU；
- 保持低级键鼠钩子回调无阻塞；
- 不提交 `venv/`、`models/`、缓存或本地 AI 配置；
- 使用 `安装环境.bat` 自动安装并准备模型，用 `verify_environment.py` 与
  `prepare_model.py` 检查；只有用户同意接管全局输入后才运行
  `启动_whisper.bat`。
