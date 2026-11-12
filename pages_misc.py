# -*- coding: utf-8 -*-
"""备忘提醒 / 主持助理 / 备婚工具 / 开发者选项"""
import os
import sys
import json
import datetime
import logging
import threading

from PySide6.QtCore import Qt, QThread, Signal, QDate, QTime, QTimer
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QComboBox, QSpinBox, QDateEdit, QTimeEdit, QLineEdit, QTextEdit, QPlainTextEdit,
    QTextBrowser, QCheckBox,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QDialog, QDialogButtonBox, QAbstractItemView,
    QScrollArea, QSizePolicy, QApplication
)

import common
from common import DB, data_dir

logger = logging.getLogger(__name__)


def make_card(parent=None, alt=False):
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


# ============================================================
#  备忘提醒
# ============================================================
CATEGORIES = ["婚礼筹备", "客户沟通", "物料准备", "流程对接", "个人事务", ""]


class MemoDialog(QDialog):
    def __init__(self, db: DB, memo=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.memo = memo
        self.setWindowTitle("编辑提醒" if memo else "新建提醒")
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.setSpacing(10)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("例如：给王先生确认仪式流程")
        self.de_date = QDateEdit(QDate.currentDate().addDays(1))
        self.de_date.setCalendarPopup(True)
        self.de_date.setDisplayFormat("yyyy-MM-dd")
        self.te_time = QTimeEdit(QTime(9, 0))
        self.te_time.setDisplayFormat("HH:mm")
        self.cb_cat = QComboBox()
        self.cb_cat.setEditable(True)
        self.cb_cat.addItems(CATEGORIES)
        self.cb_imp = QCheckBox("标记为重要（强提醒）")
        form.addWidget(QLabel("内容"), 0, 0)
        form.addWidget(self.ed_title, 0, 1, 1, 3)
        form.addWidget(QLabel("日期"), 1, 0)
        form.addWidget(self.de_date, 1, 1)
        form.addWidget(QLabel("时间"), 1, 2)
        form.addWidget(self.te_time, 1, 3)
        form.addWidget(QLabel("分类"), 2, 0)
        form.addWidget(self.cb_cat, 2, 1, 1, 3)
        form.addWidget(self.cb_imp, 3, 0, 1, 4)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("保存")
        ok.setObjectName("Primary")
        cancel = QPushButton("取消")
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)
        ok.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        if memo:
            self.ed_title.setText(memo["title"])
            if memo["due"]:
                try:
                    dt = datetime.datetime.strptime(memo["due"], "%Y-%m-%d %H:%M")
                    self.de_date.setDate(QDate(dt.year, dt.month, dt.day))
                    self.te_time.setTime(QTime(dt.hour, dt.minute))
                except Exception:
                    pass
            self.cb_cat.setCurrentText(memo.get("category", ""))
            self.cb_imp.setChecked(bool(memo.get("important")))

    def save(self):
        title = self.ed_title.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请填写提醒内容")
            return
        due = f"{self.de_date.date().toString('yyyy-MM-dd')} {self.te_time.time().toString('HH:mm')}"
        if self.memo:
            self.db.update_memo(self.memo["id"], title=title, due=due,
                                category=self.cb_cat.currentText().strip(),
                                important=1 if self.cb_imp.isChecked() else 0)
        else:
            self.db.add_memo(title, due, self.cb_cat.currentText().strip(),
                             1 if self.cb_imp.isChecked() else 0)
        self.accept()


class MemoPage(QWidget):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("备忘提醒")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addSpacing(14)
        self.btn_add = QPushButton("＋ 新建提醒")
        self.btn_add.setObjectName("Primary")
        self.btn_add.clicked.connect(self.add)
        head.addWidget(self.btn_add)
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["全部提醒", "未完成", "已完成"])
        self.cb_filter.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.cb_filter)
        head.addStretch()
        self.cnt_label = QLabel("")
        self.cnt_label.setObjectName("SubTitle")
        head.addWidget(self.cnt_label)
        lay.addLayout(head)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["完成", "重要", "提醒内容", "提醒时间", "分类"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.edit_row)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_edit = QPushButton("编辑")
        self.btn_done = QPushButton("标记完成 / 取消完成")
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("Danger")
        self.btn_edit.clicked.connect(lambda: self.edit_row())
        self.btn_done.clicked.connect(self.toggle_done)
        self.btn_del.clicked.connect(self.delete)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_done)
        row.addWidget(self.btn_del)
        row.addStretch()
        tip = QLabel("应用在托盘后台运行时也会准时弹出提醒并响铃")
        tip.setObjectName("SubTitle")
        row.addWidget(tip)
        lay.addLayout(row)

        self.refresh()

    def refresh(self):
        self.memos = self.db.memos_all()
        filt = self.cb_filter.currentIndex()
        if filt == 1:
            self.memos = [m for m in self.memos if not m["done"]]
        elif filt == 2:
            self.memos = [m for m in self.memos if m["done"]]
        self.table.setRowCount(0)
        for m in self.memos:
            r = self.table.rowCount()
            self.table.insertRow(r)
            done = QTableWidgetItem("✓" if m["done"] else "")
            done.setTextAlignment(Qt.AlignCenter)
            done.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            done.setData(Qt.UserRole, m["id"])
            self.table.setItem(r, 0, done)
            star = QTableWidgetItem("★" if m["important"] else "")
            star.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, star)
            title_item = QTableWidgetItem(m["title"])
            title_item.setData(Qt.UserRole, m["id"])
            self.table.setItem(r, 2, title_item)
            self.table.setItem(r, 3, QTableWidgetItem(m["due"][:16] if m["due"] else ""))
            self.table.setItem(r, 4, QTableWidgetItem(m["category"] or ""))
            if m["done"]:
                for c in range(5):
                    self.table.item(r, c).setForeground(QColor("#6B707C"))
        open_n = len([m for m in self.memos if not m["done"]])
        self.cnt_label.setText(f"共 {len(self.memos)} 条提醒 · 未完成 {open_n} 条")
        # 复选框点击
        self.table.cellClicked.connect(self.on_cell)

    def on_cell(self, row, col):
        if col != 0:
            return
        it = self.table.item(row, 0)
        if not it:
            return
        mid = it.data(Qt.UserRole)
        done = 1 if it.text() != "✓" else 0
        self.db.update_memo(mid, done=done)
        self.refresh()

    def add(self):
        dlg = MemoDialog(self.db, None, self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()

    def edit_row(self, _item=None):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.memos):
            return
        m = self.memos[row]
        dlg = MemoDialog(self.db, m, self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()

    def toggle_done(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.memos):
            return
        m = self.memos[row]
        self.db.update_memo(m["id"], done=0 if m["done"] else 1)
        self.refresh()

    def delete(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.memos):
            return
        if QMessageBox.question(self, "确认", "确定删除这条提醒吗？") == QMessageBox.Yes:
            self.db.delete_memo(self.memos[row]["id"])
            self.refresh()


# ============================================================
#  主持助理
# ============================================================
# -*- coding: utf-8 -*-
"""主持助理 v4：对话 + 写词参考 + 图片识别 + DeepSeek 直连"""
import os
import re
import json
import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QComboBox, QLineEdit, QTextEdit, QTabWidget, QDialog, QMessageBox,
    QFileDialog, QApplication, QScrollArea, QCheckBox,
)

import common

