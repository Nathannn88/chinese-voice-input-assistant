# 中文语音转文字助手

一个 Windows 全局语音输入小工具：按住按键说话，松开后在本机 NVIDIA GPU 上用 Whisper large-v3 转写，并自动粘贴到当前光标位置。适用于 Obsidian、Claude Code、浏览器、聊天软件等可以接收文本输入的应用。

## 它如何工作

```text
按住右 Ctrl / 鼠标后退侧键
          ↓
      16 kHz 单声道录音
          ↓
松开 → 峰值归一化 → Whisper large-v3（CUDA float16）
          ↓
中英检测 / 热词修正
          ↓
保存剪贴板 → Ctrl+V 粘贴 → 恢复原剪贴板
```

整个转写过程在本机完成。网络只用于首次安装依赖和首次下载模型，不会把录音发送给在线转写 API。

转写正文会在控制台的 `[完成]` 后完整显示，方便直接查看和复制。粘贴时程序会短暂使用 Windows
剪贴板，并在 `finally` 清理路径中恢复之前的**纯文本**内容；图片、文件、
富文本等非文本剪贴板格式不在本工具的保存范围内。

## 系统要求

- Windows 10/11 64 位；
- NVIDIA RTX 显卡，并安装较新的 NVIDIA 驱动；
- 可用麦克风；
- 首次安装和首次下载模型时需要网络；
- 建议在项目所在磁盘至少预留 16 GB；安装完成并清理临时下载后通常占用约 11 GB。

已验证环境：

- Windows 11；
- NVIDIA RTX 5090；
- Python 3.12.12（已验证版本）；
- faster-whisper 1.2.1；
- CTranslate2 4.7.1；
- CUDA float16。

> 本项目按设计只走 GPU，不提供 CPU 回退。RTX 5090 已实测；其他支持 CUDA float16 的 RTX 显卡理论可用，但请先运行环境检查。

## 最快复刻方式

### 交给朋友的 Codex 自动复刻

把本仓库 GitHub 地址连同下面这段话发给朋友的 Codex：

```text
请在这台 Windows 电脑上完整复刻这个 GitHub 项目：
https://github.com/Nathannn88/chinese-voice-input-assistant

克隆后先完整阅读仓库根目录的 AGENTS.md，并按其中“Codex 自治复刻协议”
自主执行。必须运行安装环境.bat，完成哈希锁定依赖安装、CUDA/麦克风检查、
固定 revision 的 Whisper large-v3 下载和 GPU float16 加载验证。不要改用
CPU，不要替换模型或 revision，不要跳过哈希检查。完成后把 verify_environment.py
和 prepare_model.py 的验证输出报告给我。启动_whisper.bat 会接管全局右 Ctrl
和鼠标侧键，只有在我明确同意真实桌面验收后再启动。
```

仓库已经把 Codex 需要的机器可读规则写在 `AGENTS.md`。只要 Codex 对目标
Windows 机器有终端和文件写入权限，它就可以自动完成源码克隆、环境创建、
精确依赖安装、模型下载和安全验证。

无法由 GitHub 仓库代替的外部条件只有：目标机器本身必须有兼容的 NVIDIA
GPU/驱动、可用麦克风、首次下载网络，以及允许 Codex 执行本地命令的权限。

### 1. 获取代码

在 GitHub 页面选择 **Code → Download ZIP** 并解压，或者：

```cmd
git clone <本仓库地址>
cd <仓库目录>
```

### 2. 安装环境

双击：

```text
安装环境.bat
```

脚本会：

1. 由 `bootstrap_runtime.ps1` 从固定 GitHub Release 下载 uv 0.12.5，校验
   压缩包/可执行文件 SHA-256、文件清单和版本后原子替换到 `.runtime/uv/`，
   不执行远程安装脚本，也不修改系统或用户 PATH；
2. 把精确的 Python 3.12.12 安装到项目 `.runtime/python/`，再创建 `venv/`；
3. 先从独立哈希锁安装 setuptools/wheel，再以 `--no-build-isolation` 根据完整
   运行锁安装 faster-whisper、CTranslate2、NVIDIA CUDA 运行库及固定传递依赖；
