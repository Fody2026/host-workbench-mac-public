# -*- coding: utf-8 -*-
"""音乐厅：文件夹预览 + 多播放列表 + 曲目参数（起点/淡入淡出/音量/速度/音调）持久化"""
import os
import re
import sys
import json
import html
import urllib.parse
import urllib.request
import shutil
import hashlib
import logging
import subprocess
import ctypes
import ctypes.wintypes

from PySide6.QtCore import Qt, QUrl, QTimer, QSize, QDir, QModelIndex, QMimeData
from PySide6.QtGui import QFont, QAction, QIcon, QKeySequence, QShortcut, QDrag
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox,
    QSlider, QLineEdit, QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGridLayout, QAbstractItemView, QInputDialog, QMenu, QToolButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTreeView, QFileSystemModel,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QApplication,
    QKeySequenceEdit, QGroupBox, QStyle, QProgressDialog
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

import common
import theme
import icons
from common import data_dir, get_setting, set_setting

logger = logging.getLogger(__name__)

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".ape", ".aiff")

DEFAULT_TRACK = dict(title="", start=0.0, fin=0.0, fout=0.0, gain=100, speed=1.0, semi=0)

SHORTCUT_ACTIONS = [
    ("play_pause", "播放 / 暂停", "Space"),
    ("stop", "停止", "Ctrl+."),
    ("prev", "上一首", "Ctrl+Left"),
    ("next", "下一首", "Ctrl+Right"),
    ("vol_up", "音量 +5", "Ctrl+Up"),
    ("vol_down", "音量 -5", "Ctrl+Down"),
    ("mute", "静音 / 恢复", "Ctrl+M"),
    ("seek_back", "后退 5 秒", "Ctrl+Shift+Left"),
    ("seek_fwd", "前进 5 秒", "Ctrl+Shift+Right"),
]
SHORTCUT_ACTIONS_MAP = {a[0]: a for a in SHORTCUT_ACTIONS}


def fmt_ms(ms):
    if not ms or ms <= 0:
        return "00:00"
    s = int(round(ms / 1000))
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_hms(ms):
    if not ms or ms <= 0:
        return "00:00"
    s = int(round(ms / 1000))
    h, m, sec = s // 3600, (s // 60) % 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def audio_duration(path):
    try:
        from mutagen import File
        f = File(path)
        if f is not None and getattr(f, "info", None) is not None:
            return int(f.info.length * 1000)
    except Exception:
        pass
    return 0


def is_audio(path):
    return os.path.isfile(path) and path.lower().endswith(AUDIO_EXTS)


class Library:
    """播放列表 + 曲目参数，统一持久化到 data/music_library.json"""

    def __init__(self):
        self.path = os.path.join(data_dir(), "music_library.json")
        self.lists = [{"name": "默认列表", "items": []}]
        self.settings = {}
        self.current = 0
        self._tag_cache = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                lists = data.get("lists") or []
                self.lists = [l for l in lists if isinstance(l, dict) and "items" in l] or \
                             [{"name": "默认列表", "items": []}]
                self.settings = data.get("settings") or {}
                self.current = int(data.get("current", 0))
                if not (0 <= self.current < len(self.lists)):
                    self.current = 0
            except Exception:
                logger.exception("读取音乐库配置失败")

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"lists": self.lists, "settings": self.settings,
                           "current": self.current}, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("保存音乐库配置失败")

    def tag_title(self, path):
        return read_tag_title(path)

    def track(self, path):
        st = dict(DEFAULT_TRACK)
        st.update(self.settings.get(path, {}))
        return st

    def set_track(self, path, st):
        self.settings[path] = dict(st)
        self.save()


def write_tag_title(path, title):
    """把标题写回音频文件标签，换软件也能看到"""
    title = (title or "").strip()
    if not title:
        return False
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
        if f is None:
            return False
        if f.tags is None:
            f.add_tags()
        f.tags["title"] = title
        f.save()
        return True
    except Exception:
        logger.exception("写入歌曲标题失败: %s", path)
        return False


_TAG_CACHE = {}


def read_tag_title(path):
    if path in _TAG_CACHE:
        return _TAG_CACHE[path]
    title = ""
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
        if f is not None and getattr(f, "tags", None):
            v = f.tags.get("title")
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ""
            title = str(v or "").strip()
    except Exception:
        title = ""
    _TAG_CACHE[path] = title
    return title


# ============================================================
#  曲目参数对话框
# ============================================================
class TrackDialog(QDialog):
    def __init__(self, path, st, pos_ms=0, parent=None):
        super().__init__(parent)
        self._path = path
        self.setWindowTitle("曲目设置 · " + os.path.basename(path))
        self.setMinimumWidth(430)
        st = dict(st)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        tip = QLabel("这些参数会保存在曲目上，下次播放同一首时自动生效（不修改原文件）。")
        tip.setWordWrap(True)
        tip.setObjectName("SubTitle")
        lay.addWidget(tip)

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)

        g.addWidget(QLabel("播放列表标题"), 0, 0)
        self.ed_title = QLineEdit(st.get("title") or read_tag_title(path) or os.path.splitext(os.path.basename(path))[0])
        self.ed_title.setPlaceholderText("播放列表里显示的名字，不会改文件名")
        g.addWidget(self.ed_title, 0, 1)
        g.addWidget(QLabel("原文件名："), 1, 0)
        lb_file = QLabel(os.path.basename(path))
        lb_file.setObjectName("SubTitle")
        lb_file.setWordWrap(True)
        g.addWidget(lb_file, 1, 1)
        g.addWidget(QLabel("起始播放点（秒）"), 2, 0)
        row0 = QHBoxLayout()
        self.sp_start = QDoubleSpinBox()
        self.sp_start.setRange(0, 36000)
        self.sp_start.setDecimals(1)
        self.sp_start.setValue(st.get("start", 0.0))
        self.sp_start.setSuffix(" s")
        b_pos = QPushButton("取当前播放位置")
        b_pos.clicked.connect(lambda: self.sp_start.setValue(pos_ms / 1000.0))
        row0.addWidget(self.sp_start, 1)
        row0.addWidget(b_pos)
        g.addLayout(row0, 2, 1)

        g.addWidget(QLabel("淡入（秒）"), 3, 0)
        row1 = QHBoxLayout()
        self.sp_fin = QDoubleSpinBox()
        self.sp_fin.setRange(0, 30)
        self.sp_fin.setDecimals(1)
        self.sp_fin.setValue(st.get("fin", 0.0))
        self.sp_fout = QDoubleSpinBox()
        self.sp_fout.setRange(0, 30)
        self.sp_fout.setDecimals(1)
        self.sp_fout.setValue(st.get("fout", 0.0))
        row1.addWidget(self.sp_fin, 1)
        row1.addWidget(QLabel("淡出"))
        row1.addWidget(self.sp_fout, 1)
        g.addLayout(row1, 3, 1)

        g.addWidget(QLabel("单独音量（%）"), 4, 0)
        row2 = QHBoxLayout()
        self.sl_gain = QSlider(Qt.Horizontal)
        self.sl_gain.setRange(0, 100)
        self.sl_gain.setValue(int(st.get("gain", 100)))
        self.lb_gain = QLabel(f"{int(st.get('gain', 100))}%")
        self.lb_gain.setFixedWidth(44)
        self.sl_gain.valueChanged.connect(lambda v: self.lb_gain.setText(f"{v}%"))
        row2.addWidget(self.sl_gain, 1)
        row2.addWidget(self.lb_gain)
        g.addLayout(row2, 4, 1)

        g.addWidget(QLabel("播放速度"), 5, 0)
        self.sp_speed = DragDoubleSpinBox()
        self.sp_speed.setRange(0.5, 2.0)
        self.sp_speed.setSingleStep(0.05)
        self.sp_speed.setDecimals(2)
        self.sp_speed.setValue(st.get("speed", 1.0))
        self.sp_speed.setSuffix(" x")
        g.addWidget(self.sp_speed, 5, 1)

        lay.addLayout(g)

        btns = QHBoxLayout()
        b_reset = QPushButton("恢复默认")
        b_reset.clicked.connect(self._reset)
        btns.addWidget(b_reset)
        btns.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("保存")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        btns.addWidget(box)
        lay.addLayout(btns)

    def _reset(self):
        self.ed_title.setText(os.path.basename(self._path))
        self.sp_start.setValue(0)
        self.sp_fin.setValue(0)
        self.sp_fout.setValue(0)
        self.sl_gain.setValue(100)
        self.sp_speed.setValue(1.0)

    def value(self):
        return dict(title=self.ed_title.text().strip() or os.path.basename(self._path),
                    start=round(self.sp_start.value(), 1),
                    fin=round(self.sp_fin.value(), 1),
                    fout=round(self.sp_fout.value(), 1),
                    gain=int(self.sl_gain.value()),
                    speed=round(self.sp_speed.value(), 2))


# ============================================================
#  音乐厅页面
# ============================================================
class JumpSlider(QSlider):
    """点击/拖动进度条任意位置都能直接跳转，而不是按页步进"""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setTracking(True)

    def _value_at(self, x):
        if self.maximum() <= self.minimum():
            return self.minimum()
        span = max(1, self.width() - 1)
        x = max(0, min(int(x), span))
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, span)

    def _jump(self, x):
        v = self._value_at(x)
        if v != self.value():
            self.setValue(v)
        self.sliderMoved.emit(v)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setSliderDown(True)
            self._jump(e.position().x())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.isSliderDown() and (e.buttons() & Qt.LeftButton):
            self._jump(e.position().x())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.isSliderDown():
            self._jump(e.position().x())
            self.setSliderDown(False)
            e.accept()
            return
        super().mouseReleaseEvent(e)