STYLE_TEMPLATE = """我的写词习惯（请严格遵守）：
1) 开头必须落在一个具体的「物」或概念上（一束光、放映机、咖啡、秦岭、距离、时间），先讲来历 2-4 句再落到新人，绝不写「今天，我们相聚在这里」。
2) 白描代替抒情：只写动作、声音、光线、时间；禁用「感动 / 温暖 / 幸福 / 最美 / 命中注定」这类情绪词。
3) 数字与时间是最常用的修辞：一年半、一千公里、38 万公里、一万天。
4) 句子要短，平均 20 字上下；全篇感叹号不超过 1 个，尽量不用问号。
5) 人称：多用「他们」讲新人，用「你们」称来宾；「我」偶尔出现、要克制。
6) 结尾一律落到来宾：点出新人邀请的是一路支持和爱着他们的人，说「欢迎你们 / 欢迎各位」，最后一句 4-12 字。
7) 全篇最多一句幽默旁白；不解释主题；不虚构问卷以外的细节。
8) 篇幅：正文 280-350 字（如问卷写明时长，按 200 字/分钟估算）。
9) 可自然复用口头禅：三观一致气场相合 / 水到渠成 / 不着急 / 笃定 / 日子 / 房子 / 掌声有请 / 恭喜你们。"""

def _scan_api_keys():
    """在本机常见位置扫描 DeepSeek / OpenAI 兼容 API Key（只在本机使用，不上传）"""
    keys = []
    for env in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SILICONFLOW_API_KEY"):
        v = os.environ.get(env, "").strip()
        if v and v not in keys:
            keys.append(v)
    roots = [os.path.join(os.path.expanduser("~"), ".dsh"),
             os.path.join(os.path.expanduser("~"), ".deepseek"),
             os.path.join(os.environ.get("APPDATA", ""), "DeepSeek")]
    pat = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
    files = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count(os.sep) - root.count(os.sep) > 3:
                dirnames[:] = []
                continue
            for fn in filenames:
                if fn.lower().endswith((".json", ".yaml", ".yml", ".ini", ".env", ".txt")):
                    files.append(os.path.join(dirpath, fn))
    for path in files[:60]:
        try:
            if os.path.getsize(path) > 512 * 1024:
                continue
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for m in pat.findall(text):
            if m not in keys:
                keys.append(m)
    return keys


def _scan_local_models():
    """扫描本机 Ollama / vLLM 等 OpenAI 兼容服务，返回 [(模型名, base_url)]"""
    import requests
    out = []
    ports = [(11434, "http://127.0.0.1:11434"), (8000, "http://127.0.0.1:8000"),
             (1234, "http://127.0.0.1:1234"), (8080, "http://127.0.0.1:8080")]
    for port, base in ports:
        try:
            r = requests.get(base + "/api/tags", timeout=1.2)
            if r.ok:
                for m in r.json().get("models", []):
                    name = m.get("name", "")
                    if name:
                        out.append((name, base + "/v1", "ollama"))
                continue
        except Exception:
            pass
        try:
            r = requests.get(base + "/v1/models", timeout=1.2)
            if r.ok:
                for m in r.json().get("data", []):
                    out.append((m.get("id", ""), base + "/v1", "local"))
        except Exception:
            continue
    return out


