# 中文语音转文字助手：AI 复刻说明

## 目标

这是一个仅面向 Windows 的全局语音输入工具。用户按住右 Ctrl 或鼠标后退侧键录音，松开后用 `faster-whisper` 的 Whisper large-v3 在 NVIDIA GPU 上转写，再把结果粘贴到当前光标位置。

AI 接手本仓库时，应优先做到“在另一台 Windows + NVIDIA 机器上行为一致”，不要把任务扩张成跨平台框架或 GUI 重写。

## Codex 自治复刻协议

当用户要求“复刻、安装、部署或运行这个仓库”时，Codex 应在目标 Windows
机器上自主执行以下流程，不把已自动化的步骤重新抛给用户：

1. 克隆仓库并完整阅读本文件；
2. 运行 `安装环境.bat`；
3. 确认脚本依次完成虚拟环境、哈希锁定依赖、CUDA/麦克风检查、固定模型下载与 GPU 加载；
4. 再分别运行 `venv\Scripts\python.exe verify_environment.py` 和
   `venv\Scripts\python.exe prepare_model.py`，保存通过输出作为验收证据；
5. 报告复刻完成、机器环境和验证结果；
6. 只有在目标机器的用户明确同意接管全局输入后，才运行
   `启动_whisper.bat` 做真实桌面验收。

缺少 NVIDIA GPU、驱动、麦克风权限或网络时，应明确报告具体阻塞，不得改成
CPU 推理、替换模型、跳过哈希检查或声称复刻成功。

## 成功标准

1. 双击 `安装环境.bat` 能创建 Python 3.12 虚拟环境、安装固定版本依赖并下载固定 revision 模型；使用 uv 时 Python 固定为 3.12.12。
2. `venv\Scripts\python.exe verify_environment.py` 能看到至少一个 CUDA 设备，并显示支持 `float16`。
3. `venv\Scripts\python.exe prepare_model.py` 能把固定 revision 的 Whisper large-v3 加载到 CUDA float16。
4. 出现 `[就绪]` 后：
   - 按住右 Ctrl 或鼠标后退侧键时录音；
   - 松开后转写并粘贴；
   - 鼠标前进侧键发送 Enter；
   - 鼠标中键发送 Ctrl+1。
5. Ctrl+C 退出后，全局键鼠钩子被卸载，不影响系统输入。

## 环境与硬约束

- 操作系统：Windows 10/11，64 位。
- Python：3.12（uv 安装路径固定为 3.12.12）。
- 推理：必须使用 NVIDIA GPU、CUDA、`float16`，不得静默回退 CPU。
- 已验证硬件：RTX 5090；其他支持 CUDA float16 的 RTX 显卡理论可用，但未在本仓库验证。
- 模型：`Systran/faster-whisper-large-v3`，revision `edaa852ec7e145841d8ffdb056a99866b5f0a478`。
- `venv/`、`models/`、缓存和本地 AI 配置不进入 Git。
- CTranslate2 直接负责 GPU 推理；不要重新加入本项目未使用的 PyTorch、FunASR、ModelScope。

## 关键文件

| 文件 | 作用 |
|---|---|
| `main.py` | 录音、GPU 转写、剪贴板粘贴、Win32 全局钩子和清理逻辑 |
| `requirements.in` | 直接运行依赖，维护者编辑此文件 |
| `requirements.constraints.txt` | 本机实测过的完整传递依赖版本 |
| `requirements.txt` | Windows/Python 3.12 的完整依赖锁与 SHA-256 哈希 |
| `安装环境.bat` | 创建 venv、安装依赖并执行环境检查 |
| `model_settings.py` | 主程序与准备脚本共用的模型仓库、revision 和缓存目录 |
| `prepare_model.py` | 安全下载固定模型并验证 GPU 加载，不安装全局钩子 |
| `启动_whisper.bat` | 一键启动；缺少 venv 时先调用安装脚本 |
| `verify_environment.py` | 不加载模型、不安装钩子的安全环境自检 |
| `README.md` | 面向用户的完整安装、使用和排错说明 |

## 设计不变量

- 低级键鼠钩子回调只向 `_action_queue` 投递动作，绝不在回调内录音、推理、粘贴或阻塞。
- 模型加载完毕后才安装钩子，避免模型加载期间冻结全局输入。
- 用单实例互斥锁防止多个进程同时安装钩子。
- 正常退出和 Ctrl+C 都必须调用 `_cleanup_hooks()`。
- 按键边界已经明确，因此 `vad_filter=False`。
- 转写前做峰值归一化，以改善轻声识别。
- 自动检测到非中英语言时，用中文重新识别。
- 粘贴前保存剪贴板内容，粘贴后恢复。
- 剪贴板恢复必须位于 `finally` 中；只承诺保存和恢复纯文本格式。
- 不在控制台打印完整转写正文，只显示字符数。
- NVIDIA DLL 路径从 `sys.prefix` 对应的虚拟环境解析，不依赖仓库绝对路径。

## 标准操作

```cmd
安装环境.bat
venv\Scripts\python.exe verify_environment.py
venv\Scripts\python.exe prepare_model.py
启动_whisper.bat
```

静态验证：

```cmd
venv\Scripts\python.exe -m py_compile main.py model_settings.py prepare_model.py verify_environment.py
venv\Scripts\python.exe -m pip check
git status --short
```

涉及真实录音、全局钩子、自动粘贴的验收必须由人在 Windows 桌面环境中执行。测试时不要启动第二个实例。

## 常见误区

- 不要提交 3 GB 左右的模型文件或数 GB 的虚拟环境；模型会在首次运行时下载。
- 不要为了“CUDA 支持”安装 PyTorch。本项目的实际推理后端是 CTranslate2，所需 CUDA 运行库已在 `requirements.txt` 中。
- 更新依赖时编辑 `requirements.in`，再按 README 命令重新生成带哈希的 `requirements.txt`；安装必须保留 `--require-hashes`。
- 不要在钩子回调中增加耗时逻辑，否则可能冻结全局鼠标键盘。
- 右 Ctrl、鼠标前进/后退侧键和中键会被完全吞噬，这是当前产品行为，不是 bug。
- `main.py` 使用 Windows API；在 macOS/Linux 上运行失败属于预期行为。
