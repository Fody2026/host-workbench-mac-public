"""Intercept macOS consumer transport keys while show mode is enabled.

Two independent paths are available:

* CGEventTap: preferred.  It sees NX_SYSDEFINED transport events and consumes
  them, so another player in the background cannot react as well.
* MPRemoteCommandCenter: fallback used by ``pages_music.MacNowPlaying`` when
  the event tap cannot be installed (for example, Accessibility permission is
  missing).  It relies on the app being the current Now Playing client.

Keeping the event decoding and the de-duplication gate free of AppKit makes
this module importable and testable on Windows and Linux too.
"""
import logging

logger = logging.getLogger(__name__)

try:  # macOS only; keep the module importable for static checks elsewhere.
    from AppKit import NSEvent
    import Quartz as CG
except Exception:  # pragma: no cover - exercised on Windows/Linux
    NSEvent = None
    CG = None

try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
except Exception:  # pragma: no cover - older PyObjC builds
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None

from PySide6.QtCore import Qt

# NX_SYSDEFINED, NX_SUBTYPE_AUX_CONTROL_BUTTONS and NX_KEYTYPE_*.
SYSTEM_DEFINED = 14
AUX_CONTROL = 8
TRANSPORT = {16: "play_pause", 17: "next", 18: "prev", 19: "next", 20: "prev"}

# Fallbacks are only used to keep constants usable on non-macOS systems.
CG_KEY_DOWN = getattr(CG, "kCGEventKeyDown", 10) if CG else 10
CG_KEY_UP = getattr(CG, "kCGEventKeyUp", 11) if CG else 11
CG_FLAGS = {
    "command": getattr(CG, "kCGEventFlagMaskCommand", 1 << 20) if CG else 1 << 20,
    "control": getattr(CG, "kCGEventFlagMaskControl", 1 << 18) if CG else 1 << 18,
    "shift": getattr(CG, "kCGEventFlagMaskShift", 1 << 17) if CG else 1 << 17,
    "option": getattr(CG, "kCGEventFlagMaskAlternate", 1 << 19) if CG else 1 << 19,
}

# ANSI hardware codes used by common presentation remotes and programmable HID buttons.
KEY_CODES = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    (0, 11, 8, 2, 14, 3, 5, 4, 34, 38, 40, 37, 46, 45, 31, 35, 12, 15, 1, 17,
     32, 9, 13, 7, 16, 6, 29, 18, 19, 20, 21, 23, 22, 26, 28, 25),
))
SPECIAL_CODES = {
    Qt.Key_Space: 49, Qt.Key_Escape: 53, Qt.Key_Return: 36, Qt.Key_Enter: 76,
    Qt.Key_Tab: 48, Qt.Key_Backspace: 51, Qt.Key_Delete: 117, Qt.Key_Insert: 114,
    Qt.Key_Left: 123, Qt.Key_Right: 124, Qt.Key_Down: 125, Qt.Key_Up: 126,
    Qt.Key_Home: 115, Qt.Key_End: 119, Qt.Key_PageUp: 116, Qt.Key_PageDown: 121,
    Qt.Key_Period: 47, Qt.Key_Comma: 43, Qt.Key_Slash: 44, Qt.Key_Minus: 27,
}
SPECIAL_CODES.update({
    int(Qt.Key_F1) + index: code for index, code in enumerate(
        (122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 105, 107, 113, 106, 64, 79, 80, 90))
})
MODIFIERS = (
    (Qt.ControlModifier, CG_FLAGS["command"]),
    (Qt.MetaModifier, CG_FLAGS["control"]),
    (Qt.ShiftModifier, CG_FLAGS["shift"]),
    (Qt.AltModifier, CG_FLAGS["option"]),
)
MODIFIER_MASK = sum(flag for _, flag in MODIFIERS)


def decode_transport(data1):
    """Return ``(action, is_down, is_repeat)`` from NX_SYSDEFINED data1.

    Bits 16-31 hold NX_KEYTYPE_*, bits 8-15 hold 0x0a (down) or 0x0b (up).
    Bit 0 is the auto-repeat flag on the transport events emitted by macOS.
    """
    key = (int(data1) >> 16) & 0xffff
    state = (int(data1) >> 8) & 0xff
    return TRANSPORT.get(key), state == 0x0a, bool(int(data1) & 1)


class TransportGate:
    """One action per physical press; auto-repeat and duplicate callbacks are ignored."""

    def __init__(self):
        self.pressed = set()

    def feed(self, action, down, repeat=False):
        if not down:
            self.pressed.discard(action)
            return False
        if repeat or action in self.pressed:
            return False
        self.pressed.add(action)
        return True

    def clear(self):
        self.pressed.clear()