def _chat(base, key, model, prompt, system=None, timeout=180, images=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if images:
        content = [{"type": "text", "text": prompt}]
        for b64 in images:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + b64}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    import requests
    base = (base or "").rstrip("/")
    if base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    r = requests.post(url, headers=headers, json={
        "model": model or "deepseek-chat",
        "messages": messages,
        "temperature": 0.75,
        "stream": False,
    }, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


class AIWorker(QThread):
    ok = Signal(str)
    err = Signal(str)

    def __init__(self, base, key, model, prompt, system=None, images=None):
        super().__init__()
        self.base, self.key, self.model = base, key, model
        self.prompt, self.system = prompt, system
        self.images = images or []

    def run(self):
        try:
            self.ok.emit(_chat(self.base, self.key, self.model, self.prompt,
                              self.system, images=self.images))
        except Exception as e:
            self.err.emit(str(e))


class ConnectDialog(QDialog):
    """模型连接设置：DeepSeek 官方 / 本地 Ollama / 自定义"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("AI 连接设置")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)

        tip = QLabel("直连 DeepSeek 或本机模型；本机扫描到的 Key 只保存在本机数据库。")
        tip.setObjectName("SubTitle")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        self.cb_provider = QComboBox()
        self.cb_provider.addItems(["DeepSeek 官方 API", "本地模型（Ollama / vLLM）", "自定义 OpenAI 兼容接口"])
        self.cb_provider.currentIndexChanged.connect(self._on_provider)
        g.addWidget(QLabel("接入方式"), 0, 0)
        g.addWidget(self.cb_provider, 0, 1, 1, 2)
        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("https://api.deepseek.com")
        g.addWidget(QLabel("接口地址"), 1, 0)
        g.addWidget(self.ed_base, 1, 1, 1, 2)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText("DeepSeek API Key（形如 sk-...）")
        g.addWidget(QLabel("API Key"), 2, 0)
        g.addWidget(self.ed_key, 2, 1, 1, 2)
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)
        self.cb_model.addItems(["deepseek-chat", "deepseek-reasoner", "deepseek-flash", "deepseek-r1:14b"])
        g.addWidget(QLabel("模型"), 3, 0)
        g.addWidget(self.cb_model, 3, 1, 1, 2)
        lay.addLayout(g)

        row = QHBoxLayout()
        b_scan = QPushButton("扫描本机 Key / 模型")
        b_scan.clicked.connect(self.scan)
        b_test = QPushButton("测试连接")
        b_test.clicked.connect(self.test)
        row.addWidget(b_scan)
        row.addWidget(b_test)
        row.addStretch()
        lay.addLayout(row)

        self.msg = QLabel("")
        self.msg.setObjectName("SubTitle")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)

        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(self.reject)
        b_save = QPushButton("保存")
        b_save.setObjectName("Primary")
        b_save.clicked.connect(self._save)
        btns.addWidget(b_cancel)
        btns.addWidget(b_save)
        lay.addLayout(btns)

        self._load()

    def _load(self):
        prov = self.db.get_setting("ai_provider", "deepseek")
        self.cb_provider.setCurrentIndex({"deepseek": 0, "local": 1, "custom": 2}.get(prov, 0))
        base = self.db.get_setting("ai_base_url", "")
        if not base and prov == "deepseek":
            base = "https://api.deepseek.com"
        self.ed_base.setText(base)
        self.ed_key.setText(self.db.get_setting("ai_api_key", ""))
        self.cb_model.setCurrentText(self.db.get_setting("ai_model", "deepseek-chat"))

    def _on_provider(self, idx):
        if idx == 0:
            self.ed_base.setText("https://api.deepseek.com")
            if self.cb_model.findText("deepseek-chat") >= 0:
                self.cb_model.setCurrentText("deepseek-chat")
        elif idx == 1:
            self.ed_base.setText("http://127.0.0.1:11434/v1")
            if self.cb_model.findText("deepseek-r1:14b") >= 0:
                self.cb_model.setCurrentText("deepseek-r1:14b")

    def scan(self):
        keys = _scan_api_keys()
        models = _scan_local_models()
        parts = []
        if keys:
            self.ed_key.setText(keys[0])
            parts.append(f"发现 {len(keys)} 个 API Key，已填入第一个")
        else:
            parts.append("未在本机找到 API Key（可用环境变量 DEEPSEEK_API_KEY）")
        if models:
            for name, base, kind in models[:8]:
                if self.cb_model.findText(name) < 0:
                    self.cb_model.addItem(name)
            self.cb_model.setCurrentText(models[0][0])
            self.cb_provider.setCurrentIndex(1)
            self.ed_base.setText(models[0][1])
            parts.append(f"发现本地模型：{models[0][0]}")
        self.msg.setText("；".join(parts))

    def test(self):
        base = self.ed_base.text().strip()
        if not base:
            self.msg.setText("请先填写接口地址")
            return
        self.msg.setText("正在测试…")
        QApplication.processEvents()
        try:
            reply = _chat(base, self.ed_key.text().strip(),
                          self.cb_model.currentText().strip(), "回答两个字：正常", timeout=20)
            self.msg.setText(f"连接正常：{reply.strip()[:30]}")
        except Exception as e:
            self.msg.setText(f"连接失败：{e}")

    def _save(self):
        idx = self.cb_provider.currentIndex()
        prov = "deepseek" if idx == 0 else ("local" if idx == 1 else "custom")
        base = self.ed_base.text().strip()
        if idx == 0 and not base:
            base = "https://api.deepseek.com"
        self.db.set_setting("ai_provider", prov)
        self.db.set_setting("ai_base_url", base)
        self.db.set_setting("ai_api_key", self.ed_key.text().strip())
        self.db.set_setting("ai_model", self.cb_model.currentText().strip())
        self.accept()


# ============================================================
#  主持助理（对话式）
# ============================================================
AI_STYLE_DIR = os.path.join(data_dir(), "ai_style")
AI_STYLE_INDEX = os.path.join(AI_STYLE_DIR, "index.json")
AI_STYLE_SEED = "builtin_style"


def _ensure_style_dir():
    os.makedirs(AI_STYLE_DIR, exist_ok=True)
    if not os.path.exists(AI_STYLE_INDEX):
        fid = AI_STYLE_SEED
        path = os.path.join(AI_STYLE_DIR, fid + ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(STYLE_TEMPLATE)
        with open(AI_STYLE_INDEX, "w", encoding="utf-8") as f:
            json.dump([{"id": fid, "name": "我的写词习惯（内置）",
                        "file": fid + ".txt", "builtin": True}],
                      f, ensure_ascii=False, indent=1)


def _load_style_metas():
    _ensure_style_dir()
    try:
        with open(AI_STYLE_INDEX, encoding="utf-8") as f:
            metas = json.load(f)
        if isinstance(metas, list):
            return metas
    except Exception:
        pass
    return []


def _save_style_metas(metas):
    with open(AI_STYLE_INDEX, "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False, indent=1)


def _read_doc_text(path):
    """读取常见文档格式（docx/doc/pdf/rtf/odt/txt/md/html/pptx/ppt/xlsx/xls/csv/epub/wps）"""
    import docio
    return docio.read_text(path)


class ChatInput(QPlainTextEdit):
    """对话输入框：Enter 发送（仅本控件内生效），Shift+Enter 换行"""

    sendRequested = Signal()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not (ev.modifiers() & Qt.ShiftModifier):
            self.sendRequested.emit()
            return
        super().keyPressEvent(ev)


class AIWriterPage(QWidget):
    """和 AI 直接对话：写台词、想创意、改稿；对话就是唯一的生成框"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.worker = None
        self._busy = False
        self._last_reply = ""
        self.history = []
        self._images = []
        _ensure_style_dir()
        self._build()
        self._refresh_docs()
        self._refresh_status()
        self._refresh_questionnaires()

    # ---------- 界面 ----------
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("主持助理")
        title.setObjectName("Title")
        sub = QLabel("写台词、想创意、改稿、读图，都在对话里完成")
        sub.setObjectName("SubTitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox)
        head.addStretch()
        self.status = QLabel("")
        self.status.setObjectName("SubTitle")
        head.addWidget(self.status)
        b_conn = QPushButton("连接设置")
        b_conn.clicked.connect(self.open_connect)
        head.addWidget(b_conn)
        lay.addLayout(head)

        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        mrow.addWidget(QLabel("模型"))
        self.cb_model_pick = QComboBox()
        self.cb_model_pick.setMinimumWidth(260)
        self.cb_model_pick.activated.connect(self._on_model_pick)
        mrow.addWidget(self.cb_model_pick, 1)
        b_scanm = QPushButton("扫描模型")
        b_scanm.clicked.connect(self.scan_models)
        mrow.addWidget(b_scanm)
        lay.addLayout(mrow)

        qrow = QHBoxLayout()
        qrow.setSpacing(8)
        qrow.addWidget(QLabel("客户问卷"))
        self.cb_questionnaire = QComboBox()
        self.cb_questionnaire.setMinimumWidth(320)
        self.cb_questionnaire.activated.connect(self._on_questionnaire_changed)
        qrow.addWidget(self.cb_questionnaire, 1)
        self.lb_questionnaire = QLabel("未选择（可选）")
        self.lb_questionnaire.setObjectName("SubTitle")
        qrow.addWidget(self.lb_questionnaire)
        b_qrefresh = QPushButton("刷新")
        b_qrefresh.clicked.connect(self._refresh_questionnaires)
        qrow.addWidget(b_qrefresh)
        lay.addLayout(qrow)

        left = make_card()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 12, 16, 12)
        lv.setSpacing(8)
        bar_top = QHBoxLayout()
        lb_chat = QLabel("对话")
        lb_chat.setObjectName("SectionTitle")
        bar_top.addWidget(lb_chat)
        bar_top.addStretch()
        b_copy = QPushButton("复制最近回复")
        b_copy.clicked.connect(self.copy_result)
        b_word = QPushButton("导出 Word")
        b_word.clicked.connect(self.export_word)
        b_clear = QPushButton("清空对话")
        b_clear.clicked.connect(self.clear_chat)
        bar_top.addWidget(b_copy)
        bar_top.addWidget(b_word)
        bar_top.addWidget(b_clear)
        lv.addLayout(bar_top)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setPlaceholderText("直接说你要什么：写开场白、写完整主持词、想 12 个创意环节、改一版……")
        self.chat.setStyleSheet("QTextBrowser{background:transparent;border:none;}")
        self.chat.setFont(QFont("Microsoft YaHei UI", 11))
        lv.addWidget(self.chat, 1)

        # 四个快捷入口：两列两行，保证文字完整可读
        qgrid = QGridLayout()
        qgrid.setSpacing(6)
        for i, (label, skeleton) in enumerate([
            ("写开场白", "帮我写一段婚礼开场白。新人信息："),
            ("完整主持词", "帮我写一份完整的婚礼主持词。新人故事 / 问卷信息："),
            ("12 个创意环节", "给我 12 个适合这对新人的创意环节，要能落地。新人信息："),
            ("改一版", "把下面这段改得更克制、更像口语：\n"),
        ]):
            b = QPushButton(label)
            b.setMinimumHeight(32)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, s=skeleton: self._fill_input(s))
            qgrid.addWidget(b, i // 2, i % 2)
        lv.addLayout(qgrid)

        # 附件：文档 + 图片，都直接放在对话框里
        arow = QHBoxLayout()
        arow.setSpacing(6)
        b_updoc = QPushButton("上传文档")
        b_updoc.setToolTip("支持 doc/docx/pdf/rtf/odt/txt/md/html/pptx/xlsx 等常见文档")
        b_updoc.clicked.connect(self.upload_docs)
        b_upimg = QPushButton("上传图片")
        b_upimg.setToolTip("上传现场图、参考图或手写稿，当前模型需支持识图")
        b_upimg.clicked.connect(self.upload_images)
        self.btn_docs = QPushButton("写词参考 0 篇")
        self.btn_docs.clicked.connect(self.manage_docs)
        arow.addWidget(b_updoc)
        arow.addWidget(b_upimg)
        arow.addWidget(self.btn_docs)
        arow.addStretch()
        lv.addLayout(arow)

        self.img_bar = QWidget()
        self.img_lay = QHBoxLayout(self.img_bar)
        self.img_lay.setContentsMargins(0, 0, 0, 0)
        self.img_lay.setSpacing(6)
        self.img_bar.hide()
        lv.addWidget(self.img_bar)

        self.ed_input = ChatInput()
        self.ed_input.setFixedHeight(104)
        self.ed_input.setPlaceholderText(
            "直接和 AI 说，比如：\n"
            "· 新郎叫陈默，新娘林夏，异地两年，帮我写 300 字左右的入场后开场白\n"
            "· 给我 12 个不落俗套的仪式创意，不要香槟塔\n"
            "· 这张是现场布置图，帮我写一段和它呼应的开场词")
        self.ed_input.sendRequested.connect(self.send_chat)
        lv.addWidget(self.ed_input)

        row = QHBoxLayout()
        hint = QLabel("Enter 发送 · Shift+Enter 换行 · 图片会随问题一起发给当前模型")
        hint.setObjectName("SubTitle")
        row.addWidget(hint)
        row.addStretch()
        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumWidth(96)
        self.btn_send.clicked.connect(self.send_chat)
        row.addWidget(self.btn_send)
        lv.addLayout(row)

        lay.addWidget(left, 1)
        self._populate_models(False)

    # ---------- 连接与模型 ----------
    def _settings(self):
        base = self.db.get_setting("ai_base_url", "")
        key = self.db.get_setting("ai_api_key", "")
        model = self.db.get_setting("ai_model", "") or "deepseek-chat"
        return base, key, model

    def _refresh_status(self):
        base, key, model = self._settings()
        if not base:
            base = "https://api.deepseek.com"
            self.db.set_setting("ai_base_url", base)
            self.db.set_setting("ai_model", model)
        if "deepseek.com" in base and not key:
            self.status.setText("● DeepSeek · 待填写 API Key")
            self.status.setStyleSheet("color:#C08A5E;")
        else:
            kind = "DeepSeek" if "deepseek.com" in base else "本地 / 自定义"
            self.status.setText(f"● {kind} · {model}")
            self.status.setStyleSheet("color:#7FA98E;")

    def open_connect(self):
        dlg = ConnectDialog(self.db, self)
        if dlg.exec():
            self._refresh_status()
            self._populate_models(True)
            QMessageBox.information(self, "已保存", "模型连接设置已保存。")

    def _populate_models(self, scan=False):
        items = []
        cur_base, _k, cur_model = self._settings()
        if cur_base:
            items.append((f"当前 · {cur_model}", cur_base, cur_model))
        items.append(("DeepSeek · deepseek-chat", "https://api.deepseek.com", "deepseek-chat"))
        items.append(("DeepSeek · deepseek-reasoner", "https://api.deepseek.com", "deepseek-reasoner"))
        imported = []
        if scan:
            try:
                imported = _scan_local_models()
            except Exception:
                imported = []
            for name, base, kind in imported:
                items.append((f"本机 · {name}", base, name))
        self.cb_model_pick.blockSignals(True)
        self.cb_model_pick.clear()
        for label, base, model in items:
            self.cb_model_pick.addItem(label)
            self.cb_model_pick.setItemData(self.cb_model_pick.count() - 1,
                                           (base, model), Qt.UserRole)
        self.cb_model_pick.blockSignals(False)
        for i in range(self.cb_model_pick.count()):
            base, model = self.cb_model_pick.itemData(i, Qt.UserRole)
            if base == cur_base and model == cur_model:
                self.cb_model_pick.setCurrentIndex(i)
                break
        if imported:
            self.status.setText(self.status.text() + "  · 已扫描本地模型")
        return len(imported)

    def scan_models(self):
        self._populate_models(True)

    def _on_model_pick(self, idx):
        data = self.cb_model_pick.itemData(idx, Qt.UserRole)
        if not data:
            return
        base, model = data
        self.db.set_setting("ai_base_url", base)
        self.db.set_setting("ai_model", model)
        self._refresh_status()

    def _require_model(self):
        base, key, model = self._settings()
        if not base:
            QMessageBox.information(self, "未连接模型",
                                    "请先在右上角「连接设置」里接入 DeepSeek 或本机模型。")
            return None
        return base, key, model

    # ---------- 对话 ----------
    @staticmethod
    def _esc(text):
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br/>"))

    def _append_chat(self, who, text):
        color = "#C9A86A" if who == "u" else "#7FA98E"
        label = "你" if who == "u" else "AI"
        self.chat.append(
            f"<p style='margin:6px 0'><b style='color:{color}'>{label}</b><br/>"
            f"{self._esc(text)}</p>")
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _fill_input(self, skeleton):
        self.ed_input.setPlainText(skeleton)
        self.ed_input.setFocus()
        from PySide6.QtGui import QTextCursor
        self.ed_input.moveCursor(QTextCursor.End)

    def _style_text(self):
        metas = _load_style_metas()
        chunks = []
        total = 0
        for m in metas:
            path = os.path.join(AI_STYLE_DIR, m.get("file", ""))
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    text = f.read().strip()
            except Exception:
                continue
            if not text:
                continue
            text = text[:8000]
            chunks.append(f"《{m.get('name', '风格文档')}》\n{text}")
            total += len(text)
            if total > 18000:
                break
        return "\n\n".join(chunks)

    def _refresh_questionnaires(self):
        if not hasattr(self, "cb_questionnaire"):
            return
        cur = self.cb_questionnaire.currentData()
        self.cb_questionnaire.blockSignals(True)
        self.cb_questionnaire.clear()
        self.cb_questionnaire.addItem("不使用问卷", 0)
        try:
            rows = self.db.questionnaires()
        except Exception:
            rows = []
        for q in rows:
            label = f"{q.get('wedding_date','')} · {q.get('couple','')}"
            self.cb_questionnaire.addItem(label, q["id"])
        idx = self.cb_questionnaire.findData(cur)
        self.cb_questionnaire.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_questionnaire.blockSignals(False)
        self._on_questionnaire_changed()

    def _on_questionnaire_changed(self, *_):
        qid = self.cb_questionnaire.currentData() if hasattr(self, "cb_questionnaire") else 0
        if not qid:
            self.lb_questionnaire.setText("未选择（可选）")
            return
        try:
            q = self.db.questionnaire(qid)
            n = len(self.db.questionnaire_submissions(qid))
        except Exception:
            q, n = None, 0
        self.lb_questionnaire.setText(f"已选：{q.get('couple','')} · {n} 份提交" if q else "未选择")

    def _questionnaire_context(self):
        qid = self.cb_questionnaire.currentData() if hasattr(self, "cb_questionnaire") else 0
        if not qid:
            return ""
        try:
            q = self.db.questionnaire(qid)
            subs = self.db.questionnaire_submissions(qid)
        except Exception:
            return ""
        if not q:
            return ""
        lines = [f"【已选客户问卷】{q.get('couple','')} · {q.get('wedding_date','')} · {q.get('venue','')}"]
        if not subs:
            lines.append("目前还没有客户提交记录；请基于问卷结构提问，不要虚构答案。")
            if q.get("template_text"):
                lines.append("问卷结构：\n" + q.get("template_text", "")[:2000])
            return "\n".join(lines)
        for i, s in enumerate(subs[:5], 1):
            try:
                ans = json.loads(s.get("answers_json") or "{}")
            except Exception:
                ans = {}
            parts = [f"{k}：{v}" for k, v in ans.items() if str(v).strip()]
            lines.append(f"提交{i}（{s.get('created','')}）：\n" + "\n".join(parts)[:3000])
        if len(subs) > 5:
            lines.append(f"（另有 {len(subs)-5} 份提交未展开）")
        return "\n".join(lines)

    def showEvent(self, e):
        super().showEvent(e)
        self._refresh_questionnaires()

    def _system_prompt(self):
        lines = [
            "你是婚礼主持人鹏飞的写作搭档，帮他写婚礼台词、创意环节、改稿和想说法。",
            "回复要求：直接用中文给他能上口的文本；不要解释你在做什么，不要输出模板或套话说明；"
            "台词按环节分段、可直接朗读；创意给能落地的做法；信息不够时先问一个最关键的问题。",
        ]
        style = self._style_text()
        if style:
            lines.append("\n【鹏飞的写词习惯 / 范文（来自他上传的文档，请严格模仿其句式、用词与节奏）】\n"
                         + style)
        qctx = self._questionnaire_context()
        if qctx:
            lines.append("\n" + qctx + "\n以上问卷信息只用于本次写词，不要向客户复述隐私。")
        return "\n".join(lines)

    def _chat_prompt(self, text):
        lines = []
        for role, t in self.history[-12:]:
            lines.append(("用户：" if role == "u" else "助理：") + t)
        lines.append("用户：" + text)
        return "\n".join(lines)

    def send_chat(self):
        if self._busy:
            return
        text = self.ed_input.toPlainText().strip()
        images = [im["b64"] for im in getattr(self, "_images", [])]
        if not text and not images:
            return
        if not text:
            text = "请先理解这张图片的内容，再从婚礼主持的角度告诉我可以怎么用。"
        cfg = self._require_model()
        if not cfg:
            return
        base, key, model = cfg
        prompt = self._chat_prompt(text)
        shown = text + (f"（附图 {len(images)} 张）" if images else "")
        self._append_chat("u", shown)
        self.history.append(("u", text))
        self.ed_input.clear()
        self._clear_images()
        self._last_had_image = bool(images)
        self._set_busy(True)
        self.status.setText("正在识图并回复…" if images else "正在等模型回复…")
        self.worker = AIWorker(base, key, model, prompt, self._system_prompt(), images=images)
        self.worker.ok.connect(self._on_ok)
        self.worker.err.connect(self._on_err)
        self.worker.start()

    def _set_busy(self, busy):
        self._busy = busy
        self.btn_send.setEnabled(not busy)
        self.btn_send.setText("思考中…" if busy else "发送")

    def _on_ok(self, text):
        self._set_busy(False)
        text = (text or "").strip()
        if not text:
            return
        self._last_reply = text
        self.history.append(("a", text))
        self._append_chat("a", text)
        self.status.setText(f"已回复 · {len(text.replace(' ', ''))} 字")

    def _on_err(self, err):
        self._set_busy(False)
        self.status.setText("调用失败")
        self._append_chat("a", "调用失败：" + str(err))
        extra = ""
        if getattr(self, "_last_had_image", False):
            extra = ("\n\n这次带了图片：当前模型可能不支持识图。请到「连接设置」换成"
                     "支持图片的模型（如 qwen-vl、gpt-4o、glm-4v 系列），再发送一次。")
        QMessageBox.warning(self, "模型调用失败",
                            f"{err}{extra}\n\n也可在「连接设置」里测试接口，或换成本地模型。")

    def clear_chat(self):
        self.chat.clear()
        self.history = []
        self._last_reply = ""
        self._clear_images()
        self.status.setText("对话已清空")

    # ---------- 写词参考文档 ----------
    def _refresh_docs(self):
        metas = _load_style_metas()
        self._metas = metas
        n = len(metas)
        self.btn_docs.setText(f"写词参考 {n} 篇")
        tip = "\n".join(f"· {m.get('name', '文档')}" for m in metas[:8])
        self.btn_docs.setToolTip(tip or "还没有参考文档")

    def upload_docs(self):
        import docio
        files, _ = QFileDialog.getOpenFileNames(
            self, "上传写词参考", "", docio.FILE_FILTER)
        if not files:
            return
        metas = _load_style_metas()
        added = 0
        errors = []
        for path in files:
            try:
                text = _read_doc_text(path)
            except Exception as e:
                logger.warning("读取文档失败 %s: %s", path, e)
                errors.append(f"{os.path.basename(path)}：{e}")
                continue
            if not text:
                errors.append(f"{os.path.basename(path)}：没有读到文字"
                              "（扫描版 PDF 需要先 OCR）")
                continue
            fid = "u" + datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
            with open(os.path.join(AI_STYLE_DIR, fid + ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
            metas.append({"id": fid, "name": os.path.splitext(os.path.basename(path))[0],
                          "file": fid + ".txt", "builtin": False})
            added += 1
        _save_style_metas(metas)
        self._refresh_docs()
        if added:
            QMessageBox.information(self, "已上传",
                                    f"已加入 {added} 篇参考文档，之后的对话会参考它。")
        if errors:
            QMessageBox.warning(self, "部分文件没读出来",
                                "\n".join(errors[:8]) +
                                "\n\n支持 doc/docx/pdf/rtf/odt/txt/md/html/pptx/xlsx 等；"
                                ".doc/.wps 需要本机有 Word 或 WPS。")

    def manage_docs(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("写词参考文档")
        dlg.resize(680, 500)
        v = QVBoxLayout(dlg)
        tip = QLabel("这些文档会作为写词参考一起发给模型；双击可查看全文。")
        tip.setObjectName("SubTitle")
        v.addWidget(tip)
        lst = QListWidget()
        lst.setObjectName("Plain")
        v.addWidget(lst, 1)

        def fill():
            lst.clear()
            for m in _load_style_metas():
                path = os.path.join(AI_STYLE_DIR, m.get("file", ""))
                n = 0
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        n = len(f.read())
                except Exception:
                    n = 0
                it = QListWidgetItem(f"{m.get('name', '文档')}  ·  {n} 字")
                it.setData(Qt.UserRole, m)
                lst.addItem(it)

        def view():
            it = lst.currentItem()
            if not it:
                return
            m = it.data(Qt.UserRole) or {}
            try:
                with open(os.path.join(AI_STYLE_DIR, m.get("file", "")),
                          encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                return
            d = QDialog(dlg)
            d.setWindowTitle(m.get("name", "参考文档"))
            d.resize(720, 560)
            dv = QVBoxLayout(d)
            ed = QTextEdit()
            ed.setReadOnly(True)
            ed.setPlainText(text)
            dv.addWidget(ed)
            bb = QDialogButtonBox(QDialogButtonBox.Close)
            bb.button(QDialogButtonBox.Close).setText("关闭")
            bb.rejected.connect(d.reject)
            dv.addWidget(bb)
            d.exec()

        def remove():
            it = lst.currentItem()
            if not it:
                return
            m = it.data(Qt.UserRole) or {}
            if QMessageBox.question(dlg, "删除", f"删除参考文档《{m.get('name', '')}》？") != QMessageBox.Yes:
                return
            try:
                os.remove(os.path.join(AI_STYLE_DIR, m.get("file", "")))
            except Exception:
                pass
            keep = [x for x in _load_style_metas() if x.get("id") != m.get("id")]
            _save_style_metas(keep)
            fill()
            self._refresh_docs()

        lst.itemDoubleClicked.connect(lambda _it: view())
        row = QHBoxLayout()
        b_add = QPushButton("上传文档…")
        b_add.setObjectName("Primary")
        b_add.clicked.connect(lambda: (self.upload_docs(), fill()))
        b_view = QPushButton("查看")
        b_view.clicked.connect(view)
        b_del = QPushButton("删除")
        b_del.setObjectName("Danger")
        b_del.clicked.connect(remove)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(dlg.accept)
        row.addWidget(b_add)
        row.addWidget(b_view)
        row.addWidget(b_del)
        row.addStretch()
        row.addWidget(b_close)
        v.addLayout(row)
        fill()
        dlg.exec()

    # ---------- 图片 ----------
    def upload_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "上传图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not files:
            return
        from PIL import Image
        import base64
        import io as _io
        added = 0
        for path in files:
            try:
                im = Image.open(path).convert("RGB")
                im.thumbnail((1440, 1440))
                buf = _io.BytesIO()
                im.save(buf, "JPEG", quality=88)
                raw = buf.getvalue()
                b64 = base64.b64encode(raw).decode("ascii")
                thumb = QPixmap.fromImage(
                    QPixmap(path).toImage().scaled(52, 52, Qt.KeepAspectRatioByExpanding,
                                                   Qt.SmoothTransformation))
                self._images.append({"name": os.path.basename(path), "b64": b64,
                                     "thumb": thumb})
                added += 1
            except Exception as e:
                logger.warning("读取图片失败 %s: %s", path, e)
        if added:
            self._refresh_image_bar()
            self.status.setText(f"已添加 {added} 张图片，发送时会一起交给模型识别")
            base, _key, model = self._settings()
            probe = (base + " " + model).lower()
            if "deepseek" in probe and "vl" not in probe and "vision" not in probe:
                QMessageBox.information(
                    self, "识图提示",
                    "当前连接的是 DeepSeek 文本模型，不能直接看图。\n"
                    "图片已加入；如果发送后模型报错，请到「连接设置」换成支持看图的模型"
                    "（如 qwen-vl、gpt-4o、glm-4v 系列）。")

    def _refresh_image_bar(self):
        while self.img_lay.count():
            it = self.img_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, im in enumerate(self._images):
            box = QFrame()
            box.setObjectName("CardAlt")
            h = QHBoxLayout(box)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(4)
            lb = QLabel()
            lb.setPixmap(im["thumb"])
            lb.setToolTip(im["name"])
            lb.setFixedSize(36, 36)
            b = QPushButton("×")
            b.setFixedSize(20, 20)
            b.setToolTip("移除这张图片")
            b.clicked.connect(lambda _=False, idx=i: self.remove_image(idx))
            h.addWidget(lb)
            h.addWidget(b)
            self.img_lay.addWidget(box)
        self.img_lay.addStretch()
        self.img_bar.setVisible(bool(self._images))

    def remove_image(self, idx):
        if 0 <= idx < len(self._images):
            self._images.pop(idx)
            self._refresh_image_bar()

    def _clear_images(self):
        self._images = []
        self._refresh_image_bar()

    def _refresh_meta_after_docs(self):
        self._refresh_docs()

    # ---------- 结果 ----------
    def copy_result(self):
        text = (self._last_reply or "").strip()
        if not text:
            QMessageBox.information(self, "提示", "还没有可复制的回复")
            return
        QApplication.clipboard().setText(text)
        self.status.setText("已复制到剪贴板")

    def export_word(self):
        text = (self._last_reply or "").strip()
        if not text:
            QMessageBox.information(self, "提示", "还没有可导出的回复")
            return
        d = os.path.join(data_dir(), "主持词")
        os.makedirs(d, exist_ok=True)
        default = os.path.join(d, f"主持助理_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.docx")
        path, _ = QFileDialog.getSaveFileName(self, "导出 Word", default, "Word 文档 (*.docx)")
        if not path:
            return
        try:
            from docx import Document
            doc = Document()
            doc.add_heading("主持助理", 0)
            for line in text.splitlines():
                doc.add_paragraph(line)
            doc.save(path)
            QMessageBox.information(self, "已导出", path)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))


# ============================================================
#  备婚工具
# ============================================================
BUILTIN_TEMPLATES = [
    ("婚前 30 天准备清单", [
        "婚前 30 天准备清单",
        "一、婚庆与人员",
        "□ 确认婚庆公司、主持人、摄影、摄像、化妆（四大金刚）档期与合同",
        "□ 与主持人沟通流程偏好、交接环节、特殊禁忌",
        "二、礼服与造型",
        "□ 婚纱、礼服试穿与修改；西装定制完成",
        "□ 预定试妆时间，确认婚礼当天造型",
        "□ 准备婚鞋、头纱、首饰、隐形眼镜",
        "三、证件与手续",
        "□ 领取结婚证",
        "□ 婚前体检（如需要）",
        "□ 核对身份证、户口本等证件",
        "四、宾客与场地",
        "□ 发送请柬 / 电子邀请函，统计出席人数",
        "□ 确定桌数与座位表",
        "□ 与酒店确认菜单、酒水、服务费",
        "□ 确认婚车车队与路线",
        "五、物料准备",
        "□ 婚礼请柬、签到本、桌卡、迎宾牌",
        "□ 喜糖、伴手礼、红包（改口、堵门、工作人员）",
        "□ 戒指、戒枕、誓言卡",
        "六、仪式准备",
        "□ 确定婚礼音乐清单并试播",
        "□ 制作成长视频 / 求婚视频",
        "□ 婚礼前 1-2 天完成彩排",
        "七、个人状态",
        "□ 保证睡眠，提前护肤",
        "□ 婚礼当天物品打包清单整理",
    ]),
    ("婚礼当天流程时间表", [
        "婚礼当天流程时间表（可按实际时间调整）",
        "05:30  新娘起床、洗漱、吃早餐",
        "06:00  化妆师到位，开始化妆",
        "07:30  摄影摄像到位，拍摄晨袍、化妆花絮",
        "08:30  接亲车队出发（提前确认路线与堵门时间）",
        "09:00  到达新娘家，堵门游戏（控制在 20 分钟内）",
        "09:40  完成接亲，出发前往酒店",
        "10:20  到达酒店，新娘补妆、休息",
        "10:50  宾客签到、合影区拍照",
        "11:18  婚礼仪式开始（黄金时间）",
        "11:58  仪式结束，新人退场",
        "12:08  全体合影 / 亲友合影",
        "12:18  午宴开始",
        "13:00  新人换敬酒服",
        "13:20  逐桌敬酒",
        "14:10  送客、发伴手礼",
        "14:40  工作人员收尾、结算",
        "备注：以上为午宴示例，晚宴可将时间整体后移；每个环节预留 5-10 分钟弹性。",
    ]),
    ("婚礼物品清单", [
        "婚礼物品清单",
        "一、证件类",
        "□ 身份证、户口本、结婚证",
        "□ 酒店合同、婚庆合同",
        "二、服饰类",
        "□ 婚纱、敬酒服、秀禾服",
        "□ 西装、衬衫、领结、袖扣",
        "□ 婚鞋（主婚鞋 + 备用平底鞋）",
        "□ 头纱、皇冠、耳环、项链",
        "三、仪式类",
        "□ 结婚戒指、戒枕",
        "□ 誓言卡、主持词提示卡",
        "□ 香槟塔、香槟酒",
        "□ 蜡烛、点火器",
        "□ 签到本、签字笔、签到牌",
        "四、布置类",
        "□ 迎宾牌、指引牌",
        "□ 桌卡、席位图",
        "□ 喜糖、伴手礼",
        "□ 手捧花、胸花、腕花",
        "五、应急类",
        "□ 针线包、别针、双面胶",
        "□ 创可贴、常用药、纸巾",
        "□ 备用丝袜、吸管（防口红沾杯）",
        "□ 充电宝、数据线",
        "□ 雨伞 / 防晒",
        "六、红包类",
        "□ 改口红包、堵门红包",
        "□ 给司机、摄影、化妆等工作人员的红包",
    ]),
    ("应急预案与联系人", [
        "婚礼应急预案",
        "一、天气突变（户外婚礼）",
        "预案：提前确认室内备用场地；准备透明雨伞、雨棚；通知宾客改期或改地点的话术模板。",
        "二、设备故障",
        "预案：音响备用音箱、备用 U 盘（存全部音乐）、备用电池；提前 1 小时试音。",
        "三、人员缺席",
        "预案：伴郎伴娘各留 1 名替补；重要嘉宾缺席时由主持人灵活调整环节。",
        "四、时间延误",
        "预案：仪式环节设置可删减段落；主持人准备 2 分钟暖场内容填补空档。",
        "五、突发身体不适",
        "预案：准备急救包；确认最近医院路线；安排 1 名亲友负责应急。",
        "",
        "重要联系人",
        "婚庆负责人：____________  电话：____________",
        "酒店宴会经理：__________  电话：____________",
        "摄影：__________________  电话：____________",
        "摄像：__________________  电话：____________",
        "化妆师：________________  电话：____________",
        "车队队长：______________  电话：____________",
        "新人紧急联系人：________  电话：____________",
    ]),
    ("主持词提示卡", [
        "主持词提示卡（现场速记版）",
        "【开场前 5 分钟】",
        "· 确认音响、话筒、音乐就位",
        "· 与新人确认入场站位、父母位置",
        "· 提醒摄影摄像就位",
        "【开场】",
        "· 问候来宾，介绍自己",
        "· 引入今天的主题与新人故事",
        "【新人入场】",
        "· 宣布新人入场，引导掌声",
        "· 注意新娘裙摆、伴娘协助",
        "【仪式核心】",
        "· 誓言环节：递话筒、留停顿",
        "· 交换戒指：提醒伴娘递上戒枕",
        "· 感恩环节：确认父母上台路线",
        "【互动与高潮】",
        "· 亲友祝福 / 游戏环节（控制 5 分钟内）",
        "· 香槟塔 / 切蛋糕（如安排）",
        "【结束】",
        "· 宣布礼成，引导合影",
        "· 提醒午宴/晚宴开席时间与敬酒安排",
        "【临场提醒】",
        "· 语速放慢，重要名字提前确认读音",
        "· 遇突发情况先稳住现场，再灵活调整",
    ]),
]


class PrepToolsPage(QWidget):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("备婚工具")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addSpacing(12)
        tip = QLabel("勾选需要的模板，一键生成 Word 文档，可直接发给新人")
        tip.setObjectName("SubTitle")
        head.addWidget(tip)
        head.addStretch()
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(12)
        left = make_card()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 16, 16)
        lv.setSpacing(8)
        lv.addWidget(QLabel("内置模板（可多选）"))
        self.template_checks = []
        for name, _ in BUILTIN_TEMPLATES:
            cb = QCheckBox(name)
            cb.setChecked(True)
            lv.addWidget(cb)
            self.template_checks.append(cb)
        lv.addSpacing(8)
        lv.addWidget(QLabel("我的模板"))
        self.user_list = QListWidget()
        self.user_list.setObjectName("Plain")
        self.user_list.setFixedHeight(120)
        lv.addWidget(self.user_list)
        row = QHBoxLayout()
        b_imp = QPushButton("导入 Word 模板")
        b_imp.clicked.connect(self.import_template)
        b_del = QPushButton("移除")
        b_del.clicked.connect(self.remove_template)
        row.addWidget(b_imp)
        row.addWidget(b_del)
        lv.addLayout(row)
        lv.addStretch()
        body.addWidget(left, 1)

        right = make_card()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(10)
        t = QLabel("导出")
        t.setObjectName("SectionTitle")
        rv.addWidget(t)
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["合并为一个 Word 文档", "分别导出为多个文档"])
        rv.addWidget(self.cb_mode)
        self.btn_export = QPushButton("生成并导出")
        self.btn_export.setObjectName("Primary")
        self.btn_export.clicked.connect(self.export)
        rv.addWidget(self.btn_export)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("导出记录会显示在这里……")
        rv.addWidget(self.log, 1)
        body.addWidget(right, 1)
        lay.addLayout(body, 1)

        self.load_user_templates()

    def load_user_templates(self):
        self.user_list.clear()
        cur = self.db.conn.execute("SELECT * FROM prep_templates WHERE builtin=0")
        self.user_items = [dict(r) for r in cur.fetchall()]
        for it in self.user_items:
            row = QListWidgetItem(it["name"])
            row.setData(Qt.UserRole, it["path"])
            self.user_list.addItem(row)

    def import_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Word 模板", "", "Word 文档 (*.docx)")
        if not path:
            return
        d = os.path.join(data_dir(), "templates")
        os.makedirs(d, exist_ok=True)
        target = os.path.join(d, os.path.basename(path))
        try:
            import shutil
            shutil.copy2(path, target)
            self.db.conn.execute("INSERT INTO prep_templates(name, path, builtin) VALUES(?,?,0)",
                                 (os.path.splitext(os.path.basename(path))[0], target))
            self.db.conn.commit()
            self.load_user_templates()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def remove_template(self):
        it = self.user_list.currentItem()
        if not it:
            return
        path = it.data(Qt.UserRole)
        self.db.conn.execute("DELETE FROM prep_templates WHERE path=?", (path,))
        self.db.conn.commit()
        self.load_user_templates()

    def export(self):
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor
        except Exception as e:
            QMessageBox.warning(self, "缺少依赖", f"python-docx 不可用：{e}")
            return

        selected_builtin = [BUILTIN_TEMPLATES[i] for i, cb in enumerate(self.template_checks) if cb.isChecked()]
        selected_user = [it for it in getattr(self, "user_items", [])
                         if self.user_list.currentItem() and False]  # 简化：用户模板单独导出
        if not selected_builtin:
            QMessageBox.information(self, "提示", "请至少勾选一个内置模板")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "选择保存文件夹", data_dir())
        if not out_dir:
            return
        try:
            if self.cb_mode.currentIndex() == 0:
                doc = Document()
                style = doc.styles["Normal"]
                style.font.name = "Microsoft YaHei"
                style.font.size = Pt(11)
                for idx, (name, lines) in enumerate(selected_builtin):
                    if idx > 0:
                        doc.add_page_break()
                    h = doc.add_heading(name, level=1)
                    for ln in lines[1:]:
                        p = doc.add_paragraph(ln)
                        p.paragraph_format.space_after = Pt(4)
                fname = f"备婚资料_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.docx"
                path = os.path.join(out_dir, fname)
                doc.save(path)
                self.log.append(f"已生成：{path}")
                QMessageBox.information(self, "导出成功", f"已生成合并文档：\n{path}")
            else:
                from docx.shared import Pt
                for name, lines in selected_builtin:
                    doc = Document()
                    style = doc.styles["Normal"]
                    style.font.name = "Microsoft YaHei"
                    style.font.size = Pt(11)
                    doc.add_heading(name, level=1)
                    for ln in lines[1:]:
                        p = doc.add_paragraph(ln)
                        p.paragraph_format.space_after = Pt(4)
                    path = os.path.join(out_dir, f"{name}.docx")
                    doc.save(path)
                    self.log.append(f"已生成：{path}")
                QMessageBox.information(self, "导出成功", f"已在文件夹中生成 {len(selected_builtin)} 个文档")

            # 用户模板副本
            import shutil
            for it in getattr(self, "user_items", []):
                src = it["path"]
                if os.path.exists(src):
                    dst = os.path.join(out_dir, os.path.basename(src))
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        self.log.append(f"已复制我的模板：{dst}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


# ============================================================
#  开发者选项
# ============================================================
class DeveloperPage(QWidget):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        scroll.viewport().setAutoFillBackground(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        inner.setAutoFillBackground(False)
        inner.setStyleSheet("background: transparent;")
        scroll.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(12)

        title = QLabel("开发者选项")
        title.setObjectName("Title")
        lay.addWidget(title)

        # 常规
        card1 = make_card()
        v1 = QVBoxLayout(card1)
        v1.setContentsMargins(16, 14, 16, 14)
        v1.setSpacing(8)
        t1 = QLabel("运行与日志")
        t1.setObjectName("SectionTitle")
        v1.addWidget(t1)
        row = QHBoxLayout()
        row.addWidget(QLabel("日志级别"))
        self.cb_level = QComboBox()
        self.cb_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.cb_level.setCurrentText(self.db.get_setting("log_level", "INFO"))
        row.addWidget(self.cb_level)
        b_apply = QPushButton("应用")
        b_apply.clicked.connect(self.apply_log)
        row.addWidget(b_apply)
        row.addStretch()
        v1.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("数据目录"))
        lbl_dir = QLabel(data_dir())
        lbl_dir.setStyleSheet("color:#8D919B;font-size:12px;")
        row2.addWidget(lbl_dir)
        b_open = QPushButton("打开")
        b_open.clicked.connect(lambda: common.open_path(data_dir()))
        row2.addWidget(b_open)
        row2.addStretch()
        v1.addLayout(row2)
        row3 = QHBoxLayout()
        b_log = QPushButton("打开日志文件")
        b_log.clicked.connect(self.open_log)
        b_exp = QPushButton("导出数据目录说明")
        b_exp.clicked.connect(self.export_readme)
        row3.addWidget(b_log)
        row3.addWidget(b_exp)
        row3.addStretch()
        v1.addLayout(row3)
        lay.addWidget(card1)

        # API
        card2 = make_card()
        v2 = QVBoxLayout(card2)
        v2.setContentsMargins(16, 14, 16, 14)
        v2.setSpacing(8)
        t2 = QLabel("备份与云同步")
        t2.setObjectName("SectionTitle")
        v2.addWidget(t2)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("自动备份目录"))
        self.ed_backup = QLineEdit()
        self.ed_backup.setText(self.db.get_setting("backup_dir", "") or common.default_backup_dir())
        row2.addWidget(self.ed_backup, 1)
        b_choose = QPushButton("选择…")
        b_choose.clicked.connect(self.choose_backup_dir)
        row2.addWidget(b_choose)
        b_now = QPushButton("立即备份")
        b_now.clicked.connect(self._backup_now)
        row2.addWidget(b_now)
        v2.addLayout(row2)
        note = QLabel("每 24 小时自动把软件全部数据打包到这里，只保留最新 3 份。"
                      "该文件夹独立于软件安装目录，卸载软件不会删除，需你手动清理。")
        note.setObjectName("SubTitle")
        note.setWordWrap(True)
        v2.addWidget(note)
        lay.addWidget(card2)

        # 关于
        card4 = make_card()
        v4 = QVBoxLayout(card4)
        v4.setContentsMargins(16, 14, 16, 14)
        v4.setSpacing(6)
        t4 = QLabel("关于")
        t4.setObjectName("SectionTitle")
        v4.addWidget(t4)
        for line in [
            f"{common.APP_NAME}  v{common.APP_VERSION}",
            "面向婚礼主持人的一站式工作台：档期管理、图文设计、预演沙盘、备忘提醒、主持助理、备婚工具。",
            "数据默认保存在本机用户目录；支持整体导出/导入（无密码），每 24 小时自动备份并保留 3 份。",
            "界面语言：简体中文 · 仅支持 Windows",
        ]:
            lb = QLabel(line)
            lb.setWordWrap(True)
            lb.setStyleSheet("color:#9DA1AB;font-size:12px;")
            v4.addWidget(lb)
        lay.addWidget(card4)
        lay.addStretch()

    def apply_log(self):
        level = self.cb_level.currentText()
        self.db.set_setting("log_level", level)
        common.setup_logging(level)
        QMessageBox.information(self, "已应用", f"日志级别已设为 {level}")

    def open_log(self):
        p = os.path.join(data_dir(), "logs", "app.log")
        if os.path.exists(p):
            common.open_path(p)
        else:
            QMessageBox.information(self, "提示", "暂无日志文件")

    def export_readme(self):
        p = os.path.join(data_dir(), "数据目录说明.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("主持人工作台数据目录说明\n\n")
            f.write("host.db        档期与提醒数据库（SQLite）\n")
            f.write("backups/       加密备份文件\n")
            f.write("logs/          运行日志\n")
            f.write("templates/     导入的 Word 模板\n")
            f.write("主持词/        保存的主持词文本\n")
            f.write("ai_style/      主持助理的写词参考文档\n")
            f.write("sandbox_layout.json 预演沙盘自动保存的方案\n")
            f.write("图文设计_*.png   导出的图片\n")
        QMessageBox.information(self, "已生成", p)

    def _backup_now(self):
        try:
            p = common.auto_backup_if_due(force=True)
            if p:
                QMessageBox.information(self, "备份完成", p)
            else:
                QMessageBox.warning(self, "备份失败", "请检查备份目录是否可写。")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def choose_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择备份目录", self.ed_backup.text() or data_dir())
        if d:
            self.ed_backup.setText(d)
            self.db.set_setting("backup_dir", d)


