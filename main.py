#!/usr/bin/env python3
"""
中文语音转文字助手
按住右 Ctrl 键录音，松开后自动转文字并粘贴到光标位置
"""

import atexit
import ctypes
import queue
import re
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field

from audio_settings import AUDIO_DTYPE, CHANNELS, SAMPLE_RATE
from model_settings import MODEL_DIR, MODEL_REVISION, MODEL_SIZE
from nvidia_runtime import configure_nvidia_dll_search

# ── 配置 ──────────────────────────────────────────
LANGUAGE    = None   # None=自动检测，支持中英混合

# CTranslate2 会在录音线程中延迟加载 cuBLAS；除保留 DLL directory 句柄外，
# 还需把项目 NVIDIA bin 目录前置到进程 PATH，供跨线程 LoadLibrary 使用。
_dll_handles = configure_nvidia_dll_search()

# 常见误识别修正（正则 → 正确写法，按需添加）
HOTWORD_FIXES = [
    (r"(?i)cloud\s*code", "Claude Code"),
    (r"克劳德\s*[Cc]ode", "Claude Code"),
    (r"(?i)\bcloud\b", "Claude"),
    (r"克劳德", "Claude"),
]
# ─────────────────────────────────────────────────

import numpy as np
import pyautogui
import pyperclip
import sounddevice as sd

# ── 单实例保护（防止多个进程同时挂钩导致输入冻结） ──
_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "VoiceAssistant_SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    print("[错误] 已有实例在运行，请先关闭旧实例再启动")
    ctypes.windll.kernel32.CloseHandle(_mutex)
    input("按回车退出…")
    sys.exit(1)

# ── Windows 低级钩子（鼠标侧键 + 键盘右Ctrl，完全吞噬原始功能） ──
WH_MOUSE_LL    = 14
WH_KEYBOARD_LL = 13
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP   = 0x020C
WM_KEYDOWN     = 0x0100
WM_KEYUP       = 0x0101
WM_SYSKEYDOWN  = 0x0104
WM_SYSKEYUP    = 0x0105
WM_MBUTTONDOWN = 0x0207
WM_QUIT        = 0x0012
XBUTTON1       = 1       # 鼠标后退键 → 录音触发
XBUTTON2       = 2       # 鼠标前进键 → Enter
VK_RCONTROL    = 0xA3    # 右 Ctrl
LLKHF_UP       = 0x80    # flags 位：key-up

# 需要被接管并吞噬的虚拟键码集合
_TRIGGER_VKS = {VK_RCONTROL}

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          wintypes.POINT),
        ("mouseData",   wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      wintypes.DWORD),
        ("scanCode",    wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

_HOOKPROC           = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, ctypes.c_ulonglong, ctypes.c_longlong)
_mouse_hook_id      = None
_kbd_hook_id        = None
_mouse_hook_ref     = None   # 防 GC
_kbd_hook_ref       = None   # 防 GC
_hook_thread_id     = None   # 钩子线程 ID，用于发送 WM_QUIT
_hooks_installed    = threading.Event()
_hook_install_errors = []

