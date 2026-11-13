# -*- coding: utf-8 -*-
"""主题系统：多套配色方案，统一替换全局样式颜色"""
import logging

logger = logging.getLogger(__name__)

# 每套主题包含：背景/卡片/边框/文字/辅文字/强调色/输入框/按钮/导航等
THEMES = {
    "暗夜金": {
        "bg": "#0B0B0E", "card": "#16171C", "card_alt": "#111216", "border": "#26272E",
        "text": "#F5F5F7", "sub": "#8E8E93", "accent": "#0A84FF", "accent_hover": "#409CFF",
        "input": "#101115", "btn": "#1D1E24", "btn_hover": "#282932", "soft": "#2A2B33",
        "nav": "#08080A", "nav_sel": "#17181D", "nav_hover": "#121317", "nav_text": "#9A9AA3", "title": "#FFFFFF",
        "hover_border": "#3A3B44", "danger_bg": "#3A1D1D", "danger_border": "#5A2A2A",
        "danger_text": "#E8C7C7",
        "cell_bg": "#111216", "cell_border": "#202128",
        "cell_today_bg": "#1C1D24", "cell_event_bg": "#16171D", "cell_event_border": "#35364a",
        "cell_out_bg": "#0C0D10", "cell_out_border": "#18191F",
    },
    "暗夜银": {
        "bg": "#0E1013", "card": "#171A20", "card_alt": "#12151A", "border": "#242830",
        "text": "#E6E8EC", "sub": "#8A9098", "accent": "#AEB6C4", "accent_hover": "#C7CEDB",
        "input": "#111418", "btn": "#20242C", "btn_hover": "#292E38", "soft": "#282D36",
        "nav": "#0A0C0F", "nav_sel": "#151920", "nav_hover": "#11151B", "nav_text": "#959BA6", "title": "#EEF1F6",
        "hover_border": "#363C47", "danger_bg": "#452A2C", "danger_border": "#58353A",
        "danger_text": "#E6C9CC",
        "cell_bg": "#13161B", "cell_border": "#1E222A",
        "cell_today_bg": "#1A1E25", "cell_event_bg": "#161A21", "cell_event_border": "#333A46",
        "cell_out_bg": "#0D0F13", "cell_out_border": "#181B22",
    },
    "墨绿雅致": {
        "bg": "#0C120F", "card": "#141D18", "card_alt": "#101812", "border": "#20302A",
        "text": "#E4E9E2", "sub": "#87958B", "accent": "#7FA98E", "accent_hover": "#9CC4AA",
        "input": "#0F1712", "btn": "#1A2620", "btn_hover": "#22332B", "soft": "#24332B",
        "nav": "#090F0C", "nav_sel": "#121C16", "nav_hover": "#101812", "nav_text": "#93A196", "title": "#EDF3ED",
        "hover_border": "#30463A", "danger_bg": "#3E2828", "danger_border": "#533434",
        "danger_text": "#E4C9C9",
        "cell_bg": "#111A14", "cell_border": "#1B2A22",
        "cell_today_bg": "#17241C", "cell_event_bg": "#141F18", "cell_event_border": "#2E4738",
        "cell_out_bg": "#0A100D", "cell_out_border": "#152019",
    },
    "暖棕复古": {
        "bg": "#131009", "card": "#1E1812", "card_alt": "#17120C", "border": "#332619",
        "text": "#EDE4D6", "sub": "#9C8C76", "accent": "#C08A5E", "accent_hover": "#D6A57A",
        "input": "#18120C", "btn": "#2A2016", "btn_hover": "#392B1D", "soft": "#392B1D",
        "nav": "#0E0B06", "nav_sel": "#1A140D", "nav_hover": "#17110B", "nav_text": "#A2927C", "title": "#F5EAD8",
        "hover_border": "#4A3623", "danger_bg": "#472A24", "danger_border": "#5C3630",
        "danger_text": "#E8C6C0",
        "cell_bg": "#191309", "cell_border": "#281F14",
        "cell_today_bg": "#211910", "cell_event_bg": "#1C150E", "cell_event_border": "#3F301F",
        "cell_out_bg": "#0F0C07", "cell_out_border": "#1C150E",
    },
    "日间白": {
        "bg": "#F3F5F8", "card": "#FFFFFF", "card_alt": "#FAFBFD", "border": "#DDE2E9",
        "text": "#262A31", "sub": "#6E7683", "accent": "#A87A3F", "accent_hover": "#C2924F",
        "input": "#FFFFFF", "btn": "#EEF1F5", "btn_hover": "#E3E8EF", "soft": "#DCE2EA",
        "nav": "#FFFFFF", "nav_sel": "#F1F4F8", "nav_hover": "#E9EDF4", "nav_text": "#5C6470", "title": "#1A1D23",
        "hover_border": "#C9D2DE", "danger_bg": "#FBEAEA", "danger_border": "#E9C2C2",
        "danger_text": "#A33A3A",
        "cell_bg": "#FFFFFF", "cell_border": "#E3E8EF",
        "cell_today_bg": "#FBF4E6", "cell_event_bg": "#F4F8FF", "cell_event_border": "#BFD2EA",
        "cell_out_bg": "#EDF0F5", "cell_out_border": "#E2E7EE",
    },
}

# 旧样式表中的固定色 -> 主题键
_COLOR_KEYS = {
    "#111318": "bg",
    "#1A1D24": "card",
    "#151820": "card_alt",
    "#262A33": "border",
    "#E8E6E1": "text",
    "#8D919B": "sub",
    "#C9A86A": "accent",
    "#D8BA82": "accent_hover",
    "#141720": "input",
    "#232833": "btn",
    "#2B3140": "btn_hover",
    "#2B303C": "soft",
    "#0D0F13": "nav",
    "#171B23": "nav_sel",
    "#141822": "nav_hover",
    "#E9E4D8": "title",
    "#9DA1AB": "nav_text",
    "#F2EFE8": "title",
    "#3B4252": "hover_border",
    "#4A2A2A": "danger_bg",
    "#5E3434": "danger_border",
    "#E8C7C7": "danger_text",
}

_current = "暗夜金"


def current_theme() -> str:
    return _current


def build_qss(base_qss: str, name: str = None, set_current: bool = True) -> str:
    """把基础样式表里的固定色替换成目标主题色"""
    global _current
    name = name or _current
    if name not in THEMES:
        name = "暗夜金"
    t = THEMES[name]
    if set_current:
        _current = name
    qss = base_qss
    tokens = {}
    for i, (old, key) in enumerate(_COLOR_KEYS.items()):
        tokens[old] = (f"@@C{i}@@", t[key])
    for old, (token, _) in tokens.items():
        qss = qss.replace(old, token)
    for old, (token, new) in tokens.items():
        qss = qss.replace(token, new)
    return qss


def cell_qss(kind: str = "normal") -> str:
    """月历格子的样式（跟随当前主题）"""
    t = THEMES.get(_current, THEMES["暗夜金"])
    if kind == "out":
        bg, border = t["cell_out_bg"], t["cell_out_border"]
    elif kind == "today":
        bg, border = t["cell_today_bg"], t["accent"]
    elif kind == "event":
        bg, border = t["cell_event_bg"], t["cell_event_border"]
    else:
        bg, border = t["cell_bg"], t["cell_border"]
    return f"QFrame{{background:{bg};border:1px solid {border};border-radius:8px;}}"


def theme_names():
    return list(THEMES.keys())