4. 检查 CUDA 设备、float16 支持和默认麦克风是否支持 16000 Hz/单声道/float32；
5. 下载固定 revision 的 Whisper large-v3，加载到 CUDA float16，并执行一次真实推理验证 cuBLAS 延迟加载。

不需要预先安装系统 Python、Python Launcher 或全局 uv。uv、Python、安装临时文件、
Hugging Face 元数据和 CUDA 缓存都保存在项目目录；重装 Windows 后只需重新运行脚本。

如果维护者使用 `.runtime\uv\uvx.exe` 临时运行 Ruff、Bandit 等工具，也应先把
`UV_PYTHON_INSTALL_DIR` 设为项目 `.runtime\python`、把 `UV_CACHE_DIR` 设为项目
`.cache\uv`，避免 uvx 默认把工具运行时 Python 下载到 `%APPDATA%\uv\python`。

项目内存储布局：

| 目录 | 内容 |
|---|---|
| `.runtime/uv/` | 固定版 uv 可执行文件 |
| `.runtime/python/` | uv 管理的 Python 3.12.12 |
| `venv/` | Python 依赖与 NVIDIA CUDA/cuDNN 运行库 |
| `models/` | 固定 revision 的 Whisper large-v3 |
| `.cache/` | 安装临时文件、uv/Hugging Face/CUDA 缓存 |

以上目录均被 Git 忽略。Windows 桌面快捷方式本身仍位于用户桌面，但只占数 KB。

### 3. 启动

双击：

```text
启动_whisper.bat
```

`安装环境.bat` 已经从 Hugging Face 下载固定 revision 的
`Systran/faster-whisper-large-v3`，模型约 3 GB，保存在本项目的
`models/` 目录中。启动时会直接读取缓存；看到以下提示后即可使用：

```text
[就绪] 模型与全局钩子均已就绪，按住右Ctrl开始录音
```

## 操作方式

| 输入 | 行为 |
|---|---|
| 按住右 Ctrl | 开始录音 |
| 松开右 Ctrl | 停止录音、转写并粘贴 |
| 按住/松开鼠标后退侧键 | 与右 Ctrl 相同 |
| 鼠标前进侧键 | 发送 Enter |
| 鼠标中键 | 发送 Ctrl+1 |
| 左 Ctrl+C | 安全退出并卸载全局钩子 |

右 Ctrl、鼠标前进/后退侧键和中键会被工具完全接管，原始功能不会继续传给当前应用。

## 手动环境检查

环境检查不会加载模型、录音、安装全局钩子或发送按键，可以安全地单独执行：

```cmd
venv\Scripts\python.exe verify_environment.py
```

正常输出应包含：

```text
[CUDA] 检测到 1 个设备
[CUDA] 支持的计算类型：... float16 ...
[录音] 检测到 ... 个输入设备
[通过] 运行环境满足要求。
```

模型准备脚本同样不会录音、安装钩子、修改剪贴板或发送按键：

```cmd
venv\Scripts\python.exe prepare_model.py
```

它会下载固定模型（若尚未缓存）并验证 `device=cuda`、
`compute_type=float16`。

## 当前转写配置

- 模型：Whisper large-v3；
- 模型 revision：`edaa852ec7e145841d8ffdb056a99866b5f0a478`；
- 设备：CUDA；
- 计算类型：float16；
- `beam_size=3`；
- `vad_filter=False`，录音边界由按键控制；
- 中英自动检测，检测成其他语言时强制用中文重识别；
- 16 kHz 单声道录音；
- 转写前做峰值归一化；
- 内置 `Cloud → Claude`、`克劳德 → Claude` 等热词修正。

这些参数集中在 [main.py](main.py) 顶部和 `_WHISPER_COMMON` 中。

## 依赖锁定

- `requirements.in` 只列直接运行依赖；
- `requirements.constraints.txt` 固定本机实测过的完整传递依赖版本；
- `requirements.txt` 锁定 Windows x86_64 + Python 3.12 的完整传递依赖和
  SHA-256 哈希；