# 为 Win32 API 设置正确的 64 位类型声明，防止指针/句柄被截断为 32 位
_user32 = ctypes.windll.user32
_user32.SetWindowsHookExW.argtypes   = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype    = ctypes.c_void_p
_user32.CallNextHookEx.argtypes      = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ulonglong, ctypes.c_longlong]
_user32.CallNextHookEx.restype       = ctypes.c_longlong
_user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
_user32.UnhookWindowsHookEx.restype  = wintypes.BOOL
_user32.GetMessageW.argtypes         = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
_user32.GetMessageW.restype          = wintypes.BOOL
_user32.TranslateMessage.argtypes    = [ctypes.POINTER(wintypes.MSG)]
_user32.TranslateMessage.restype     = wintypes.BOOL
_user32.DispatchMessageW.argtypes    = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype     = ctypes.c_longlong
_user32.PostThreadMessageW.argtypes  = [wintypes.DWORD, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
_user32.PostThreadMessageW.restype   = wintypes.BOOL

# 钩子回调只往此队列放消息，实际操作由 _action_worker 处理
# 绝不能在钩子回调内做任何耗时操作，否则 Windows 会冻结全局输入
_action_queue: queue.SimpleQueue = queue.SimpleQueue()


# ── 钩子清理（进程退出时自动调用，防止残留钩子冻结输入） ──
def _cleanup_hooks():
    global _mouse_hook_id, _kbd_hook_id
    if _mouse_hook_id:
        _user32.UnhookWindowsHookEx(_mouse_hook_id)
        _mouse_hook_id = None
    if _kbd_hook_id:
        _user32.UnhookWindowsHookEx(_kbd_hook_id)
        _kbd_hook_id = None
    if _hook_thread_id:
        _user32.PostThreadMessageW(_hook_thread_id, WM_QUIT, 0, 0)

atexit.register(_cleanup_hooks)


def _mouse_hook_callback(nCode, wParam, lParam):
    if nCode >= 0:
        # 鼠标中键 → Ctrl+1（截图）
        if wParam == WM_MBUTTONDOWN:
            _action_queue.put('screenshot')
            return 1   # 吞噬中键原始功能（滚轮点击）

        # 鼠标侧键
        if wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            button_id = (ms.mouseData >> 16) & 0xFFFF
            if wParam == WM_XBUTTONDOWN:
                if button_id == XBUTTON1:
                    _action_queue.put('start')
                elif button_id == XBUTTON2:
                    _action_queue.put('enter')
            elif wParam == WM_XBUTTONUP and button_id == XBUTTON1:
                _action_queue.put('stop')
            return 1   # 吞噬：浏览器不收到前进/后退

    return _user32.CallNextHookEx(_mouse_hook_id, nCode, wParam, lParam)


def _kbd_hook_callback(nCode, wParam, lParam):
    if nCode >= 0:
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if kb.vkCode in _TRIGGER_VKS:
            is_up = bool(kb.flags & LLKHF_UP)
            _action_queue.put('stop' if is_up else 'start')
            return 1        # 吞噬：应用不收到 Ctrl 激活菜单等副作用
    return _user32.CallNextHookEx(_kbd_hook_id, nCode, wParam, lParam)


def _run_hooks():
    """在同一线程安装鼠标和键盘两个低级钩子，共享一个消息循环。"""
    global _mouse_hook_id, _kbd_hook_id, _mouse_hook_ref, _kbd_hook_ref, _hook_thread_id
    _hook_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

    _mouse_hook_ref = _HOOKPROC(_mouse_hook_callback)
    _mouse_hook_id  = _user32.SetWindowsHookExW(
        WH_MOUSE_LL, _mouse_hook_ref, None, 0
    )
    if not _mouse_hook_id:
        error = f"鼠标侧键钩子安装失败（错误码 {ctypes.GetLastError()}）"
        _hook_install_errors.append(error)
        print(f"[错误] {error}")

    _kbd_hook_ref = _HOOKPROC(_kbd_hook_callback)
    _kbd_hook_id  = _user32.SetWindowsHookExW(
        WH_KEYBOARD_LL, _kbd_hook_ref, None, 0
    )
    if not _kbd_hook_id:
        error = f"键盘钩子安装失败（错误码 {ctypes.GetLastError()}）"
        _hook_install_errors.append(error)
        print(f"[错误] {error}")

    _hooks_installed.set()
    if _hook_install_errors:
        if _mouse_hook_id:
            _user32.UnhookWindowsHookEx(_mouse_hook_id)
            _mouse_hook_id = None
        if _kbd_hook_id:
            _user32.UnhookWindowsHookEx(_kbd_hook_id)
            _kbd_hook_id = None
        return

    # 消息循环：低级钩子必须有此循环才能持续接收事件
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))

    # 消息循环退出后清理（收到 WM_QUIT 后到达这里）
    if _mouse_hook_id:
        _user32.UnhookWindowsHookEx(_mouse_hook_id)
        _mouse_hook_id = None
    if _kbd_hook_id:
        _user32.UnhookWindowsHookEx(_kbd_hook_id)
        _kbd_hook_id = None


def _dispatch_action(action):
    """分发单个动作；未知动作只报告，不终止 worker。"""
    if action == "start":
        _start_recording()
    elif action == "stop":
        _stop_recording()
    elif action == "enter":
        pyautogui.press("enter")
    elif action == "screenshot":
        pyautogui.hotkey("ctrl", "1")
    else:
        print(f"[错误] 未知动作：{action!r}")


def _action_worker():
    """消费动作队列；单次动作失败后继续处理下一项。"""
    while True:
        action = _action_queue.get()
        try:
            _dispatch_action(action)
        except Exception as exc:  # noqa: BLE001 - worker must survive one failed action
            print(f"[错误] 动作 {action!r} 执行失败：{exc}")
# ──────────────────────────────────────────────────────────────────────────

model       = None
model_ready = threading.Event()
model_load_finished = threading.Event()
model_load_error = None


@dataclass
class RecordingSession:
    """一次录音处理独占的停止信号与后台线程。"""

    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


_recording_lock = threading.Lock()
_active_session: RecordingSession | None = None


def load_model():
    global model, model_load_error
    try:
        from faster_whisper import WhisperModel
        print(f"[加载中] 正在加载 Whisper {MODEL_SIZE} 模型…")
        model = WhisperModel(
            MODEL_SIZE,
            device="cuda",
            compute_type="float16",
            download_root=MODEL_DIR,
            revision=MODEL_REVISION,
        )
        model_ready.set()
        print("[模型] Whisper large-v3 加载完成")
    except Exception as exc:  # noqa: BLE001 - isolate third-party model load failures
        model_load_error = exc
        print(f"[错误] 模型加载失败：{exc}")
    finally:
        model_load_finished.set()