class MacMediaKeyHook:
    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.shortcuts = {}
        self.pressed = set()
        self.gate = TransportGate()
        self.hook = None
        self.source = None
        self.loop = None
        self.error = ""
        self.events = 0
        if CG is None:
            self.error = "当前系统没有 Quartz，无法监听 macOS 媒体键"
            return
        if not self._ensure_accessibility():
            self.error = ("未获得辅助功能权限。请到「系统设置 → 隐私与安全性 → 辅助功能」"
                          "允许主持人工作台后重启。")
            return
        try:
            self.hook = CG.CGEventTapCreate(
                CG.kCGSessionEventTap, CG.kCGHeadInsertEventTap,
                CG.kCGEventTapOptionDefault,
                (1 << SYSTEM_DEFINED) | (1 << CG_KEY_DOWN) | (1 << CG_KEY_UP),
                self._event, None,
            )
        except Exception as exc:
            self.error = "媒体键监听安装失败：%s" % exc
            logger.exception("安装 CGEventTap 失败")
            return
        if self.hook is None:
            self.error = "媒体键监听安装失败（系统未允许事件监听）"
            return
        self.loop = CG.CFRunLoopGetMain()
        self.source = CG.CFMachPortCreateRunLoopSource(None, self.hook, 0)
        if self.source is None:
            self.error = "媒体键事件循环安装失败"
            self.uninstall()
            return
        CG.CFRunLoopAddSource(self.loop, self.source, CG.kCFRunLoopCommonModes)
        logger.info("macOS 媒体键监听已安装")

    @staticmethod
    def _ensure_accessibility():
        if AXIsProcessTrustedWithOptions is None or kAXTrustedCheckOptionPrompt is None:
            try:
                return bool(CG.AXIsProcessTrusted())
            except Exception:
                return True
        try:
            return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
        except Exception:
            try:
                return bool(CG.AXIsProcessTrusted())
            except Exception:
                return True

    @property
    def available(self):
        return self.hook is not None and self.source is not None

    def _event(self, proxy, kind, event, context):
        try:
            if kind in (CG.kCGEventTapDisabledByTimeout, CG.kCGEventTapDisabledByUserInput):
                self.gate.clear()
                self.pressed.clear()
                if self.hook is not None:
                    CG.CGEventTapEnable(self.hook, True)
                logger.warning("macOS 媒体键监听被系统暂停，已重新启用")
                return event
            if kind in (CG_KEY_DOWN, CG_KEY_UP):
                return self._keyboard_event(kind, event)
            if kind != SYSTEM_DEFINED:
                return event
            native = NSEvent.eventWithCGEvent_(event)
            if native is None or native.subtype() != AUX_CONTROL:
                return event
            data1 = native.data1()
            action, down, repeat = decode_transport(data1)
            if action is None:
                return event
            self.events += 1
            if self.gate.feed(action, down, repeat):
                logger.info("macOS 媒体键：%s", action)
                self.dispatch(action)
            return None
        except Exception:
            logger.exception("处理 macOS 媒体键失败")
            return event

    def bind(self, sequence, action):
        if not self.available or sequence.count() != 1:
            return False
        combo = sequence[0]
        key = int(combo.key())
        code = KEY_CODES.get(chr(key)) if 0x30 <= key <= 0x5a else SPECIAL_CODES.get(key)
        if code is None:
            return False
        mods = combo.keyboardModifiers()
        if mods & (Qt.KeypadModifier | Qt.GroupSwitchModifier):
            return False
        flags = sum(flag for modifier, flag in MODIFIERS if modifier & mods)
        self.shortcuts[code, flags] = action
        return True

    def _keyboard_event(self, kind, event):
        code = CG.CGEventGetIntegerValueField(event, CG.kCGKeyboardEventKeycode)
        if kind == CG_KEY_UP:
            if code not in self.pressed:
                return event
            self.pressed.discard(code)
            return None
        flags = CG.CGEventGetFlags(event) & MODIFIER_MASK
        action = self.shortcuts.get((code, flags))
        if action is None:
            return event
        repeat = bool(CG.CGEventGetIntegerValueField(event, CG.kCGKeyboardEventAutorepeat))
        self.pressed.add(code)
        if not repeat:
            self.dispatch(action)
        return None

    def uninstall(self):
        try:
            if self.source is not None and self.loop is not None:
                CG.CFRunLoopRemoveSource(self.loop, self.source, CG.kCFRunLoopCommonModes)
        except Exception:
            pass
        self.source = None
        try:
            if self.hook is not None:
                CG.CFMachPortInvalidate(self.hook)
        except Exception:
            pass
        self.hook = None