class DragDoubleSpinBox(QDoubleSpinBox):
    """在数值区按住左键上下滑动即可调整"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._y0 = 0.0
        self._v0 = 0.0
        self.setToolTip("按住数值上下滑动可快速调整")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < self.height() * 0.75:
            self._dragging = True
            self._y0 = e.position().y()
            self._v0 = self.value()
            self.setCursor(Qt.SizeVerCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            dy = self._y0 - e.position().y()
            step = self.singleStep() or 0.01
            v = self._v0 + dy * max(step, 0.01) * 1.6
            self.setValue(max(self.minimum(), min(self.maximum(), v)))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)


class DragSpinBox(QSpinBox):
    """整数版：按住数值上下滑动调整"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._y0 = 0.0
        self._v0 = 0
        self.setToolTip("按住数值上下滑动可快速调整")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < self.height() * 0.75:
            self._dragging = True
            self._y0 = e.position().y()
            self._v0 = self.value()
            self.setCursor(Qt.SizeVerCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            dy = self._y0 - e.position().y()
            self.setValue(max(self.minimum(), min(self.maximum(),
                                                 self._v0 + int(dy / 6))))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)


class PlayTable(QTableWidget):
    """可接收文件拖拽、也能把曲目拖到左侧播放列表"""

    MIME = "application/x-pengfei-tracks"

    def __init__(self, page, parent=None):
        super().__init__(0, 3, parent)
        self.page = page
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def startDrag(self, supported_actions):
        rows = sorted({i.row() for i in self.selectedIndexes()})
        if not rows:
            return
        paths = []
        lst = self.page.lib.lists[self.page.lib.current]
        for r in rows:
            if 0 <= r < len(lst["items"]):
                paths.append(lst["items"][r])
        if not paths:
            return
        mime = QMimeData()
        mime.setData(self.MIME, json.dumps({"from": self.page.lib.current, "paths": paths}).encode("utf-8"))
        mime.setText("\n".join(paths))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction | Qt.CopyAction)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.page.add_to_list(paths)
                e.acceptProposedAction()
            return
        if e.mimeData().hasFormat(self.MIME):
            e.ignore()
            return
        super().dropEvent(e)


class PlaylistList(QListWidget):
    """左侧播放列表：接收曲目拖拽，可直接把歌曲移到这个列表"""

    MIME = "application/x-pengfei-tracks"

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        row = idx.row() if idx.isValid() else self.count() - 1
        if e.mimeData().hasFormat(self.MIME):
            try:
                data = json.loads(bytes(e.mimeData().data(self.MIME)).decode("utf-8"))
                self.page.drop_tracks_to_list(data.get("paths") or [], row)
                e.acceptProposedAction()
            except Exception:
                e.ignore()
            return
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.page.drop_tracks_to_list(paths, row, external=True)
                e.acceptProposedAction()
            return
        super().dropEvent(e)


class HotkeyListener(QWidget):
    """Windows 全局热键：用隐藏窗口接收 WM_HOTKEY"""
    def __init__(self, parent=None):
        super().__init__(None)
        from PySide6.QtCore import Signal
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.resize(1, 1)
        self._callbacks = {}
        self._next = 0xB100
        try:
            self._hwnd = int(self.winId())
        except Exception:
            self._hwnd = 0

    @staticmethod
    def _vk(key):
        if Qt.Key_A <= key <= Qt.Key_Z:
            return int(key)
        if Qt.Key_0 <= key <= Qt.Key_9:
            return int(key)
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return 0x70 + (int(key) - int(Qt.Key_F1))
        table = {
            Qt.Key_Space: 0x20, Qt.Key_Return: 0x0D, Qt.Key_Enter: 0x0D,
            Qt.Key_Escape: 0x1B, Qt.Key_Tab: 0x09, Qt.Key_Backspace: 0x08,
            Qt.Key_Delete: 0x2E, Qt.Key_Insert: 0x2D,
            Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28,
            Qt.Key_Home: 0x24, Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
            Qt.Key_Comma: 0xBC, Qt.Key_Period: 0xBE, Qt.Key_Slash: 0xBF,
            Qt.Key_Semicolon: 0xBA, Qt.Key_Apostrophe: 0xDE,
            Qt.Key_BracketLeft: 0xDB, Qt.Key_BracketRight: 0xDD,
            Qt.Key_Backslash: 0xDC, Qt.Key_Minus: 0xBD, Qt.Key_Equal: 0xBB,
        }
        return table.get(key)

    def register(self, sequence, callback):
        try:
            seq = QKeySequence(sequence)
            if seq.isEmpty():
                return None
            combo = seq[0]
            vk = self._vk(combo.key())
            if not vk:
                return None
            mods = 0
            m = combo.keyboardModifiers()
            if m & Qt.ControlModifier:
                mods |= 0x0002
            if m & Qt.AltModifier:
                mods |= 0x0001
            if m & Qt.ShiftModifier:
                mods |= 0x0004
            if m & Qt.MetaModifier:
                mods |= 0x0008
            hid = self._hwnd
            if not hid:
                return None
            self._next += 1
            hk = self._next
            ok = ctypes.windll.user32.RegisterHotKey(hid, hk, mods, vk)
            if not ok:
                return None
            self._callbacks[hk] = callback
            return hk
        except Exception:
            return None

    def unregister(self, hk):
        try:
            ctypes.windll.user32.UnregisterHotKey(self._hwnd, int(hk))
        except Exception:
            pass
        self._callbacks.pop(hk, None)

    def unregister_all(self):
        for hk in list(self._callbacks):
            self.unregister(hk)

    def nativeEvent(self, event_type, message):
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:
                    cb = self._callbacks.get(int(msg.wParam))
                    if cb:
                        cb()
                        return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", ctypes.wintypes.DWORD),
                ("scanCode", ctypes.wintypes.DWORD),
                ("flags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class MediaKeyHook:
    """诺为 N61 司仪宝（模式1）的上一曲/播放暂停/下一曲媒体键全局接管。
    低层键盘钩子只拦截多媒体键，不影响正常键盘和翻页笔。"""

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    MAP = {
        0xB1: "prev",       # VK_MEDIA_PREV_TRACK
        0xB0: "next",       # VK_MEDIA_NEXT_TRACK
        0xB3: "play_pause", # VK_MEDIA_PLAY_PAUSE
        0xB2: "stop",       # VK_MEDIA_STOP
    }

    def __init__(self, on_action):
        self.on_action = on_action
        self.hook = None
        self.proc = None
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                          ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                                 ctypes.c_void_p, ctypes.wintypes.DWORD]
            self._user32 = user32
            self._kernel32 = kernel32
            self.proc = HOOKPROC(self._callback)
            hmod = kernel32.GetModuleHandleW(None)
            self.hook = user32.SetWindowsHookExW(13, self.proc, hmod, 0)
            if not self.hook:
                err = ctypes.get_last_error()
                logger.warning("司仪宝媒体键钩子安装失败: %s", err)
        except Exception:
            logger.exception("安装司仪宝媒体键钩子异常")

    def _callback(self, nCode, wParam, lParam):
        try:
            if nCode == 0:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                action = self.MAP.get(int(kb.vkCode))
                if action:
                    if wParam in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN):
                        QTimer.singleShot(0, lambda a=action: self.on_action(a))
                    return 1
        except Exception:
            pass
        try:
            return self._user32.CallNextHookEx(None, nCode, wParam, lParam)
        except Exception:
            return 0

    def uninstall(self):
        try:
            if self.hook:
                self._user32.UnhookWindowsHookEx(self.hook)
        except Exception:
            pass
        self.hook = None


class ShortcutDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setMinimumWidth(620)
        self.cfg = {k: dict(v) for k, v in cfg.items()}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        tip = QLabel("勾选「全局」后，软件最小化或在后台也能用；不勾选则只在软件窗口激活时生效。\n"
                     "全局热键会占用系统组合键，设置失败会自动退回软件内快捷键。\n"
                     "诺为 N61 司仪宝：接收器 Mode 切到「模式1」，上一曲/播放暂停/下一曲会自动接管，无需再设快捷键。")
        tip.setObjectName("SubTitle")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        box = QGroupBox("播放快捷键")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for col, text in enumerate(("功能", "快捷键", "全局", "")):
            lb = QLabel(text)
            lb.setObjectName("SubTitle")
            grid.addWidget(lb, 0, col)
        self.rows = {}
        for i, (key, label, default) in enumerate(SHORTCUT_ACTIONS, start=1):
            cur = self.cfg.get(key) or {"seq": default, "global": False}
            grid.addWidget(QLabel(label), i, 0)
            edit = QKeySequenceEdit(QKeySequence(cur.get("seq", default)))
            grid.addWidget(edit, i, 1)
            chk = QCheckBox("全局")
            chk.setChecked(bool(cur.get("global")))
            grid.addWidget(chk, i, 2)
            b_clear = QPushButton("清除")
            b_clear.setMinimumWidth(64)
            b_clear.clicked.connect(edit.clear)
            grid.addWidget(b_clear, i, 3)
            self.rows[key] = (edit, chk)
        lay.addWidget(box)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b_reset = QPushButton("恢复默认")
        bb.addButton(b_reset, QDialogButtonBox.ResetRole)
        b_reset.clicked.connect(self.reset)
        bb.button(QDialogButtonBox.Ok).setText("保存并应用")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def reset(self):
        for key, label, default in SHORTCUT_ACTIONS:
            edit, chk = self.rows[key]
            edit.setKeySequence(QKeySequence(default))
            chk.setChecked(False)

    def _ok(self):
        seen = {}
        for key, label, default in SHORTCUT_ACTIONS:
            edit, chk = self.rows[key]
            seq = edit.keySequence().toString(QKeySequence.PortableText).strip()
            if seq:
                if seq in seen:
                    QMessageBox.warning(self, "快捷键重复",
                                        f"「{label}」和「{SHORTCUT_ACTIONS_MAP[seen[seq]][1]}」都是 {seq}，请改一个。")
                    return
                seen[seq] = key
        for key, label, default in SHORTCUT_ACTIONS:
            edit, chk = self.rows[key]
            self.cfg[key] = {
                "seq": edit.keySequence().toString(QKeySequence.PortableText).strip(),
                "global": bool(chk.isChecked()),
            }
        self.accept()

    def result_cfg(self):
        return self.cfg