_WHISPER_COMMON = {
    "beam_size": 3,  # 平衡速度与准确率
    "initial_prompt": "以下是中英混合的对话，使用简体中文和英语。",
    "vad_filter": False,  # 手动按键控制边界，VAD 多余且会误裁开头/结尾
    "condition_on_previous_text": False,
}

def _transcribe(audio):
    segments, info = model.transcribe(audio, language=LANGUAGE, **_WHISPER_COMMON)
    # 检测到非中英语言时强制用中文重识别
    if info.language not in ("zh", "en"):
        print(f"[修正] 检测为 {info.language}，强制切换为中文重新识别")
        segments, info = model.transcribe(audio, language="zh", **_WHISPER_COMMON)
    return "".join(seg.text for seg in segments).strip()


def _record_and_transcribe(session):
    frames = []
    print("[录音中] …")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=AUDIO_DTYPE,
        ) as stream:
            while not session.stop_event.is_set():
                data, _ = stream.read(512)
                frames.append(data.copy())
    except Exception as e:  # noqa: BLE001 - sounddevice exposes backend-specific errors
        print(f"[错误] 录音失败: {e}")
        return

    if not frames:
        return

    duration = len(frames) * 512 / SAMPLE_RATE
    if duration < 0.3:
        return

    print(f"[识别中] 音频时长 {duration:.1f}s…")
    audio = np.concatenate(frames).flatten()

    # 音频归一化：拉满到 [-1, 1]，防止轻声说话被模型忽略
    peak = np.max(np.abs(audio))
    if peak > 0.01:
        audio = audio / peak

    if not model_ready.is_set():
        print("[等待] 模型还未加载完成…")
        model_ready.wait()

    try:
        text = _transcribe(audio)
    except Exception as e:  # noqa: BLE001 - transcription backend errors vary by driver
        print(f"[错误] 识别失败: {e}")
        return

    if not text:
        print("[提示] 未识别到文字")
        return

    # 热词修正
    for pattern, repl in HOTWORD_FIXES:
        text = re.sub(pattern, repl, text)

    print(f"[完成] {text}")

    # 保存剪贴板 → 粘贴转写结果 → 恢复剪贴板
    old_clip = pyperclip.paste()
    try:
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
    finally:
        pyperclip.copy(old_clip)


def _release_session(session):
    global _active_session
    with _recording_lock:
        if _active_session is session:
            _active_session = None


def record_and_transcribe(session):
    """录音、识别并粘贴；无论哪一步失败都释放当前 session。"""
    try:
        _record_and_transcribe(session)
    except Exception as exc:  # noqa: BLE001 - always release session after pipeline failure
        print(f"[错误] 录音处理失败：{exc}")
    finally:
        _release_session(session)


def _start_recording():
    global _active_session
    with _recording_lock:
        if _active_session is not None:
            print("[提示] 上一段录音仍在处理中，本次触发已忽略。")
            return
        if not model_ready.is_set():
            print("[提示] 模型加载中，请稍候…")
            return

        session = RecordingSession()
        session.thread = threading.Thread(
            target=record_and_transcribe,
            args=(session,),
            daemon=True,
        )
        _active_session = session
        try:
            session.thread.start()
        except Exception:
            if _active_session is session:
                _active_session = None
            raise


def _stop_recording():
    with _recording_lock:
        session = _active_session
        if session is not None:
            session.stop_event.set()


def main():
    pyautogui.FAILSAFE = False

    print("=" * 50)
    print("  中文语音转文字助手")
    print("  触发键 : 右 Ctrl / 鼠标侧键(后退)")
    print("  前进键 : 鼠标侧键(前进) → Enter")
    print("  中键   : 鼠标中键 → Ctrl+1（截图）")
    print(f"  模型   : Whisper {MODEL_SIZE} (GPU float16)")
    print("  语言   : 自动检测（中/英）")
    print("  用法   : 按住触发键说话，松开自动粘贴")
    print("  注意   : 触发键已被完全接管，不触发任何原始功能")
    print("  退出   : Ctrl+C（左Ctrl+C）")
    print("=" * 50)

    # 先加载模型，加载期间不安装任何全局钩子
    threading.Thread(target=load_model, daemon=True).start()
    model_load_finished.wait()
    if not model_ready.is_set():
        print("[退出] 模型未能加载，不会安装键盘或鼠标钩子。")
        return

    # 启动 action worker（消费队列，执行录音/Enter）
    threading.Thread(target=_action_worker, daemon=True).start()

    # 模型就绪后，安装低级鼠标+键盘钩子，共用一个消息循环
    threading.Thread(target=_run_hooks, daemon=True).start()
    _hooks_installed.wait()
    if _hook_install_errors:
        print("[退出] 全局钩子未完整安装。")
        return
    print("[就绪] 模型与全局钩子均已就绪，按住右Ctrl开始录音")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[退出] 正在清理钩子…")
        _stop_recording()
        _cleanup_hooks()
        time.sleep(0.3)
        sys.exit(0)


if __name__ == "__main__":
    main()