- `requirements.build.in` 与 `requirements.build.txt` 单独固定
  `setuptools==70.2.0` 和 `wheel==0.45.1`，构建工具只接受锁中的 wheel；
- `安装环境.bat` 固定使用官方 PyPI，并通过 `--require-hashes` 验证每个
  wheel 或源码包的下载产物；运行依赖安装固定使用 `--no-build-isolation`，
  禁止 PEP 517 另建环境下载未锁定构建依赖；
- 安装脚本固定使用项目内 uv 0.12.5 和 Python 3.12.12；不读取系统 Python，
  也不执行全局 `pip install`；
- pip 持久缓存被禁用，安装临时目录被重定向到项目 `.cache/`，成功后清理；
- CTranslate2 直接负责 GPU 推理，不需要 PyTorch、FunASR 或 ModelScope。

维护者更新 `requirements.in` 后，应重新生成锁定文件：

```cmd
uv pip compile requirements.in --constraint requirements.constraints.txt --python-platform x86_64-pc-windows-msvc --python-version 3.12 --generate-hashes --emit-index-url --output-file requirements.txt
```

uv 引导包固定为
`uv-x86_64-pc-windows-msvc.zip`，压缩包 SHA-256 为
`4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a`，
`uv.exe` SHA-256 为
`8da6cedef60c27ac997ebf400fbfc6d373c5b0a7ae6a299b9d52be7fe63723fb`。

## 速度参考

RTX 5090、`beam_size=3` 的本机经验值：

| 说话时长 | 推理耗时 |
|---|---:|
| 1–3 秒 | 约 0.2–0.5 秒 |
| 5–8 秒 | 约 0.5–1.0 秒 |
| 10–15 秒 | 约 1.0–2.0 秒 |

首次加载模型的时间不计入上述数据。

## 常见问题

### 环境检查提示没有 CUDA 设备

确认电脑使用 NVIDIA 显卡、驱动已正确安装，并在命令行执行 `nvidia-smi`。本项目不会自动改用 CPU。

### 提示找不到 cublas、cudnn 或其他 DLL

重新运行 `安装环境.bat`。脚本会安装 `nvidia-cublas-cu12`、`nvidia-cudnn-cu12` 和 `nvidia-cuda-nvrtc-cu12`，程序会从当前虚拟环境动态加入这些 DLL 目录。

### 首次启动卡在模型下载

模型约 3 GB。确认能够访问 Hugging Face，并保持窗口开启。已经下载的文件会缓存在 `models/`，通常可以断点续传。

### 没有录到声音

在 Windows 的“隐私和安全性 → 麦克风”中允许桌面应用访问麦克风，然后运行 `verify_environment.py` 检查输入设备。

### 按键或鼠标被占用

这是当前设计：工具会吞掉右 Ctrl、两个鼠标侧键和鼠标中键的原始事件。按左 Ctrl+C 退出即可恢复。若程序异常退出，可在任务管理器结束对应的 `python.exe`，然后只启动一个实例。

### 粘贴位置不对

开始说话前先把输入焦点放在目标文本框中。工具会向当前焦点发送 Ctrl+V，并在粘贴后恢复原剪贴板内容。

## 仓库中为什么没有模型和 venv

本地完整目录通常约 11 GB，其中运行时、模型和虚拟环境都是可重新生成的机器产物，
不适合提交 Git：

- `.runtime/` 由 `安装环境.bat` 下载固定版 uv 和 Python 3.12.12；
- `venv/` 由 `安装环境.bat` 重建；
- `models/` 在首次启动时按固定 revision 下载；
- `.cache/` 保存项目内临时文件和运行缓存；
- `.claude/`、`.codex/` 等本地 AI 配置也不会上传。

仓库只保存复刻所需的源码、固定依赖、安装脚本、环境检查与说明文档。

## 给 AI 复刻者

请先阅读 [AGENTS.md](AGENTS.md)。其中列出了成功标准、Windows/CUDA 硬约束、关键不变量、验收命令和常见误区。

## 许可证

本项目采用 [MIT License](LICENSE)，允许使用、复制、修改和分发，但不提供任何担保。