class MusicSearchDialog(QDialog):
    """在线搜索 + 下载，保存到可配置目录"""

    def __init__(self, on_done=None, parent=None):
        super().__init__(parent)
        self.on_done = on_done
        self.rows = []
        self._url_cache = {}
        self.setWindowTitle("音乐搜索 / 下载")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.ed_kw = QLineEdit()
        self.ed_kw.setPlaceholderText("输入歌名 / 歌手，回车搜索")
        self.ed_kw.returnPressed.connect(self.search)
        b_search = QPushButton("搜索")
        b_search.setObjectName("Primary")
        b_search.clicked.connect(self.search)
        top.addWidget(self.ed_kw, 1)
        top.addWidget(b_search)
        lay.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["歌名", "歌手", "专辑", "时长"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _: self.download())
        lay.addWidget(self.table, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.errorOccurred.connect(lambda *_: self.lb_msg.setText("试听失败，换一首试试"))
        pv = QHBoxLayout()
        self.b_play = QPushButton("▶ 试听")
        self.b_play.setFixedWidth(86)
        self.b_play.clicked.connect(self._toggle_preview)
        pv.addWidget(self.b_play)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._seek)
        pv.addWidget(self.slider, 1)
        self.lb_time = QLabel("00:00 / 00:00")
        self.lb_time.setObjectName("SubTitle")
        pv.addWidget(self.lb_time)
        lay.addLayout(pv)
        self.table.currentCellChanged.connect(lambda r, c, pr, pc: self._preview(r))
        row = QHBoxLayout()
        row.addWidget(QLabel("保存到"))
        self.ed_dir = QLineEdit(get_setting("music_download_dir", os.path.join(data_dir(), "下载音乐")))
        b_dir = QPushButton("选择…")
        b_dir.clicked.connect(self.pick_dir)
        row.addWidget(self.ed_dir, 1)
        row.addWidget(b_dir)
        lay.addLayout(row)
        bottom = QHBoxLayout()
        self.lb_msg = QLabel("")
        self.lb_msg.setObjectName("SubTitle")
        bottom.addWidget(self.lb_msg, 1)
        b_dl = QPushButton("下载选中")
        b_dl.setObjectName("Primary")
        b_dl.clicked.connect(self.download)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.accept)
        bottom.addWidget(b_dl)
        bottom.addWidget(b_close)
        lay.addLayout(bottom)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择下载目录", self.ed_dir.text() or data_dir())
        if d:
            self.ed_dir.setText(d)
            set_setting("music_download_dir", d)

    def search(self):
        kw = self.ed_kw.text().strip()
        if not kw:
            return
        self.lb_msg.setText("搜索中…")
        QApplication.processEvents()
        url = ("http://search.kuwo.cn/r.s?all=" + urllib.parse.quote(kw) +
               "&ft=music&itemset=web_2013&client=kt&pn=0&rn=30&rformat=json&encoding=utf8")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
        except Exception as exc:
            self.lb_msg.setText("搜索失败：" + str(exc))
            return
        self.rows = []
        try:
            data = json.loads(raw.replace("'", '"'))
            items = data.get("abslist") or []
        except Exception:
            items = []
        for it in items:
            rid = str(it.get("MUSICRID") or "").replace("MUSIC_", "")
            if not rid:
                continue
            self.rows.append({
                "rid": rid,
                "name": html.unescape(str(it.get("SONGNAME") or "")),
                "artist": html.unescape(str(it.get("ARTIST") or "")),
                "album": html.unescape(str(it.get("ALBUM") or "")),
                "duration": str(it.get("DURATION") or ""),
            })
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["artist"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["album"]))
            self.table.setItem(i, 3, QTableWidgetItem(r["duration"]))
        self.table.resizeRowsToContents()
        self.lb_msg.setText(f"找到 {len(self.rows)} 首")

    def _resolve_url(self, row):
        if row in self._url_cache:
            return self._url_cache[row]
        item = self.rows[row]
        api = ("http://antiserver.kuwo.cn/anti.s?type=convert_url&format=mp3&response=url&rid=MUSIC_"
               + item["rid"])
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        src = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore").strip().splitlines()[0]
        if not src.startswith("http"):
            raise RuntimeError("no url")
        self._url_cache[row] = src
        return src

    def _preview(self, row):
        if not (0 <= row < len(self.rows)):
            return
        self.lb_msg.setText("加载试听…")
        QApplication.processEvents()
        try:
            src = self._resolve_url(row)
            self.player.setSource(QUrl(src))
            self.player.play()
            self.b_play.setText("⏸ 暂停")
            self.lb_msg.setText(self.rows[row]["name"] + " · " + self.rows[row]["artist"])
        except Exception as exc:
            self.lb_msg.setText("试听失败：" + str(exc))

    def _toggle_preview(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.b_play.setText("▶ 试听")
        elif self.player.source().isEmpty():
            self._preview(self.table.currentRow())
        else:
            self.player.play()
            self.b_play.setText("⏸ 暂停")

    def _fmt(self, ms):
        s = max(0, int(ms // 1000))
        return "%02d:%02d" % (s // 60, s % 60)

    def _on_pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.lb_time.setText(self._fmt(pos) + " / " + self._fmt(self.player.duration()))

    def _on_dur(self, dur):
        self.slider.setRange(0, max(0, dur))
        self.lb_time.setText("00:00 / " + self._fmt(dur))

    def _seek(self, val):
        self.player.setPosition(int(val))

    def download(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self.rows)):
            self.lb_msg.setText("先选一首歌")
            return
        item = self.rows[row]
        d = self.ed_dir.text().strip() or os.path.join(data_dir(), "下载音乐")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as exc:
            self.lb_msg.setText("目录不可用：" + str(exc))
            return
        set_setting("music_download_dir", d)
        safe = re.sub(r'[\\/:*?"<>|]+', "_", f"{item['artist']} - {item['name']}").strip()
        path = os.path.join(d, safe + ".mp3")
        n = 1
        while os.path.exists(path):
            path = os.path.join(d, f"{safe} ({n}).mp3")
            n += 1
        try:
            api = ("http://antiserver.kuwo.cn/anti.s?type=convert_url&format=mp3&response=url&rid=MUSIC_"
                   + item["rid"])
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            src = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore").strip().split("\n")[0]
            if not src.startswith("http"):
                self.lb_msg.setText("拿不到下载地址，换个源试试")
                return
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=20)
            total = int(resp.headers.get("Content-Length") or 0)
            dlg = QProgressDialog("下载中…", "取消", 0, max(1, total), self)
            dlg.setWindowTitle(item["name"])
            dlg.setWindowModality(Qt.WindowModal)
            dlg.show()
            got = 0
            with open(path, "wb") as fh:
                while True:
                    if dlg.wasCanceled():
                        break
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        dlg.setValue(got)
                    QApplication.processEvents()
            dlg.close()
            if got <= 0:
                try: os.remove(path)
                except OSError: pass
                self.lb_msg.setText("下载失败")
                return
            self.lb_msg.setText("已下载：" + os.path.basename(path))
            if self.on_done:
                self.on_done(path)
        except Exception as exc:
            self.lb_msg.setText("下载失败：" + str(exc))
            try:
                if os.path.exists(path) and os.path.getsize(path) == 0:
                    os.remove(path)
            except OSError:
                pass

class LegalMusicDialog(QDialog):
    """Jamendo 正版/CC 曲库：需要免费 Client ID"""

    def __init__(self, on_done=None, parent=None):
        super().__init__(parent)
        self.on_done = on_done
        self.rows = []
        self.setWindowTitle("正版曲库 · Jamendo")
        self.resize(860, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.ed_cid = QLineEdit(get_setting("jamendo_client_id", ""))
        self.ed_cid.setPlaceholderText("Jamendo Client ID（免费注册 developer.jamendo.com）")
        self.ed_kw = QLineEdit()
        self.ed_kw.setPlaceholderText("搜索正版/CC 音乐，回车")
        self.ed_kw.returnPressed.connect(self.search)
        b_search = QPushButton("搜索")
        b_search.setObjectName("Primary")
        b_search.clicked.connect(self.search)
        top.addWidget(self.ed_cid, 2)
        top.addWidget(self.ed_kw, 2)
        top.addWidget(b_search)
        lay.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["歌名", "艺人", "时长", "许可"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        pv = QHBoxLayout()
        self.b_play = QPushButton("▶ 试听")
        self.b_play.setFixedWidth(86)
        self.b_play.clicked.connect(self._toggle)
        pv.addWidget(self.b_play)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(int(v)))
        pv.addWidget(self.slider, 1)
        self.lb_time = QLabel("00:00 / 00:00")
        self.lb_time.setObjectName("SubTitle")
        pv.addWidget(self.lb_time)
        lay.addLayout(pv)
        self.table.currentCellChanged.connect(lambda r, c, pr, pc: self._preview(r))
        row = QHBoxLayout()
        self.lb_msg = QLabel("")
        self.lb_msg.setObjectName("SubTitle")
        row.addWidget(self.lb_msg, 1)
        b_dl = QPushButton("下载选中")
        b_dl.setObjectName("Primary")
        b_dl.clicked.connect(self.download)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_dl)
        row.addWidget(b_close)
        lay.addLayout(row)
        tip = QLabel("说明：Jamendo 曲目为 CC/正版授权，使用前请点「许可」确认是否允许商业播放；"
                     "主流流行歌曲需要平台授权，无法通过公开接口下载。")
        tip.setObjectName("SubTitle")
        tip.setWordWrap(True)
        lay.addWidget(tip)

    def search(self):
        cid = self.ed_cid.text().strip()
        kw = self.ed_kw.text().strip()
        if not cid:
            self.lb_msg.setText("先填 Jamendo Client ID")
            return
        set_setting("jamendo_client_id", cid)
        self.lb_msg.setText("搜索中…")
        QApplication.processEvents()
        url = ("https://api.jamendo.com/v3.0/tracks/?client_id=" + urllib.parse.quote(cid) +
               "&format=json&limit=30&search=" + urllib.parse.quote(kw) +
               "&audioformat=mp32&include=licenses")
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                         timeout=15).read().decode("utf-8", "ignore")
            data = json.loads(raw)
        except Exception as exc:
            self.lb_msg.setText("搜索失败：" + str(exc))
            return
        self.rows = data.get("results") or []
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(r.get("name") or "")))
            self.table.setItem(i, 1, QTableWidgetItem(str(r.get("artist_name") or "")))
            self.table.setItem(i, 2, QTableWidgetItem(self._fmt(int(r.get("duration") or 0) * 1000)))
            lic = str(r.get("license_ccurl") or "")
            self.table.setItem(i, 3, QTableWidgetItem(lic.split("/")[-1] if lic else "CC"))
        self.lb_msg.setText(f"找到 {len(self.rows)} 首正版/CC 曲目")

    def _fmt(self, ms):
        s = max(0, int(ms // 1000))
        return "%02d:%02d" % (s // 60, s % 60)

    def _preview(self, row):
        if not (0 <= row < len(self.rows)):
            return
        src = self.rows[row].get("audio") or ""
        if not src:
            self.lb_msg.setText("这首没有试听地址")
            return
        self.player.setSource(QUrl(src))
        self.player.play()
        self.b_play.setText("⏸ 暂停")

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause(); self.b_play.setText("▶ 试听")
        elif self.player.source().isEmpty():
            self._preview(self.table.currentRow())
        else:
            self.player.play(); self.b_play.setText("⏸ 暂停")

    def _on_pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.lb_time.setText(self._fmt(pos) + " / " + self._fmt(self.player.duration()))

    def _on_dur(self, dur):
        self.slider.setRange(0, max(0, dur))

    def download(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self.rows)):
            self.lb_msg.setText("先选一首")
            return
        r = self.rows[row]
        src = r.get("audiodownload") or r.get("audio")
        if not src:
            self.lb_msg.setText("没有下载地址")
            return
        d = get_setting("music_download_dir", os.path.join(data_dir(), "下载音乐"))
        os.makedirs(d, exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|]+', "_", f"{r.get('artist_name','')} - {r.get('name','')}").strip()
        path = os.path.join(d, safe + ".mp3")
        try:
            resp = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"}), timeout=25)
            with open(path, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            self.lb_msg.setText("已下载：" + os.path.basename(path))
            if self.on_done:
                self.on_done(path)
        except Exception as exc:
            self.lb_msg.setText("下载失败：" + str(exc))

class MusicPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lib = Library()
        self.cur_path = ""
        self.cur_row = -1
        self.master_vol = 70
        self.cur_gain = 100
        self._pending = {}
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)
        self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_target = 1.0
        self._fade_dir = 1
        self._fade_total = 0
        self._fade_elapsed = 0
        self._after_fade = None
        self._clip_files = None      # (mode, [paths])
        self._clip_list = None       # (list dict)
        self._dur_cache = {}
        self._pitch_jobs = 0
        self.hotkey = HotkeyListener()
        self._local_shortcuts = []
        self._global_ids = []
        self._shortcut_cfg = self._load_shortcut_cfg()
        self._build_ui()
        self._init_player()
        self.media_hook = MediaKeyHook(self._on_media_key)
        self._load_lists()
        self._set_root(get_setting("music_dir", "") or os.path.join(data_dir(), "music"))
        self._load_tracks()
        self._apply_shortcuts(self._shortcut_cfg, silent=True)

    # ---------- 播放器 ----------
    def _init_player(self):
        self.audio = QAudioOutput(self)
        try:
            self.master_vol = int(get_setting("music_volume", "70"))
        except Exception:
            self.master_vol = 70
        self.audio.setVolume(self.master_vol / 100)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)
        self.sl_vol.setValue(self.master_vol)

    # ---------- UI ----------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # 顶部工具条
        head = QHBoxLayout()
        head.setSpacing(8)
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("音乐播放器")
        title.setObjectName("Title")
        sub = QLabel("本地音乐 · 多播放列表 · 司仪宝遥控 · 曲目参数记忆")
        sub.setObjectName("SubTitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox)
        head.addStretch()
        b_legal = QPushButton("正版曲库(Jamendo)")
        b_legal.setToolTip("CC/正版授权曲库，需要免费 Jamendo Client ID")
        b_legal.clicked.connect(self.open_legal)
        head.addWidget(b_legal)
        b_search = QPushButton("音乐搜索/下载")
        b_search.setToolTip("在线搜索歌曲并下载到指定目录，下载后可直接加入当前列表")
        b_search.clicked.connect(self.open_search)
        head.addWidget(b_search)
        b_add = QPushButton("添加文件")
        b_add.setIcon(icons.icon("add", 18))
        b_add.clicked.connect(self.add_files)
        b_folder = QPushButton("添加文件夹")
        b_folder.setIcon(icons.icon("folder", 18))
        b_folder.clicked.connect(self.add_folder)
        b_refresh = QPushButton("刷新")
        b_refresh.clicked.connect(self.refresh)
        b_saveproj = QPushButton("保存列表")
        b_saveproj.setToolTip("把当前所有播放列表与曲目参数保存为工程文件")
        b_saveproj.clicked.connect(self.save_project)
        b_loadproj = QPushButton("加载列表")
        b_loadproj.setToolTip("加载之前保存的列表工程，一键恢复排版")
        b_loadproj.clicked.connect(self.load_project)
        b_keys = QPushButton("快捷键设置")
        b_keys.setToolTip("设置播放快捷键，可勾选为全局快捷键（软件在后台也能用）")
        b_keys.clicked.connect(self.open_shortcuts)
        head.addWidget(b_add)
        head.addWidget(b_folder)
        head.addWidget(b_refresh)
        head.addWidget(b_saveproj)
        head.addWidget(b_loadproj)
        head.addWidget(b_keys)
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(10)

        # ① 播放列表栏
        pl_card = QFrame()
        pl_card.setObjectName("Card")
        pl_card.setFixedWidth(186)
        pv = QVBoxLayout(pl_card)
        pv.setContentsMargins(12, 12, 12, 12)
        pv.setSpacing(8)
        prow = QHBoxLayout()
        lb_pl = QLabel("播放列表")
        lb_pl.setObjectName("SectionTitle")
        b_newlist = QPushButton()
        b_newlist.setIcon(icons.icon("add", 16))
        b_newlist.setFixedSize(28, 26)
        b_newlist.setToolTip("新建播放列表")
        b_newlist.clicked.connect(self.new_list)
        prow.addWidget(lb_pl, 1)
        prow.addWidget(b_newlist)
        pv.addLayout(prow)
        self.list_lists = PlaylistList(self)
        self.list_lists.setObjectName("Plain")
        self.list_lists.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_lists.customContextMenuRequested.connect(self._list_menu)
        self.list_lists.currentRowChanged.connect(self._switch_list)
        pv.addWidget(self.list_lists, 1)
        self.lb_pl_count = QLabel("")
        self.lb_pl_count.setObjectName("SubTitle")
        pv.addWidget(self.lb_pl_count)

        # ② 音乐文件夹预览
        fs_card = QFrame()
        fs_card.setObjectName("CardAlt")
        fs_card.setFixedWidth(252)
        fv = QVBoxLayout(fs_card)
        fv.setContentsMargins(12, 12, 12, 12)
        fv.setSpacing(8)
        frow = QHBoxLayout()
        lb_fs = QLabel("音乐文件")
        lb_fs.setObjectName("SectionTitle")
        b_dir = QPushButton()
        b_dir.setIcon(icons.icon("folder", 16))
        b_dir.setFixedSize(28, 26)
        b_dir.setToolTip("选择音乐库目录")
        b_dir.clicked.connect(self.pick_dir)
        frow.addWidget(lb_fs, 1)
        frow.addWidget(b_dir)
        fv.addLayout(frow)
        self.tree = QTreeView()
        self.tree.setObjectName("Plain")
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragOnly)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._file_menu)
        self.tree.doubleClicked.connect(self._tree_play)
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Files)
        self.fs_model.setNameFilters(["*" + e for e in AUDIO_EXTS])
        self.fs_model.setNameFilterDisables(False)
        self.tree.setModel(self.fs_model)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        fv.addWidget(self.tree, 1)
        self.lb_dir = QLabel("")
        self.lb_dir.setObjectName("SubTitle")
        self.lb_dir.setWordWrap(True)
        fv.addWidget(self.lb_dir)

        body.addWidget(fs_card)
        body.addWidget(pl_card)

        # ③ 曲目表
        mid = QVBoxLayout()
        mid.setSpacing(10)
        tr_card = QFrame()
        tr_card.setObjectName("Card")
        tv = QVBoxLayout(tr_card)
        tv.setContentsMargins(14, 12, 14, 12)
        tv.setSpacing(8)
        trow = QHBoxLayout()
        self.lb_cur_list = QLabel("默认列表")
        self.lb_cur_list.setObjectName("SectionTitle")
        self.lb_cur_list.setMinimumWidth(120)
        b_del = QPushButton("移除")
        b_del.clicked.connect(self.remove_selected)
        b_up = QPushButton("上移")
        b_up.clicked.connect(lambda: self.move_selected(-1))
        b_down = QPushButton("下移")
        b_down.clicked.connect(lambda: self.move_selected(1))
        b_cfg = QPushButton("曲目设置")
        b_cfg.setObjectName("Primary")
        b_cfg.clicked.connect(self.edit_selected_track)
        trow.addWidget(self.lb_cur_list, 1)
        trow.addWidget(b_del)
        trow.addWidget(b_up)
        trow.addWidget(b_down)
        trow.addWidget(b_cfg)
        tv.addLayout(trow)

        self.table = PlayTable(self)
        self.table.setObjectName("PlayTable")
        self.table.setHorizontalHeaderLabels(["#", "曲目", "时长"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DropOnly)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._track_menu)
        self.table.doubleClicked.connect(self._table_play)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(2, 76)
        tv.addWidget(self.table, 1)
        hint = QLabel("从左侧文件树把曲目拖到这里，或双击文件直接播放；右键曲目可设置起点、淡入淡出、音量、速度与音调。")
        hint.setObjectName("SubTitle")
        hint.setWordWrap(True)
        tv.addWidget(hint)
        mid.addWidget(tr_card, 1)
        body.addLayout(mid, 1)
        lay.addLayout(body, 1)

        # 底部控制条
        ctl = QFrame()
        ctl.setObjectName("PlayerBar")
        cv = QVBoxLayout(ctl)
        cv.setContentsMargins(16, 10, 16, 12)
        cv.setSpacing(8)

        row_prog = QHBoxLayout()
        self.lb_cur = QLabel("00:00")
        self.lb_cur.setFixedWidth(52)
        self.slider = JumpSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self._seek)
        self.lb_dur = QLabel("00:00")
        self.lb_dur.setFixedWidth(52)
        row_prog.addWidget(self.lb_cur)
        row_prog.addWidget(self.slider, 1)
        row_prog.addWidget(self.lb_dur)
        cv.addLayout(row_prog)

        row_ctl = QHBoxLayout()
        row_ctl.setSpacing(8)
        b_prev = QPushButton()
        b_prev.setIcon(icons.icon("prev", 20))
        b_prev.setFixedSize(38, 34)
        b_prev.setToolTip("上一首")
        b_prev.clicked.connect(self.play_prev)
        self.b_play = QPushButton()
        self.b_play.setObjectName("Primary")
        self.b_play.setFixedSize(52, 36)
        self.b_play.setIcon(icons.icon("play", 22, "#14161B"))
        self.b_play.setToolTip("播放 / 暂停")
        self.b_play.clicked.connect(self.toggle_play)
        b_stop = QPushButton()
        b_stop.setIcon(icons.icon("stop", 18))
        b_stop.setFixedSize(38, 34)
        b_stop.setToolTip("停止")
        b_stop.clicked.connect(self.stop)
        b_next = QPushButton()
        b_next.setIcon(icons.icon("next", 20))
        b_next.setFixedSize(38, 34)
        b_next.setToolTip("下一首")
        b_next.clicked.connect(self.play_next)
        row_ctl.addWidget(b_prev)
        row_ctl.addWidget(self.b_play)
        row_ctl.addWidget(b_stop)
        row_ctl.addWidget(b_next)

        row_ctl.addSpacing(10)
        lb_v = QLabel()
        lb_v.setPixmap(icons.icon("volume", 18).pixmap(18, 18))
        row_ctl.addWidget(lb_v)
        self.sl_vol = QSlider(Qt.Horizontal)
        self.sl_vol.setRange(0, 100)
        self.sl_vol.setFixedWidth(120)
        self.sl_vol.valueChanged.connect(self._on_master_vol)
        row_ctl.addWidget(self.sl_vol)

        row_ctl.addSpacing(8)
        row_ctl.addWidget(QLabel("速度"))
        self.sp_speed = DragDoubleSpinBox()
        self.sp_speed.setRange(0.5, 2.0)
        self.sp_speed.setSingleStep(0.05)
        self.sp_speed.setDecimals(2)
        self.sp_speed.setFixedWidth(80)
        self.sp_speed.setSuffix(" x")
        self.sp_speed.setValue(1.0)
        self.sp_speed.valueChanged.connect(self._speed_changed)
        row_ctl.addWidget(self.sp_speed)
        row_ctl.addStretch()
        lb_loop = QLabel("循环")
        lb_loop.setObjectName("SubTitle")
        row_ctl.addWidget(lb_loop)
        self.btn_loop_one = QToolButton()
        self.btn_loop_list = QToolButton()
        self.btn_loop_none = QToolButton()
        for b, name, tip in ((self.btn_loop_one, "loop_one", "单曲循环"),
                             (self.btn_loop_list, "loop_list", "列表内循环"),
                             (self.btn_loop_none, "no_loop", "顺序播放，不循环")):
            b.setIcon(icons.icon(name, 20))
            b.setCheckable(True)
            b.setFixedSize(36, 32)
            b.setToolTip(tip)
            b.setObjectName("LoopBtn")
            b.clicked.connect(self._loop_changed)
            row_ctl.addWidget(b)
        self._sync_loop_buttons()
        cv.addLayout(row_ctl)
        lay.addWidget(ctl)

        self.lb_status = QLabel("")
        self.lb_status.setObjectName("SubTitle")
        lay.addWidget(self.lb_status)

    # ---------- 快捷键 ----------
    def _shortcut_file(self):
        return os.path.join(data_dir(), "music_shortcuts.json")

    def _load_shortcut_cfg(self):
        cfg = {k: {"seq": d, "global": False} for k, _l, d in SHORTCUT_ACTIONS}
        try:
            with open(self._shortcut_file(), encoding="utf-8") as f:
                data = json.load(f)
            for k, v in (data or {}).items():
                if k in cfg and isinstance(v, dict):
                    cfg[k] = {"seq": str(v.get("seq", cfg[k]["seq"])),
                              "global": bool(v.get("global"))}
        except Exception:
            pass
        return cfg

    def _save_shortcut_cfg(self, cfg):
        try:
            with open(self._shortcut_file(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.warning("保存快捷键失败: %s", e)

    def open_shortcuts(self):
        dlg = ShortcutDialog(self._shortcut_cfg, self)
        if dlg.exec() != QDialog.Accepted:
            return
        cfg = dlg.result_cfg()
        self._shortcut_cfg = cfg
        self._save_shortcut_cfg(cfg)
        failed = self._apply_shortcuts(cfg, silent=False)
        if failed:
            QMessageBox.warning(
                self, "全局快捷键未注册",
                "以下全局组合键已被系统或其他软件占用，已退回为软件内快捷键：\n"
                + "、".join(failed) +
                "\n\n可换一个组合键，或取消勾选「全局」。")
        else:
            self._status("快捷键已保存并生效")

    def _apply_shortcuts(self, cfg, silent=False):
        for sc in self._local_shortcuts:
            try:
                sc.setEnabled(False)
                sc.deleteLater()
            except Exception:
                pass
        self._local_shortcuts = []
        for hk in self._global_ids:
            self.hotkey.unregister(hk)
        self._global_ids = []
        failed = []
        for key, label, default in SHORTCUT_ACTIONS:
            item = cfg.get(key) or {}
            seq = str(item.get("seq", "")).strip()
            if not seq:
                continue
            cb = (lambda a=key: self._do_shortcut(a))
            if item.get("global"):
                hk = self.hotkey.register(seq, cb)
                if hk is not None:
                    self._global_ids.append(hk)
                    continue
                failed.append(f"{label}（{seq}）")
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(cb)
            sc.setEnabled(True)
            self._local_shortcuts.append(sc)
        if not silent and failed:
            logger.warning("全局快捷键注册失败: %s", failed)
        return failed

    def _do_shortcut(self, action):
        try:
            if action == "play_pause":
                self.toggle_play()
            elif action == "stop":
                self.stop()
            elif action == "prev":
                self.play_prev()
            elif action == "next":
                self.play_next()
            elif action == "vol_up":
                self.bump_volume(5)
            elif action == "vol_down":
                self.bump_volume(-5)
            elif action == "mute":
                self.toggle_mute()
            elif action == "seek_back":
                self.seek_rel(-5000)
            elif action == "seek_fwd":
                self.seek_rel(5000)
        except Exception:
            logger.exception("执行快捷键失败: %s", action)

    def _on_media_key(self, action):
        """诺为 N61 司仪宝媒体键（模式1）"""
        try:
            import time as _time
            now = _time.time()
            last = getattr(self, "_last_media", (None, 0))
            if action == last[0] and now - last[1] < 0.28:
                return
            self._last_media = (action, now)
            if action == "play_pause":
                self.toggle_play()
                self._status("司仪宝：播放 / 暂停")
            elif action == "next":
                self.play_next()
                self._status("司仪宝：下一曲")
            elif action == "prev":
                self.play_prev()
                self._status("司仪宝：上一曲")
            elif action == "stop":
                self.stop()
                self._status("司仪宝：停止")
        except Exception:
            logger.exception("司仪宝按键处理失败: %s", action)

    def seek_rel(self, delta_ms):
        if self.player.source().isEmpty():
            return
        pos = self.player.position() + int(delta_ms)
        pos = max(0, min(pos, max(0, self.player.duration() - 100)))
        self.player.setPosition(pos)

    def toggle_mute(self):
        if self.sl_vol.value() > 0:
            self._mute_restore = self.sl_vol.value()
            self.sl_vol.setValue(0)
            self._status("已静音")
        else:
            self.sl_vol.setValue(getattr(self, "_mute_restore", 70))
            self._status("已恢复音量")

    # ---------- 拖到左侧列表 ----------
    def drop_tracks_to_list(self, paths, row, external=False):
        if not paths or not self.lib.lists:
            return
        if row < 0 or row >= len(self.lib.lists):
            row = len(self.lib.lists) - 1
        target = self.lib.lists[row]
        if external:
            add = [p for p in paths if is_audio(p) and os.path.exists(p)]
            if not add:
                self._status("拖进来的不是可播放音频")
                return
            for p in add:
                if p not in target["items"]:
                    target["items"].append(p)
        else:
            src_idx = self.lib.current
            if row == src_idx:
                return
            src = self.lib.lists[src_idx]
            moved = [p for p in paths if p in src["items"]]
            if not moved:
                return
            for p in moved:
                src["items"].remove(p)
            for p in moved:
                if p not in target["items"]:
                    target["items"].append(p)
        self.lib.save()
        self._load_lists()
        self._load_tracks()
        self._status(f"已移动到「{target['name']}」：{len(paths)} 首")

    # ---------- 状态 ----------
    def _status(self, msg):
        self.lb_status.setText(msg)

    def _set_root(self, d):
        os.makedirs(d, exist_ok=True)
        idx = self.fs_model.setRootPath(d)
        self.tree.setRootIndex(idx)
        self.lb_dir.setText("音乐库：" + d)
        set_setting("music_dir", d)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择音乐库目录", self.fs_model.rootPath())
        if d:
            self._set_root(d)
            self._status("音乐库目录已切换到：" + d)

    def refresh(self):
        self._load_lists()
        self._load_tracks()
        self.tree.doItemsLayout()
        self._status("已刷新")

    # ---------- 播放列表 ----------
    def _load_lists(self):
        self.list_lists.blockSignals(True)
        self.list_lists.clear()
        for lst in self.lib.lists:
            it = QListWidgetItem(f"{lst['name']}   ({len(lst['items'])})")
            self.list_lists.addItem(it)
        self.list_lists.setCurrentRow(self.lib.current)
        self.list_lists.blockSignals(False)
        self.lb_pl_count.setText(f"共 {len(self.lib.lists)} 个列表")

    def _switch_list(self, row):
        if 0 <= row < len(self.lib.lists):
            self.lib.current = row
            self.lib.save()
            self._load_tracks()

    def new_list(self):
        name, ok = QInputDialog.getText(self, "新建播放列表", "列表名称：", text="新列表")
        if ok and name.strip():
            self.lib.lists.append({"name": name.strip(), "items": []})
            self.lib.current = len(self.lib.lists) - 1
            self.lib.save()
            self._load_lists()
            self._load_tracks()

    def _list_menu(self, pos):
        idx = self.list_lists.indexAt(pos)
        row = idx.row() if idx.isValid() else -1
        m = QMenu(self)
        m.addAction("新建播放列表", self.new_list)
        if row >= 0:
            m.addSeparator()
            m.addAction("重命名", lambda: self.rename_list(row))
            m.addAction("复制列表", lambda: self.copy_list(row))
            m.addAction("剪切列表", lambda: self.cut_list(row))
            if self._clip_list:
                m.addAction("粘贴列表", self.paste_list)
            m.addSeparator()
            m.addAction("删除列表", lambda: self.delete_list(row))
        elif self._clip_list:
            m.addAction("粘贴列表", self.paste_list)
        m.exec(self.list_lists.mapToGlobal(pos))

    def rename_list(self, row):
        name, ok = QInputDialog.getText(self, "重命名列表", "新名称：",
                                        text=self.lib.lists[row]["name"])
        if ok and name.strip():
            self.lib.lists[row]["name"] = name.strip()
            self.lib.save()
            self._load_lists()

    def copy_list(self, row):
        self._clip_list = (json.loads(json.dumps(self.lib.lists[row])), "copy")
        self._status("已复制列表：" + self.lib.lists[row]["name"] + "（右键粘贴）")

    def cut_list(self, row):
        self._clip_list = (json.loads(json.dumps(self.lib.lists[row])), "cut")
        self._status("已剪切列表，右键选择粘贴位置")

    def paste_list(self):
        if not self._clip_list:
            return
        data, mode = self._clip_list
        data = json.loads(json.dumps(data))
        data["name"] = data["name"] + "（副本）"
        self.lib.lists.append(data)
        if mode == "cut":
            # 剪切：粘贴后原列表移除
            for i, l in enumerate(self.lib.lists[:-1]):
                if l["name"] == data["name"].replace("（副本）", ""):
                    self.lib.lists.pop(i)
                    break
            self._clip_list = None
        self.lib.save()
        self._load_lists()
        self._load_tracks()

    def delete_list(self, row):
        if len(self.lib.lists) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个播放列表")
            return
        name = self.lib.lists[row]["name"]
        if QMessageBox.question(self, "删除列表", f"确定删除「{name}」？曲目文件不会被删除。") != QMessageBox.Yes:
            return
        self.lib.lists.pop(row)
        self.lib.current = min(self.lib.current, len(self.lib.lists) - 1)
        self.lib.save()
        self._load_lists()
        self._load_tracks()

    # ---------- 曲目表 ----------
    def track_title(self, path):
        try:
            title = self.lib.track(path).get("title")
            if title:
                return title
            tag = self.lib.tag_title(path)
            if tag:
                return tag
            return os.path.splitext(os.path.basename(path))[0]
        except Exception:
            return os.path.splitext(os.path.basename(path))[0]

    def _load_tracks(self):
        if not self.lib.lists:
            self.lib.lists = [{"name": "默认列表", "items": []}]
        self.lib.current = max(0, min(int(self.lib.current), len(self.lib.lists) - 1))
        lst = self.lib.lists[self.lib.current]
        self.lb_cur_list.setText(lst["name"])
        self.table.setRowCount(0)
        self.table.setRowCount(len(lst["items"]))
        for i, p in enumerate(lst["items"]):
            it0 = QTableWidgetItem(str(i + 1))
            it0.setTextAlignment(Qt.AlignCenter)
            it0.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            name = self.track_title(p)
            it1 = QTableWidgetItem(name)
            it1.setToolTip(p)
            it1.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            dur = self._dur(p)
            it2 = QTableWidgetItem(fmt_hms(dur))
            it2.setTextAlignment(Qt.AlignCenter)
            it2.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(i, 0, it0)
            self.table.setItem(i, 1, it1)
            self.table.setItem(i, 2, it2)
            self.table.setRowHeight(i, 34)
        self.table.resizeRowsToContents()
        self.list_lists.blockSignals(True)
        item = self.list_lists.item(self.lib.current)
        if item:
            item.setText(f"{lst['name']}   ({len(lst['items'])})")
        self.list_lists.blockSignals(False)

    def _dur(self, path):
        if path not in self._dur_cache:
            self._dur_cache[path] = audio_duration(path)
        return self._dur_cache[path]

    def sync_flow_playlist(self, paths, name="流程配乐"):
        """备婚工具 → 流程清单：把各环节指定音乐同步成一条播放列表"""
        paths = [os.path.abspath(p) for p in paths if p and os.path.exists(p)]
        idx = next((i for i, l in enumerate(self.lib.lists) if l["name"] == name), None)
        if idx is None:
            self.lib.lists.append({"name": name, "items": list(paths)})
            idx = len(self.lib.lists) - 1
        else:
            self.lib.lists[idx]["items"] = list(paths)
        self.lib.current = idx
        self.lib.save()
        self._load_lists()
        self._load_tracks()
        return len(paths)

    def add_to_list(self, paths, row_hint=None):
        lst = self.lib.lists[self.lib.current]
        added = 0
        for p in paths:
            if is_audio(p):
                lst["items"].append(os.path.abspath(p))
                added += 1
            elif os.path.isdir(p):
                for root, _, fns in os.walk(p):
                    for fn in sorted(fns):
                        fp = os.path.join(root, fn)
                        if is_audio(fp):
                            lst["items"].append(os.path.abspath(fp))
                            added += 1
        if added:
            self.lib.save()
            self._load_tracks()
            self._status(f"已加入 {added} 首")
        return added

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "添加音乐", self.fs_model.rootPath(),
            "音频文件 (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.wma *.ape)")
        if not files:
            return
        # 复制进音乐库目录，再入列
        d = self.fs_model.rootPath()
        dst_list = []
        for f in files:
            try:
                dst = os.path.join(d, os.path.basename(f))
                if os.path.abspath(f) != os.path.abspath(dst):
                    shutil.copy2(f, dst)
                dst_list.append(dst)
            except Exception as e:
                logger.warning("复制失败 %s: %s", f, e)
        self.add_to_list(dst_list)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "添加文件夹", self.fs_model.rootPath())
        if not folder:
            return
        d = self.fs_model.rootPath()
        copied = []
        for root, _, fns in os.walk(folder):
            for fn in fns:
                if is_audio(os.path.join(root, fn)):
                    src = os.path.join(root, fn)
                    dst = os.path.join(d, fn)
                    try:
                        if os.path.abspath(src) != os.path.abspath(dst):
                            shutil.copy2(src, dst)
                        copied.append(dst)
                    except Exception:
                        pass
        self.add_to_list(copied)

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        lst = self.lib.lists[self.lib.current]
        for r in rows:
            if 0 <= r < len(lst["items"]):
                lst["items"].pop(r)
        self.lib.save()
        self._load_tracks()

    def move_selected(self, delta):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        lst = self.lib.lists[self.lib.current]
        items = lst["items"]
        if delta < 0:
            for r in rows:
                if r > 0:
                    items[r - 1], items[r] = items[r], items[r - 1]
        else:
            for r in reversed(rows):
                if r < len(items) - 1:
                    items[r + 1], items[r] = items[r], items[r + 1]
        self.lib.save()
        self._load_tracks()

    def _table_play(self, idx):
        self.play_row(idx.row())

    def _track_menu(self, pos):
        idx = self.table.indexAt(pos)
        row = idx.row() if idx.isValid() else -1
        m = QMenu(self)
        if row >= 0:
            m.addAction("播放", lambda: self.play_row(row))
            m.addAction("曲目设置…", lambda: self.edit_track(row))
            m.addSeparator()
            m.addAction("从列表移除", self.remove_selected)
            if row > 0:
                m.addAction("上移", lambda: self.move_one(row, -1))
            if row < self.table.rowCount() - 1:
                m.addAction("下移", lambda: self.move_one(row, 1))
            p = self.lib.lists[self.lib.current]["items"][row]
            m.addSeparator()
            m.addAction("在资源管理器中显示", lambda: self.reveal(p))
        m.exec(self.table.mapToGlobal(pos))

    def move_one(self, row, delta):
        lst = self.lib.lists[self.lib.current]
        items = lst["items"]
        t = row + delta
        if 0 <= t < len(items):
            items[row], items[t] = items[t], items[row]
            self.lib.save()
            self._load_tracks()
            self.table.selectRow(t)

    def reveal(self, path):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception:
            pass

    # ---------- 文件树 ----------
    def _tree_play(self, idx):
        p = self.fs_model.filePath(idx)
        if is_audio(p):
            if self.add_to_list([p]):
                self.table.selectRow(self.table.rowCount() - 1)
                self.play_row(self.table.rowCount() - 1)

    def _file_menu(self, pos):
        idx = self.tree.indexAt(pos)
        paths = []
        if idx.isValid():
            p = self.fs_model.filePath(idx)
            if os.path.isfile(p):
                paths = [p]
            elif os.path.isdir(p):
                paths = [os.path.join(p, f) for f in os.listdir(p)
                         if is_audio(os.path.join(p, f))]
        m = QMenu(self)
        if paths:
            m.addAction("播放", lambda: self._play_files(paths))
            m.addAction("加入当前列表", lambda: self.add_to_list(paths))
            m.addSeparator()
            m.addAction("复制", lambda: self._set_clip("copy", paths))
            m.addAction("剪切", lambda: self._set_clip("cut", paths))
            m.addSeparator()
            m.addAction("重命名…", lambda: self._rename_file(paths[0]))
            m.addAction("删除", lambda: self._delete_files(paths))
            m.addAction("在资源管理器中显示", lambda: self.reveal(paths[0]))
        if self._clip_files:
            target = self.fs_model.rootPath()
            if idx.isValid():
                p = self.fs_model.filePath(idx)
                target = p if os.path.isdir(p) else os.path.dirname(p)
            m.addAction("粘贴到此文件夹", lambda: self._paste_files(target))
        m.addSeparator()
        m.addAction("打开音乐库目录", lambda: self.reveal(self.fs_model.rootPath()))
        m.addAction("选择音乐库目录…", self.pick_dir)
        m.exec(self.tree.mapToGlobal(pos))

    def _play_files(self, paths):
        n = self.add_to_list(paths)
        if n:
            self.play_row(self.table.rowCount() - 1)

    def _set_clip(self, mode, paths):
        self._clip_files = (mode, list(paths))
        self._status(f"已{'复制' if mode == 'copy' else '剪切'} {len(paths)} 个文件")

    def _paste_files(self, target):
        if not self._clip_files:
            return
        mode, paths = self._clip_files
        try:
            for p in paths:
                dst = os.path.join(target, os.path.basename(p))
                if os.path.abspath(p) == os.path.abspath(dst):
                    continue
                shutil.copy2(p, dst)
            if mode == "cut":
                self._clip_files = None
            self._status("已粘贴到：" + target)
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "粘贴失败", str(e))

    def _rename_file(self, path):
        old = os.path.basename(path)
        base, ext = os.path.splitext(old)
        new, ok = QInputDialog.getText(self, "重命名", "新文件名：", text=base)
        if ok and new.strip():
            try:
                os.rename(path, os.path.join(os.path.dirname(path), new.strip() + ext))
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "重命名失败", str(e))

    def _delete_files(self, paths):
        if QMessageBox.question(self, "删除文件", f"确定删除 {len(paths)} 个文件？不进回收站，无法恢复。") != QMessageBox.Yes:
            return
        for p in paths:
            try:
                os.remove(p)
            except Exception as e:
                logger.warning("删除失败 %s: %s", p, e)
        self.refresh()

    # ---------- 列表工程保存 / 加载 ----------
    def save_project(self):
        import datetime
        default = os.path.join(data_dir(), "音乐工程_%s.json" % datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        path, _ = QFileDialog.getSaveFileName(self, "保存列表工程", default, "列表工程 (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"lists": self.lib.lists, "settings": self.lib.settings,
                           "current": self.lib.current}, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "已保存", path)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载列表工程", data_dir(), "列表工程 (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            lists = data.get("lists") or []
            if not lists:
                raise ValueError("工程文件里没有播放列表")
            self.lib.lists = lists
            self.lib.settings = data.get("settings") or {}
            self.lib.current = int(data.get("current", 0))
            if not (0 <= self.lib.current < len(self.lib.lists)):
                self.lib.current = 0
            self.lib.save()
            self._load_lists()
            self._load_tracks()
            QMessageBox.information(self, "已加载", os.path.basename(path))
        except Exception as e:
            QMessageBox.warning(self, "加载失败", str(e))

    # ---------- 播放 ----------
    def _reload_current(self, pos_ms=0, play=True):
        """保持播放位置地重新加载当前曲目（用于变调后立即生效）"""
        if not self.cur_path:
            return
        st = self._track_setting(self.cur_path)
        self._stop_fade()
        self.player.setSource(QUrl.fromLocalFile(self.cur_path))
        self._pending = {"start": float(pos_ms),
                         "fin": 0.0, "gain": int(st.get("gain", 100))}
        if play:
            self.player.play()
        self.player.setPlaybackRate(float(st.get("speed", 1.0)))

    def set_volume(self, v):
        self.sl_vol.setValue(int(v))

    def bump_volume(self, delta):
        self.sl_vol.setValue(max(0, min(100, self.sl_vol.value() + delta)))

    def _track_setting(self, path):
        return self.lib.track(path) if path else dict(DEFAULT_TRACK)

    def _pitch_cache(self, path, semi):
        ratio = 2 ** (semi / 12.0)
        key = hashlib.md5((path + str(semi) + str(os.path.getmtime(path))).encode("utf-8")).hexdigest()[:12]
        out_dir = os.path.join(data_dir(), "cache")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"pitch_{key}.wav")
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
        ff = common.asset_path("ffmpeg.exe")
        cmd = [ff if os.path.exists(ff) else "ffmpeg", "-y", "-i", path,
               "-af", f"rubberband=pitch={ratio:.4f}", "-ar", "44100", "-ac", "2", out]
        flags = 0
        if os.name == "nt":
            flags = 0x08000000  # CREATE_NO_WINDOW
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=flags, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
        return path

    def play_row(self, row):
        lst = self.lib.lists[self.lib.current]
        if not (0 <= row < len(lst["items"])):
            return
        path = lst["items"][row]
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", path)
            return
        self.cur_row = row
        self.cur_path = path
        st = self._track_setting(path)
        self.cur_gain = int(st.get("gain", 100))
        src = path
        if int(st.get("semi", 0)) != 0:
            self._status("正在按设定调整音调…")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                src = self._pitch_cache(path, int(st["semi"]))
            finally:
                QApplication.restoreOverrideCursor()
            self._status("")
        self._stop_fade()
        self.player.setSource(QUrl.fromLocalFile(src))
        self._pending = {"start": float(st.get("start", 0.0)) * 1000.0,
                         "fin": float(st.get("fin", 0.0)),
                         "gain": int(st.get("gain", 100))}
        self.player.play()
        self.player.setPlaybackRate(float(st.get("speed", 1.0)))
        self.b_play.setIcon(icons.icon("pause", 22, "#14161B"))
        self.sp_speed.blockSignals(True)
        self.sp_speed.setValue(float(st.get("speed", 1.0)))
        self.sp_speed.blockSignals(False)
        self.table.selectRow(row)
        self._status(f"正在播放：{self.track_title(path)}")

    def _on_status(self, status):
        if status == QMediaPlayer.LoadedMedia and self._pending:
            start = self._pending.get("start", 0)
            if start > 0:
                self.player.setPosition(int(start))
            self.cur_gain = self._pending.get("gain", 100)
            fin = self._pending.get("fin", 0)
            self._pending = {}
            self._fade_start(1, fin * 1000 if fin > 0 else 0, target=self.cur_gain)
        elif status == QMediaPlayer.EndOfMedia:
            self._on_end()

    def _on_error(self, err, msg):
        if err != QMediaPlayer.NoError:
            self._status(f"播放错误：{msg}")

    def _on_end(self):
        mode = get_setting("loop_mode", "list")
        lst = self.lib.lists[self.lib.current]
        if mode == "one":
            self.player.setPosition(int(self._track_setting(self.cur_path).get("start", 0) * 1000))
            self.player.play()
        elif mode == "list":
            nxt = (self.cur_row + 1) % max(len(lst["items"]), 1)
            self.play_row(nxt)
        else:
            if self.cur_row + 1 < len(lst["items"]):
                self.play_row(self.cur_row + 1)
            else:
                self.stop()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._fade_start(-1, 0)  # 暂停时直接停
            self.player.pause()
            self.b_play.setIcon(icons.icon("play", 22, "#14161B"))
        else:
            if not self.player.source().isEmpty():
                self.player.play()
                self.player.setPlaybackRate(self.sp_speed.value())
                self.b_play.setIcon(icons.icon("pause", 22, "#14161B"))
            elif self.table.rowCount():
                self.play_row(0)

    def stop(self):
        st = self._track_setting(self.cur_path) if self.cur_path else dict(DEFAULT_TRACK)
        fout = float(st.get("fout", 0.0))

        def _do():
            self.player.stop()
            self.b_play.setIcon(icons.icon("play", 22, "#14161B"))
            self.slider.setValue(0)
            self.lb_cur.setText("00:00")
            self._apply_volume()

        if fout > 0 and self.player.playbackState() == QMediaPlayer.PlayingState:
            self._fade_start(-1, fout * 1000, after=_do)
        else:
            _do()

    def play_prev(self):
        lst = self.lib.lists[self.lib.current]
        if not lst["items"]:
            return
        self.play_row((self.cur_row - 1) % len(lst["items"]))

    def play_next(self):
        lst = self.lib.lists[self.lib.current]
        if not lst["items"]:
            return
        self.play_row((self.cur_row + 1) % len(lst["items"]))

    def _seek(self, v):
        self.player.setPosition(v)

    def _on_pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(pos)
            self.slider.blockSignals(False)
        self.lb_cur.setText(fmt_hms(pos))

    def _on_dur(self, dur):
        self.slider.setRange(0, max(int(dur), 1))
        self.lb_dur.setText(fmt_hms(dur))

    # ---------- 音量 / 淡入淡出 ----------
    def _apply_volume(self):
        v = (self.master_vol / 100.0) * (self.cur_gain / 100.0)
        self.audio.setVolume(max(0.0, min(1.0, v)))

    def _on_master_vol(self, v):
        self.master_vol = int(v)
        set_setting("music_volume", str(v))
        self._apply_volume()

    def _fade_start(self, direction, duration_ms, target=None, after=None):
        self._stop_fade()
        self._fade_dir = direction
        self._fade_total = max(int(duration_ms), 0)
        self._fade_elapsed = 0
        self._fade_target = (target if target is not None else self.cur_gain) / 100.0
        self._after_fade = after
        if self._fade_total <= 0:
            if direction > 0:
                self._apply_volume()
            elif after:
                after()
            return
        if direction < 0:
            self._fade_from = (self.audio.volume())
        else:
            self.audio.setVolume(0.0)
            self._fade_from = 0.0
        self._fade_timer.start()

    def _fade_tick(self):
        self._fade_elapsed += 40
        p = min(1.0, self._fade_elapsed / max(self._fade_total, 1))
        base = (self.master_vol / 100.0)
        if self._fade_dir > 0:
            v = base * self._fade_target * p
        else:
            v = self._fade_from * (1 - p)
        self.audio.setVolume(max(0.0, min(1.0, v)))
        if p >= 1.0:
            self._fade_timer.stop()
            if self._fade_dir > 0:
                self._apply_volume()
            elif self._after_fade:
                fn = self._after_fade
                self._after_fade = None
                fn()

    def _stop_fade(self):
        self._fade_timer.stop()
        self._after_fade = None

    # ---------- 曲目参数 ----------
    def _speed_changed(self, v):
        if not self.cur_path:
            return
        st = self._track_setting(self.cur_path)
        st["speed"] = round(float(v), 2)
        self.lib.set_track(self.cur_path, st)
        self.player.setPlaybackRate(float(v))

    def _semi_changed(self, v):
        if not self.cur_path:
            return
        st = self._track_setting(self.cur_path)
        if int(st.get("semi", 0)) == int(v):
            return
        st["semi"] = int(v)
        self.lib.set_track(self.cur_path, st)
        if self.player.playbackState() != QMediaPlayer.StoppedState:
            pos = self.player.position()
            was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
            self._reload_current(pos, was_playing)
        self._status(f"音调已调整为 {v} 半音（立即生效）")

    def _selected_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return rows[0] if rows else (self.cur_row if self.cur_row >= 0 else -1)

    def edit_selected_track(self):
        r = self._selected_row()
        if r >= 0:
            self.edit_track(r)

    def open_legal(self):
        LegalMusicDialog(self._add_downloaded, self).exec()

    def open_search(self):
        dlg = MusicSearchDialog(self._add_downloaded, self)
        dlg.exec()

    def _add_downloaded(self, path):
        try:
            lst = self.lib.lists[self.lib.current]
            if path not in lst["items"]:
                lst["items"].append(path)
                self.lib.save()
            self._load_tracks()
            self._status("已加入当前列表：" + os.path.basename(path))
        except Exception:
            logger.exception("加入下载歌曲失败")

    def edit_track(self, row):
        lst = self.lib.lists[self.lib.current]
        if not (0 <= row < len(lst["items"])):
            return
        path = lst["items"][row]
        st = self._track_setting(path)
        pos = self.player.position() if path == self.cur_path else 0
        dlg = TrackDialog(path, st, pos, self)
        if dlg.exec() == QDialog.Accepted:
            self.lib.set_track(path, dlg.value())
            write_tag_title(path, dlg.value().get("title", ""))
            self._load_tracks()
            if path == self.cur_path:
                self.cur_gain = int(dlg.value().get("gain", 100))
                self.sp_speed.blockSignals(True)
                self.sp_speed.setValue(float(dlg.value().get("speed", 1.0)))
                self.sp_speed.blockSignals(False)
                self._apply_volume()
            self._status("曲目参数已保存，下次播放自动生效")

    # ---------- 循环 ----------
    def _loop_changed(self):
        if self.btn_loop_one.isChecked():
            set_setting("loop_mode", "one")
        elif self.btn_loop_list.isChecked():
            set_setting("loop_mode", "list")
        else:
            set_setting("loop_mode", "none")

    def _sync_loop_buttons(self):
        mode = get_setting("loop_mode", "list")
        self.btn_loop_one.setChecked(mode == "one")
        self.btn_loop_list.setChecked(mode == "list")
        self.btn_loop_none.setChecked(mode == "none")

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        if ev.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.add_to_list(paths)
                ev.acceptProposedAction()

    # ---------- 对外 ----------
    def save_state(self):
        self.lib.save()
        set_setting("music_volume", str(self.master_vol))
