# -*- coding: utf-8 -*-
"""备婚工具：人员 / 物品 / 流程 三张清单
   · 导入文档/表格（docx / xlsx / csv / txt / md）并自动解析成清单
   · 另存为 Word（自动排版 + 美学配色）
   · 多选 / 编辑 / 删除 / 上移下移 / 新增
   · 流程清单支持 地点、指定音乐，并可一键生成音乐库播放列表
"""
import os
import re
import json
import logging
import datetime

from PySide6.QtCore import Qt, QDate, QTimer, QEvent, QObject, QUrl
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog,
    QMessageBox, QDialog, QDialogButtonBox, QLineEdit, QListWidget, QListWidgetItem,
    QCheckBox, QComboBox, QGridLayout, QDateEdit, QSlider, QMenu, QApplication
)

import common
import docio
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import theme
from common import data_dir, get_setting

logger = logging.getLogger(__name__)

QTY_RE = re.compile(
    r"(.*?)[\s:：\-—]*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(份|个|张|瓶|盒|包|束|对|套|台|条|件|杯|支|只|斤|箱|袋|本|把|块|辆|顶|面|副|枚)?"
    r"\s*(.*)")
PHONE_RE = re.compile(r"1[3-9][0-9]{9}")
TIME_RE = re.compile(r"^(\d{1,2}[:：]\d{2})\s*[-—·、]?\s*(.*)$")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".ape")

MUSIC_WORDS = ("音乐", "曲", "bgm", "BGM", "配乐")

ACCENTS = {
    "people": ("4E6B57", "EAF0E9"),   # 人员：墨绿
    "items": ("A8863F", "F7F2E6"),    # 物品：香槟金
    "flow": ("8C4A4A", "F7EDED"),     # 流程：酒红
}


def make_card(parent=None, alt=False):
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


# ============================================================
#  Word 解析
# ============================================================
def read_docx(path):
    """返回 (段落文本列表, 表格行列表)；表格行是单元格文本列表"""
    from docx import Document
    doc = Document(path)
    paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    rows = []
    for tb in getattr(doc, "tables", []):
        for row in tb.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(cells)
    return paras, rows


def read_txt(path):
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        return [ln for ln in f.read().splitlines() if ln.strip()], []


def read_xlsx(path):
    """读取 Excel 第一张表（.xlsx），返回行列表"""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = ["" if v is None else str(v).strip() for v in row]
        if any(cells):
            rows.append(cells)
    wb.close()
    return [], rows


def read_csv_file(path):
    import csv
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return [], [row for row in csv.reader(f) if any(c.strip() for c in row)]
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        return [], [row for row in csv.reader(f) if any(c.strip() for c in row)]


HEADER_ALIASES = {
    "people": {"project": ("项目", "事项"),
               "headcount": ("人数", "数量"),
               "event": ("负责事件", "事件", "分工"),
               "detail": ("说明", "备注"),
               "person": ("负责人", "姓名", "名字", "人员"),
               "phone": ("手机号码", "手机号", "电话", "手机", "联系方式")},
    "items": {"name": ("物品", "名称", "物品名称", "项目"),
              "qty": ("数量",),
              "note": ("备注", "说明")},
    "flow": {"time": ("时间",),
             "title": ("环节", "流程", "项目"),
             "content": ("内容", "环节内容", "流程内容"),
             "location": ("地点", "场地", "位置"),
             "music": ("音乐", "指定音乐", "曲目"),
             "note": ("备注", "说明")},
}


def parse_table_rows(kind, rows):
    """有表头的表格：按表头映射列，返回 dict 列表；没表头返回 None"""
    aliases = HEADER_ALIASES.get(kind)
    if not aliases or not rows:
        return None
    header_idx, mapping = None, {}
    for idx, row in enumerate(rows[:6]):
        cells = [str(c).strip() for c in row]
        mapping = {}
        for key, names in aliases.items():
            for i, c in enumerate(cells):
                if any(n in c for n in names):
                    mapping[key] = i
                    break
        if len(mapping) >= 2:
            header_idx = idx
            break
    if header_idx is None:
        return None
    out = []
    for row in rows[header_idx + 1:]:
        cells = [str(c).strip() for c in row]
        if not any(cells):
            continue
        rec = {k: (cells[i] if i < len(cells) else "") for k, i in mapping.items()}
        if kind == "people":
            if not rec.get("person") and not rec.get("phone"):
                continue
            out.append({"project": rec.get("project", "")[:40],
                        "headcount": rec.get("headcount", "")[:10],
                        "event": rec.get("event", "")[:40],
                        "detail": rec.get("detail", "")[:80],
                        "person": rec.get("person", "")[:30],
                        "phone": rec.get("phone", "")})
        elif kind == "items":
            if not rec.get("name"):
                continue
            out.append({"name": rec.get("name", "")[:40],
                        "qty": rec.get("qty", "")[:20],
                        "note": rec.get("note", "")[:80]})
        else:
            if not rec.get("title"):
                continue
            out.append({"time": rec.get("time", "")[:10],
                        "title": rec.get("title", "")[:40],
                        "content": rec.get("content", "")[:200],
                        "location": rec.get("location", "")[:40],
                        "music": rec.get("music", "")[:200],
                        "note": rec.get("note", "")[:100]})
    return out


def _clean_line(s):
    return s.strip().strip("·•-—*").strip()


def _looks_location(s):
    return any(k in s for k in ("厅", "舞台", "区", "门", "台", "场", "廊", "通道", "入口"))


def _looks_music(s):
    low = s.lower()
    return low.endswith(AUDIO_EXT) or any(k in s for k in MUSIC_WORDS)


ROLE_WORDS = ("主持人", "主持", "司仪", "督导", "音控", "灯光", "摄影", "摄像", "化妆",
              "化妆师", "伴郎", "伴娘", "新人", "新郎", "新娘", "爸爸", "妈妈", "长辈",
              "证婚人", "策划", "总导演", "统筹", "场控", "花艺")
HEADER_WORDS = {"时间", "环节", "地点", "音乐", "指定音乐", "备注", "序号", "人员",
                "姓名", "电话", "角色", "分工", "物品", "数量", "已备", "名称", "流程",
                "内容", "项目", "清单"}


def _split_name_role(text, extra=""):
    """把“主持人：张伟 全场串场”拆成 (姓名, 角色/分工)"""
    text = text.replace("：", ":").strip()
    role = extra.strip()
    if ":" in text:
        left, right = text.split(":", 1)
        if left.strip() and right.strip():
            role = (left.strip() + " " + role).strip()
            text = right.strip()
    parts = [p for p in re.split(r"[|｜/、,，\s]{1,}", text) if p]
    if not parts:
        return "", role
    name = parts[0]
    rest = parts[1:]
    if (name in ROLE_WORDS or (len(name) <= 3 and rest and rest[0] not in ROLE_WORDS
                               and any(w in name for w in ROLE_WORDS))):
        role = (name + " " + role).strip()
        name = rest[0]
        rest = rest[1:]
    if rest:
        role = (role + " " + " ".join(rest)).strip()
    return name.strip(), role.strip()


def parse_people(paras, rows):
    out = []
    seen = set()
    for cells in rows:
        raw = [c.strip() for c in cells]
        if not any(raw):
            continue
        if raw[0] in HEADER_WORDS and (len(raw) < 2 or raw[1] in HEADER_WORDS):
            continue
        phone = ""
        pidx = -1
        for i, c in enumerate(raw):
            m = PHONE_RE.search(c)
            if m:
                phone = m.group(0)
                pidx = i
                break
        if not phone:
            continue
        name_raw = raw[0] if raw else ""
        role_raw = raw[1] if len(raw) > 1 and 1 != pidx else ""
        note_raw = raw[2] if len(raw) > 2 and 2 != pidx else ""
        name, role = _split_name_role(name_raw, role_raw)
        if not name:
            continue
        key = (name, phone)
        if key in seen:
            continue
        seen.add(key)
        out.append({"project": "", "headcount": "", "event": role[:40],
                    "detail": note_raw[:80], "person": name[:30], "phone": phone})
    for raw in paras:
        line = _clean_line(raw)
        if not line or len(line) > 100:
            continue
        m = PHONE_RE.search(line)
        if not m:
            continue
        rest = PHONE_RE.sub("", line).strip(" ：:|-—,，、")
        rest = re.sub(r"[（(].*?[)）]", "", rest).strip()
        name, role = _split_name_role(rest)
        if not name:
            name = "未命名"
        key = (name, m.group(0))
        if key in seen:
            continue
        seen.add(key)
        out.append({"project": "", "headcount": "", "event": role[:40],
                    "detail": "", "person": name[:30], "phone": m.group(0)})
    return out


def parse_items(paras, rows):
    out = []
    seen = set()
    for cells in rows:
        raw = [c.strip() for c in cells]
        if not any(raw):
            continue
        if raw[0] in HEADER_WORDS:
            continue
        if len(raw) < 2 or not re.search(r"\d", raw[1]):
            continue
        name = raw[0]
        qty = raw[1]
        note = raw[2] if len(raw) > 2 else ""
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name[:40], "qty": qty[:20], "note": note[:80]})
    for raw in paras:
        line = _clean_line(raw)
        if not line or len(line) > 90:
            continue
        if PHONE_RE.search(line):
            continue
        m = QTY_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip(" ：:|-—,，、")
        qty = m.group(2) + (m.group(3) or "")
        note = (m.group(4) or "").strip(" ：:|-—,，、")
        if not name or len(name) > 32 or name in seen:
            continue
        if not re.search(r"[\u4e00-\u9fa5A-Za-z]", name):
            continue
        seen.add(name)
        out.append({"name": name[:40], "qty": qty[:20], "note": note[:80]})
    return out


def parse_flow(paras, rows):
    out = []
    for cells in rows:
        raw = [c.strip() for c in cells]
        if not any(raw):
            continue
        if raw[0] in HEADER_WORDS:
            continue
        time = ""
        m = TIME_RE.match(raw[0])
        if m:
            time = m.group(1).replace("：", ":")
            title = m.group(2) or (raw[1] if len(raw) > 1 else "")
            location = raw[2] if len(raw) > 2 else ""
            music = raw[3] if len(raw) > 3 else ""
            note = raw[4] if len(raw) > 4 else ""
        else:
            title = raw[0]
            location = raw[1] if len(raw) > 1 else ""
            music = raw[2] if len(raw) > 2 else ""
            note = raw[3] if len(raw) > 3 else ""
        if not title:
            continue
        out.append({"time": time, "title": title[:40], "content": "",
                    "location": location[:40], "music": music[:200], "note": note[:100]})
    for raw in paras:
        line = _clean_line(raw)
        if not line or len(line) > 120:
            continue
        time = ""
        m = TIME_RE.match(line)
        rest = line
        if m:
            time = m.group(1).replace("：", ":")
            rest = m.group(2)
        if not rest:
            continue
        parts = [p.strip() for p in re.split(r"[|｜\t]+", rest) if p.strip()]
        if len(parts) == 1:
            parts = [p.strip() for p in re.split(r"\s{2,}", rest) if p.strip()]
        title = parts[0] if parts else rest
        location, music, note = "", "", ""
        for p in parts[1:]:
            if not music and _looks_music(p):
                music = p
            elif not location and (_looks_location(p) or len(parts) >= 3):
                location = p
            else:
                note = (note + " " + p).strip()
        if not time and not location and not music and len(line) < 6:
            continue
        # 文档标题、小标题不是流程条目
        if not time and "|" not in line and "｜" not in line and "  " not in line \
                and len(line) <= 22:
            continue
        out.append({"time": time, "title": title[:40], "content": "",
                    "location": location[:40], "music": music[:200], "note": note[:100]})
    return out


PARSERS = {"people": parse_people, "items": parse_items, "flow": parse_flow}


# ============================================================
#  Word 导出（自动排版 + 配色）
# ============================================================
def _rgb(hexs):
    from docx.shared import RGBColor
    h = hexs.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _font(run, name="微软雅黑", size=None, bold=False, color=None):
    from docx.shared import Pt
    from docx.oxml.ns import qn
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    if size:
        run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = _rgb(color)


def _shade(cell, hexs):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexs)
    tcPr.append(shd)


def _table_borders(table, color="D8D2C4", sz=4):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblPr.append(borders)
    mar = OxmlElement("w:tblCellMar")
    for edge, w in (("top", 70), ("bottom", 70), ("left", 120), ("right", 120)):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:w"), str(w))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


def _para_rule(doc, color, sz=8):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import Pt
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(10)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    pPr.append(pbdr)
    return p


def export_word(path, kind, headers, keys, rows):
    """把清单导出成排版讲究的 Word"""
    from docx import Document
    from docx.shared import Cm, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    accent, tint = ACCENTS[kind]
    titles = {"people": ("PEOPLE LIST", "婚礼人员清单"),
              "items": ("WEDDING ITEMS", "婚礼物品清单"),
              "flow": ("RUNNING ORDER", "婚礼流程安排")}
    en, cn = titles[kind]

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(1.8)
    sec.left_margin = Cm(2.0)
    sec.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "微软雅黑"
    normal.font.size = Pt(10.5)
    try:
        normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")
    except Exception:
        pass

    # 顶部小标
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(en)
    _font(r, "微软雅黑", 9, True, accent)
    # 标题
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    _font(p.add_run(cn), "微软雅黑", 24, True, "2B2B2B")
    # 副标
    now = datetime.date.today().strftime("%Y 年 %m 月 %d 日")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    _font(p.add_run(f"{now}  ·  共 {len(rows)} 项  ·  主持人工作台"), "微软雅黑", 9.5, False, "8A8272")
    _para_rule(doc, accent, 10)

    # 表格
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _table_borders(table)

    widths = {"people": [2.4, 1.4, 3.4, 4.4, 2.8, 2.4], "items": [6.4, 2.8, 1.8, 5.6],
              "flow": [1.6, 2.8, 3.6, 2.6, 3.2, 3.0]}.get(kind)
    if not widths or len(widths) != len(headers):
        widths = [16.8 / len(headers)] * len(headers)

    hdr = table.rows[0]
    trPr = hdr._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    trPr.append(th)
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.width = Cm(widths[i])
        _shade(cell, accent)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.space_before = Pt(3)
        para.paragraph_format.space_after = Pt(3)
        _font(para.add_run(h), "微软雅黑", 10.5, True, "FFFFFF")

    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for i, key in enumerate(keys):
            cell = cells[i]
            cell.width = Cm(widths[i])
            if ridx % 2 == 1:
                _shade(cell, tint)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            val = row.get(key, "")
            if key == "done":
                val = "✓" if val else ""
            if key == "music" and val:
                val = os.path.basename(val)
            para = cell.paragraphs[0]
            para.paragraph_format.space_before = Pt(2)
            para.paragraph_format.space_after = Pt(2)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER if key in ("time", "qty", "done") \
                else WD_ALIGN_PARAGRAPH.LEFT
            _font(para.add_run(str(val or "")), "微软雅黑", 10, False, "333333")

    if not rows:
        p = doc.add_paragraph()
        _font(p.add_run("（清单为空）"), "微软雅黑", 10.5, False, "999999")

    # 页脚
    footer = sec.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(fp.add_run("主持人工作台 · 备婚工具   |   第 "), "微软雅黑", 8, False, "9A9384")
    run = fp.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)
    _font(fp.add_run(" 页"), "微软雅黑", 8, False, "9A9384")

    doc.save(path)


# ============================================================
#  导入分析对话框
# ============================================================
class AnalyzeDialog(QDialog):
    def __init__(self, kind, headers, keys, rows, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.keys = keys
        self.headers = headers
        self.setWindowTitle("Word 分析结果 · 勾选后加入清单")
        self.setMinimumSize(860, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        tip = QLabel(f"从文档中识别到 {len(rows)} 条，取消勾选可跳过；表格里可直接改内容。")
        tip.setObjectName("SubTitle")
        lay.addWidget(tip)

        self.tbl = QTableWidget(0, len(headers) + 1)
        self.tbl.setHorizontalHeaderLabels(["加入"] + headers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, len(headers) + 1):
            hh.setSectionResizeMode(i, QHeaderView.Stretch)
        self.tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked)
            self.tbl.setItem(i, 0, chk)
            for j, key in enumerate(keys):
                val = row.get(key, "")
                if key == "done":
                    val = "是" if val else ""
                it = QTableWidgetItem(str(val or ""))
                self.tbl.setItem(i, j + 1, it)
        lay.addWidget(self.tbl, 1)

        bar = QHBoxLayout()
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: self._set_all(False))
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addStretch()
        lay.addLayout(bar)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("加入清单")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _set_all(self, on):
        for i in range(self.tbl.rowCount()):
            self.tbl.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def selected(self):
        out = []
        for i in range(self.tbl.rowCount()):
            if self.tbl.item(i, 0).checkState() != Qt.Checked:
                continue
            row = {}
            for j, key in enumerate(self.keys):
                it = self.tbl.item(i, j + 1)
                row[key] = it.text().strip() if it else ""
            if any(row.values()):
                out.append(row)
        return out


# ============================================================
#  选音乐对话框
# ============================================================
class ClickSlider(QSlider):
    """点击任意位置直接跳转，仍可拖动"""
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.orientation() == Qt.Horizontal:
            val = int(self.minimum() + (self.maximum() - self.minimum()) * ev.position().x() / max(1, self.width()))
            self.setValue(val)
            self.sliderMoved.emit(val)
            self.sliderReleased.emit()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton and self.orientation() == Qt.Horizontal:
            val = int(self.minimum() + (self.maximum() - self.minimum()) * ev.position().x() / max(1, self.width()))
            self.setValue(val)
            self.sliderMoved.emit(val)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self.sliderReleased.emit()


class MusicDialog(QDialog):
    def __init__(self, current="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("指定环节音乐")
        self.setMinimumSize(680, 540)
        self._dragging = False
        lay = QVBoxLayout(self)
        tip = QLabel("搜索音乐库，单击试听，双击选中；也可以直接输入曲名。")
        tip.setObjectName("SubTitle")
        lay.addWidget(tip)
        row = QHBoxLayout()
        self.ed = QLineEdit(current or "")
        row.addWidget(self.ed, 1)
        b_file = QPushButton("浏览文件…")
        b_file.clicked.connect(self._browse)
        row.addWidget(b_file)
        lay.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索曲名 / 文件夹…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._pick)
        self.list.currentItemChanged.connect(self._load_preview)
        lay.addWidget(self.list, 1)
        for path in self._collect():
            it = QListWidgetItem(os.path.basename(path))
            it.setToolTip(path)
            it.setData(Qt.UserRole, path)
            self.list.addItem(it)
        pv = QHBoxLayout()
        self.b_play = QPushButton("▶ 试听")
        self.b_play.setFixedWidth(86)
        self.b_play.clicked.connect(self._toggle_play)
        pv.addWidget(self.b_play)
        self.slider = ClickSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._slider_down)
        self.slider.sliderReleased.connect(self._slider_up)
        self.slider.sliderMoved.connect(self._slider_move)
        pv.addWidget(self.slider, 1)
        self.lb_time = QLabel("00:00 / 00:00")
        self.lb_time.setObjectName("SubTitle")
        pv.addWidget(self.lb_time)
        lay.addLayout(pv)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.playbackStateChanged.connect(self._on_state)
        bar = QHBoxLayout()
        b_clear = QPushButton("清空")
        b_clear.clicked.connect(lambda: self.ed.setText(""))
        bar.addWidget(b_clear)
        bar.addStretch()
        lay.addLayout(bar)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, text):
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            hay = ((it.text() or "") + " " + (it.toolTip() or "")).lower()
            it.setHidden(bool(text) and text not in hay)

    def _load_preview(self, cur, prev=None):
        if not cur:
            return
        path = cur.data(Qt.UserRole) or ""
        if not path or not os.path.exists(path):
            return
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.pause()
        self.slider.setValue(0)
        self.lb_time.setText("00:00 / 00:00")

    def _toggle_play(self):
        if self.player.source().isEmpty():
            cur = self.list.currentItem()
            if cur is None:
                return
            self._load_preview(cur)
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state(self, st):
        self.b_play.setText("⏸ 暂停" if st == QMediaPlayer.PlayingState else "▶ 试听")

    def _fmt(self, ms):
        s = max(0, int(ms // 1000))
        return "%02d:%02d" % (s // 60, s % 60)

    def _on_dur(self, dur):
        self.lb_time.setText(f"{self._fmt(self.player.position())} / {self._fmt(dur)}")

    def _on_pos(self, pos):
        if not self._dragging and self.player.duration() > 0:
            self.slider.setValue(int(pos * 1000 / self.player.duration()))
        self.lb_time.setText(f"{self._fmt(pos)} / {self._fmt(self.player.duration())}")

    def _slider_down(self):
        self._dragging = True

    def _slider_move(self, val):
        dur = self.player.duration()
        self.lb_time.setText(f"{self._fmt(dur * val / 1000)} / {self._fmt(dur)}")

    def _slider_up(self):
        self._dragging = False
        dur = self.player.duration()
        if dur > 0:
            self.player.setPosition(int(dur * self.slider.value() / 1000))

    def _collect(self):
        out, seen = [], set()
        root = get_setting("music_dir", "") or os.path.join(data_dir(), "music")
        try:
            win = self.parent().window() if self.parent() else None
            music = getattr(win, "music", None)
            lib = getattr(music, "lib", None) if music else None
            if lib:
                for lst in lib.lists:
                    for p in lst.get("items", []):
                        if p not in seen:
                            seen.add(p)
                            out.append(p)
        except Exception:
            pass
        if os.path.isdir(root):
            n = 0
            for base, _, fns in os.walk(root):
                for fn in sorted(fns):
                    if fn.lower().endswith(AUDIO_EXT):
                        p = os.path.join(base, fn)
                        if p not in seen:
                            seen.add(p)
                            out.append(p)
                            n += 1
                            if n > 600:
                                return out
        return out

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择音频", "", "音频文件 (*.mp3 *.wav *.m4a *.flac *.ogg *.aac)")
        if f:
            self.ed.setText(f)

    def _pick(self, item):
        self.ed.setText(item.data(Qt.UserRole) or item.text())

    def value(self):
        return self.ed.text().strip()

    def closeEvent(self, ev):
        self.player.stop()
        super().closeEvent(ev)

    def done(self, r):
        self.player.stop()
        super().done(r)

class RowDialog(QDialog):
    def __init__(self, kind, headers, keys, row, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.keys = keys
        self.row = dict(row)
        self.setWindowTitle("编辑清单项")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        for i, (h, key) in enumerate(zip(headers, keys)):
            form.addWidget(QLabel(h), i, 0)
            if key == "done":
                w = QCheckBox("已备好")
                w.setChecked(bool(row.get("done")))
            elif key == "music":
                w = QLineEdit(row.get("music") or "")
                w.setPlaceholderText("点击右侧按钮选择，或直接输入曲名")
            else:
                w = QLineEdit(str(row.get(key) or ""))
            setattr(self, "w_" + key, w)
            form.addWidget(w, i, 1)
            if key == "music":
                b = QPushButton("选择…")
                b.clicked.connect(self._pick_music)
                form.addWidget(b, i, 2)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("保存")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick_music(self):
        dlg = MusicDialog(self.w_music.text(), self)
        if dlg.exec() == QDialog.Accepted:
            self.w_music.setText(dlg.value())

    def value(self):
        out = {}
        for key in self.keys:
            w = getattr(self, "w_" + key, None)
            if w is None:
                continue
            if key == "done":
                out[key] = 1 if w.isChecked() else 0
            else:
                out[key] = w.text().strip()
        return out


# ============================================================
#  清单面板
# ============================================================
class RowResizeFilter(QObject):
    """没有行号栏时，用鼠标拖行底边来调行高"""
    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.row = -1
        self.start_y = 0
        self.start_h = 0
        self.active = False
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)

    def _near_bottom(self, y):
        row = self.table.rowAt(y)
        if row < 0:
            return row, False
        rect = self.table.visualRect(self.table.model().index(row, 0))
        return row, abs(y - rect.bottom()) <= 4

    def eventFilter(self, obj, ev):
        try:
            if obj is not self.table.viewport():
                return False
        except RuntimeError:
            return False
        if ev.type() == QEvent.MouseMove:
            y = ev.position().y()
            row, near = self._near_bottom(y)
            self.table.viewport().setCursor(Qt.SizeVerCursor if near or self.active else Qt.ArrowCursor)
            if self.active and self.row >= 0:
                dy = y - self.start_y
                self.table.setRowHeight(self.row, max(30, self.start_h + int(dy)))
                if getattr(self.table, "on_row_resize", None):
                    self.table.on_row_resize(self.row)
                return True
        elif ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            y = ev.position().y()
            row, near = self._near_bottom(y)
            if near:
                self.active = True
                self.row = row
                self.start_y = y
                self.start_h = self.table.rowHeight(row)
                return True
        elif ev.type() == QEvent.MouseButtonRelease:
            if self.active:
                self.active = False
                self.row = -1
                return True
        return False


class FitTable(QTableWidget):
    """列宽可拖动，同时自动铺满整个表格宽度"""
    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self.on_resize = None
        self.on_row_resize = None

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.on_resize:
            self.on_resize()


class ListPane(QWidget):
    def __init__(self, page, kind, parent=None):
        super().__init__(parent)
        self.page = page
        self.db = page.db
        self.kind = kind
        self._loading = False
        self.rows = []
        self.define()
        self._build()
        self.refresh()

    def define(self):
        if self.kind == "people":
            self.headers = ["项目", "人数", "负责事件", "说明", "负责人", "手机号码"]
            self.keys = ["project", "headcount", "event", "detail", "person", "phone"]
            self.widths = [None, 70, 170, None, 110, 130]
            self.plural = "位"
        elif self.kind == "items":
            self.headers = ["物品", "数量", "已备", "备注"]
            self.keys = ["name", "qty", "done", "note"]
            self.widths = [None, 130, 70, 220]
            self.plural = "件"
        else:
            self.headers = ["时间", "环节", "内容", "地点", "指定音乐", "备注"]
            self.keys = ["time", "title", "content", "location", "music", "note"]
            self.widths = [90, 150, None, 150, 190, None]
            self.plural = "个环节"

    # ---------- UI ----------
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        b_imp = QPushButton("导入文档/表格")
        b_imp.setObjectName("Primary")
        b_imp.setToolTip("支持 doc/docx/pdf/rtf/odt/txt/md/html/pptx/xlsx/xls/csv 等")
        b_imp.clicked.connect(self.import_docs)
        b_exp = QPushButton("另存为 Word")
        b_exp.setToolTip("按美学配色自动排版后导出 .docx")
        b_exp.clicked.connect(self.export_word)
        b_add = QPushButton("＋ 新增")
        b_add.clicked.connect(self.add_row)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(self.edit_row)
        b_del = QPushButton("删除")
        b_del.setObjectName("Danger")
        b_del.clicked.connect(self.delete_rows)
        b_up = QPushButton("↑ 上移")
        b_up.clicked.connect(lambda: self.move_rows(-1))
        b_dn = QPushButton("↓ 下移")
        b_dn.clicked.connect(lambda: self.move_rows(1))
        b_sel = QPushButton("全选")
        b_sel.clicked.connect(self.select_all)
        for b in (b_imp, b_exp, b_add, b_edit, b_del, b_up, b_dn, b_sel):
            bar.addWidget(b)
        self.chk_center = QCheckBox("居中显示")
        self.chk_center.toggled.connect(self.apply_center)
        bar.addWidget(self.chk_center)
        bar.addStretch()
        if self.kind == "flow":
            b_pl = QPushButton("↻ 生成播放列表")
            b_pl.setToolTip("把流程里指定的音乐按顺序同步到音乐库「流程配乐」列表")
            b_pl.clicked.connect(self.build_playlist)
            bar.addWidget(b_pl)
        v.addLayout(bar)

        self.table = FitTable(0, len(self.headers))
        self.table.on_resize = None
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.SelectedClicked)
        self.table.setWordWrap(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._layout = self._load_layout()
        self._restoring = False
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        for i in range(len(self.headers)):
            hh.setSectionResizeMode(i, QHeaderView.Interactive)
            self.table.setColumnWidth(i, self.widths[i] or 120)
        vh = self.table.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.Interactive)
        vh.setDefaultSectionSize(38)
        self._row_filter = RowResizeFilter(self.table)
        hh.sectionResized.connect(self._on_col_resized)
        self._widths_fitted = False
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        _t = theme.THEMES[theme.current_theme()]
        self.table.setStyleSheet(
            "QTableWidget QLineEdit{background:%s;color:%s;border:2px solid %s;"
            "border-radius:6px;padding:4px 8px;min-height:22px;"
            "selection-background-color:%s;selection-color:#14161B;}"
            % (_t["card"], _t["text"], _t["accent"], _t["accent"]))
        self.table.itemChanged.connect(self.on_changed)
        self.table.itemSelectionChanged.connect(self.update_tip)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        v.addWidget(self.table, 1)

        self.lb_tip = QLabel("")
        self.lb_tip.setObjectName("SubTitle")
        v.addWidget(self.lb_tip)

    # ---------- 数据 ----------
    def fetch(self):
        if self.kind == "people":
            return self.db.prep_people()
        if self.kind == "items":
            return self.db.prep_items()
        return self.db.prep_flow()

    def refresh(self):
        self.rows = self.fetch()
        self._loading = True
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            for j, key in enumerate(self.keys):
                if key == "done":
                    it = QTableWidgetItem()
                    it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setCheckState(Qt.Checked if r.get("done") else Qt.Unchecked)
                    it.setTextAlignment(Qt.AlignCenter)
                elif key == "music":
                    val = r.get("music") or ""
                    it = QTableWidgetItem(os.path.basename(val) if val else "")
                    it.setToolTip(val)
                    if val:
                        it.setForeground(QColor("#C9A86A"))
                else:
                    it = QTableWidgetItem(str(r.get(key) or ""))
                    if key == "time":
                        it.setTextAlignment(Qt.AlignCenter)
                it.setData(Qt.UserRole, r.get("id"))
                self.table.setItem(i, j, it)
            self.table.setRowHeight(i, 38)
        self._loading = False
        saved = self._layout.get("widths") or []
        if len(saved) == len(self.headers):
            self._restoring = True
            for j, w in enumerate(saved):
                self.table.setColumnWidth(j, max(50, int(w)))
            self._restoring = False
            self._widths_fitted = True
        elif not self._widths_fitted:
            try:
                self.table.resizeColumnsToContents()
                for j in range(len(self.headers)):
                    self.table.setColumnWidth(j, max(80, min(420, self.table.columnWidth(j))))
            except Exception:
                pass
            self._widths_fitted = True
            QTimer.singleShot(0, self._fill_columns)
        for i in range(self.table.rowCount()):
            rid = self.rows[i].get("id")
            h = self._heights.get(str(rid))
            if h:
                self.table.setRowHeight(i, max(30, int(h)))
        self._schedule_fit()
        if hasattr(self, "chk_center") and self.chk_center.isChecked():
            self.apply_center(True)
        self.update_tip()

    def _load_layout(self):
        try:
            raw = self.db.get_setting("prep_layout_" + self.kind, "")
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        self._heights = dict(data.get("heights") or {})
        return {"widths": data.get("widths") or [], "heights": self._heights}

    def _persist_layout(self):
        try:
            widths = [self.table.columnWidth(i) for i in range(len(self.headers))]
            self.db.set_setting("prep_layout_" + self.kind,
                                json.dumps({"widths": widths, "heights": self._heights},
                                           ensure_ascii=False))
        except Exception:
            pass

    def _on_row_resized(self, row):
        if 0 <= row < len(self.rows):
            rid = self.rows[row].get("id")
            self._heights[str(rid)] = self.table.rowHeight(row)
            self._persist_layout()

    def _clamp_widths(self):
        try:
            vw = self.table.viewport().width()
            n = len(self.headers)
            total = sum(self.table.columnWidth(i) for i in range(n))
            if vw > 0 and total > vw:
                self._restoring = True
                acc = 0
                for i in range(n):
                    w = self.table.columnWidth(i)
                    nw = max(50, int(vw * w / total))
                    self.table.setColumnWidth(i, nw)
                    acc += nw
                self._restoring = False
                self._persist_layout()
        except Exception:
            pass

    def _on_col_resized(self, idx, old, new):
        if self._restoring:
            return
        try:
            vw = self.table.viewport().width()
            total = sum(self.table.columnWidth(i) for i in range(len(self.headers)))
            if vw > 0 and total > vw:
                others = total - self.table.columnWidth(idx)
                maxw = max(50, vw - others)
                if self.table.columnWidth(idx) > maxw:
                    self._restoring = True
                    self.table.setColumnWidth(idx, maxw)
                    self._restoring = False
        except Exception:
            pass
        self._persist_layout()
        self._schedule_fit()

    def apply_center(self, on):
        for i in range(self.table.rowCount()):
            for j in range(self.table.columnCount()):
                it = self.table.item(i, j)
                if it is not None:
                    it.setTextAlignment(Qt.AlignCenter if on else (Qt.AlignLeft | Qt.AlignVCenter))

    def _schedule_fill(self, *_):
        QTimer.singleShot(30, self._fill_columns)

    def _fill_columns(self):
        try:
            vw = self.table.viewport().width()
            n = len(self.headers)
            if vw <= 0 or n == 0:
                return
            widths = [self.table.columnWidth(i) for i in range(n)]
            total = sum(widths)
            if total <= 0:
                return
            if total < vw - 2:
                extra = vw - total - 2
                for i in range(n):
                    add = int(extra * (widths[i] / total))
                    self.table.setColumnWidth(i, widths[i] + add)
        except Exception:
            pass

    def _schedule_fit(self, *_):
        QTimer.singleShot(60, self._fit_rows)

    def _fit_rows(self):
        try:
            self.table.resizeRowsToContents()
            for i in range(self.table.rowCount()):
                rid = self.rows[i].get("id") if i < len(self.rows) else None
                saved = self._heights.get(str(rid))
                if saved:
                    self.table.setRowHeight(i, max(30, int(saved)))
                elif self.table.rowHeight(i) < 38:
                    self.table.setRowHeight(i, 38)
        except Exception:
            pass

    def update_tip(self, *_):
        n = len(self.rows)
        sel = len(set(idx.row() for idx in self.table.selectedIndexes()))
        extra = f" · 已选 {sel} 行" if sel else ""
        self.lb_tip.setText(f"共 {n} {self.plural}{extra}　｜　双击单元格直接改，双击「音乐」单元格可挑曲目；"
                            f"按住 Ctrl / Shift 可多选后批量删除或移动。")

    def _sel_rows(self):
        return sorted(set(idx.row() for idx in self.table.selectedIndexes()))

    def select_all(self):
        self.table.selectAll()

    # ---------- 编辑同步 ----------
    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return
        self.table.setCurrentItem(item)
        col = item.column()
        key = self.keys[col] if col < len(self.keys) else ""
        menu = QMenu(self)
        if key == "music":
            act_pick = menu.addAction("在音乐库挑选…")
            menu.addSeparator()
        else:
            act_pick = None
        act_copy = menu.addAction("复制")
        act_cut = menu.addAction("剪切")
        act_paste = menu.addAction("粘贴")
        menu.addSeparator()
        act_center = menu.addAction("居中")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if act_pick is not None and chosen == act_pick:
            dlg = MusicDialog(item.text(), self)
            if dlg.exec() == QDialog.Accepted:
                self._set_cell(item.row(), col, dlg.value())
            return
        clip = QApplication.clipboard()
        if chosen == act_copy:
            clip.setText(item.text())
        elif chosen == act_cut:
            clip.setText(item.text())
            self._set_cell(item.row(), col, "")
        elif chosen == act_paste:
            self._set_cell(item.row(), col, clip.text())
        elif chosen == act_center:
            for idx in self.table.selectedIndexes():
                it = self.table.item(idx.row(), idx.column())
                if it is not None:
                    it.setTextAlignment(Qt.AlignCenter)

    def _set_cell(self, row, col, text):
        if row < 0 or row >= len(self.rows) or col >= len(self.keys):
            return
        it = self.table.item(row, col)
        if it is None:
            return
        it.setText(text)
        self._update(self.rows[row]["id"], self.keys[col], text)
        self.rows[row][self.keys[col]] = text

    def on_changed(self, item):
        if self._loading:
            return
        row, col = item.row(), item.column()
        if row < 0 or col < 0 or row >= len(self.rows) or col >= len(self.keys):
            return
        rec = self.rows[row]
        rid = rec.get("id")
        key = self.keys[col]
        if key == "done":
            val = 1 if item.checkState() == Qt.Checked else 0
        elif key == "music":
            val = item.text().strip()
            if not val:
                val = ""
        else:
            val = item.text().strip()
        self._update(rid, key, val)
        rec[key] = val

    def _update(self, rid, key, val):
        if self.kind == "people":
            self.db.prep_update_person(rid, **{key: val})
        elif self.kind == "items":
            self.db.prep_update_item(rid, **{key: val})
        else:
            self.db.prep_update_flow(rid, **{key: val})

    def on_double(self, item):
        if self.keys[item.column()] == "music":
            dlg = MusicDialog(item.toolTip() or item.text(), self)
            if dlg.exec() == QDialog.Accepted:
                val = dlg.value()
                self._update(self.rows[item.row()]["id"], "music", val)
                self.refresh()
                self.table.selectRow(item.row())

    # ---------- 增删改移 ----------
    def add_row(self):
        sel = self._sel_rows()
        at = sel[0] if sel else len(self.rows)
        if self.kind == "people":
            rid = self.db.prep_add_person("新项目", "", "", "", "新成员", "")
        elif self.kind == "items":
            rid = self.db.prep_add_item("婚礼物品", "新物品", "1 份", "")
        else:
            rid = self.db.prep_add_flow("", "新环节", "", "", "", "")
        table = {"people": "prep_people", "items": "prep_items", "flow": "prep_flow"}[self.kind]
        order = [r["id"] for r in self.rows]
        order.insert(min(at, len(order)), rid)
        self.db.prep_set_order(table, order)
        self.refresh()
        row = min(at, self.table.rowCount() - 1)
        self.table.selectRow(row)
        self.table.scrollToItem(self.table.item(row, 0))

    def edit_row(self):
        rows = self._sel_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要编辑的行")
            return
        row = rows[0]
        dlg = RowDialog(self.kind, self.headers, self.keys, self.rows[row], self)
        if dlg.exec() != QDialog.Accepted:
            return
        val = dlg.value()
        rid = self.rows[row]["id"]
        for k, v in val.items():
            self._update(rid, k, v)
        self.refresh()
        self.table.selectRow(row)

    def delete_rows(self):
        rows = self._sel_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行（可 Ctrl / Shift 多选）")
            return
        if QMessageBox.question(self, "删除确认",
                                f"确定删除选中的 {len(rows)} 行？") != QMessageBox.Yes:
            return
        for i in rows:
            rid = self.rows[i]["id"]
            if self.kind == "people":
                self.db.prep_delete_person(rid)
            elif self.kind == "items":
                self.db.prep_delete_item(rid)
            else:
                self.db.prep_delete_flow(rid)
        self.refresh()
        self.page.refresh_summary()

    def move_rows(self, delta):
        rows = self._sel_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要移动的行")
            return
        order = [r["id"] for r in self.rows]
        n = len(order)
        if delta < 0:
            if rows[0] == 0:
                return
            for i in rows:
                order[i - 1], order[i] = order[i], order[i - 1]
        else:
            if rows[-1] >= n - 1:
                return
            for i in reversed(rows):
                order[i], order[i + 1] = order[i + 1], order[i]
        table = {"people": "prep_people", "items": "prep_items", "flow": "prep_flow"}[self.kind]
        self.db.prep_set_order(table, order)
        self.refresh()
        sel = self.table.selectionModel()
        self.table.clearSelection()
        for r in rows:
            nr = r + delta
            if 0 <= nr < self.table.rowCount():
                self.table.selectRow(nr)
        self.table.scrollToItem(self.table.item(min(rows[-1] + delta, self.table.rowCount() - 1), 0))

    # ---------- 导入 / 导出 ----------
    def import_docs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "导入文档 / 表格", "", docio.FILE_FILTER)
        if not files:
            return
        all_rows, failed = [], []
        for f in files:
            try:
                paras, trows = docio.read_document(f)
                table = parse_table_rows(self.kind, trows)
                if table is not None:
                    parsed = table + (PARSERS[self.kind](paras, []) if paras else [])
                else:
                    parsed = PARSERS[self.kind](paras, trows)
                all_rows.extend(parsed)
            except Exception as e:
                logger.warning("解析失败 %s: %s", f, e)
                failed.append(os.path.basename(f))
        if not all_rows:
            msg = "没有从文件里识别到可加入的条目。\n\n"
            msg += ("人员清单需要「姓名 + 手机号」，或表头包含 姓名/电话/角色；\n"
                    if self.kind == "people" else
                    "物品清单需要「名称 + 数量」，或表头包含 物品/数量；\n"
                    if self.kind == "items" else
                    "流程清单建议一行一个环节，或表头包含 时间/环节/地点/音乐；\n")
            msg += "\n支持 doc/docx/pdf/rtf/odt/txt/md/html/pptx/xlsx/xls/csv/epub/wps。"
            if failed:
                msg += "解析失败：" + "、".join(failed)
            QMessageBox.information(self, "没识别到内容", msg)
            return
        # 自动写入下方清单（按关键字段去重）
        seen = set()
        added = 0
        for row in all_rows:
            if self.kind == "people":
                key = (row.get("person") or row.get("name"), row.get("phone"))
                if key in seen:
                    continue
                seen.add(key)
                self.db.prep_add_person(row.get("project", ""), row.get("headcount", ""),
                                        row.get("event", ""), row.get("detail", ""),
                                        row.get("person", "") or row.get("name", ""),
                                        row.get("phone", ""))
            elif self.kind == "items":
                key = row.get("name")
                if key in seen:
                    continue
                seen.add(key)
                self.db.prep_add_item("婚礼物品", row.get("name", ""), row.get("qty", ""),
                                      row.get("note", ""))
            else:
                key = (row.get("time"), row.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                self.db.prep_add_flow(row.get("time", ""), row.get("title", ""),
                                      row.get("content", ""), row.get("location", ""),
                                      row.get("note", ""), row.get("music", ""))
            added += 1
        self.refresh()
        self.page.refresh_summary()
        skip = len(all_rows) - added
        extra = f"，跳过重复 {skip} 条" if skip else ""
        QMessageBox.information(self, "已导入",
                                f"已从 {len(files)} 个文件自动解析并加入 {added} 条{extra}。")

    def export_word(self):
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        names = {"people": "人员清单", "items": "物品清单", "flow": "流程安排"}
        default = os.path.join(data_dir(), f"{names[self.kind]}_{now}.docx")
        path, _ = QFileDialog.getSaveFileName(self, "另存为 Word", default, "Word 文档 (*.docx)")
        if not path:
            return
        if not path.lower().endswith(".docx"):
            path += ".docx"
        try:
            export_word(path, self.kind, self.headers, self.keys, self.rows)
        except Exception as e:
            logger.exception("导出 Word 失败")
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "已导出", f"已保存带排版的 Word：\n{path}")

    def build_playlist(self):
        paths = []
        for r in self.rows:
            m = (r.get("music") or "").strip()
            if m and os.path.exists(m):
                paths.append(m)
        if not paths:
            QMessageBox.information(
                self, "还没有可用的音乐",
                "请先在「指定音乐」列给环节挑好音频文件（双击音乐单元格）。\n"
                "只填曲名的条目无法加入播放列表。")
            return
        win = self.window()
        music = getattr(win, "music", None)
        if music is None or not hasattr(music, "sync_flow_playlist"):
            QMessageBox.warning(self, "不可用", "音乐库页面还没准备好，请稍后再试。")
            return
        n = music.sync_flow_playlist(paths, "流程配乐")
        if QMessageBox.question(
                self, "已生成播放列表",
                f"已把流程里的 {n} 首音乐同步到「流程配乐」列表。\n要现在去音乐库看看吗？") == QMessageBox.Yes:
            try:
                win.go(7)
            except Exception:
                pass


# ============================================================
#  备婚工具页
# ============================================================
class PrepPage(QWidget):
    def __init__(self, db: common.DB, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        tbox = QVBoxLayout()
        tbox.setSpacing(2)
        title = QLabel("备婚工具")
        title.setObjectName("Title")
        sub = QLabel("人员 · 物品 · 流程三张清单：导入文档/表格分析、美学排版导出、多选编辑排序")
        sub.setObjectName("SubTitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox)
        head.addStretch()
        self.lb_sum = QLabel("")
        self.lb_sum.setObjectName("SubTitle")
        head.addWidget(self.lb_sum)
        lay.addLayout(head)

        info = QFrame()
        info.setObjectName("Card")
        ig = QGridLayout(info)
        ig.setContentsMargins(16, 12, 16, 12)
        ig.setHorizontalSpacing(12)
        ig.setVerticalSpacing(8)
        self.ed_wed_date = QDateEdit(QDate.currentDate())
        self.ed_wed_date.setCalendarPopup(True)
        self.ed_wed_date.setDisplayFormat("yyyy-MM-dd")
        self.ed_wed_hotel = QLineEdit(); self.ed_wed_hotel.setPlaceholderText("酒店名称")
        self.ed_wed_floor = QLineEdit(); self.ed_wed_floor.setPlaceholderText("几楼")
        self.ed_wed_hall = QLineEdit(); self.ed_wed_hall.setPlaceholderText("什么厅")
        self.ed_wed_groom = QLineEdit(); self.ed_wed_groom.setPlaceholderText("新郎名字")
        self.ed_wed_bride = QLineEdit(); self.ed_wed_bride.setPlaceholderText("新娘名字")
        ig.addWidget(QLabel("婚礼日期"), 0, 0); ig.addWidget(self.ed_wed_date, 0, 1)
        ig.addWidget(QLabel("酒店"), 0, 2); ig.addWidget(self.ed_wed_hotel, 0, 3)
        ig.addWidget(QLabel("楼层"), 0, 4); ig.addWidget(self.ed_wed_floor, 0, 5)
        ig.addWidget(QLabel("厅名"), 0, 6); ig.addWidget(self.ed_wed_hall, 0, 7)
        ig.addWidget(QLabel("新郎"), 1, 0); ig.addWidget(self.ed_wed_groom, 1, 1)
        ig.addWidget(QLabel("新娘"), 1, 2); ig.addWidget(self.ed_wed_bride, 1, 3)
        for w in (self.ed_wed_hotel, self.ed_wed_floor, self.ed_wed_hall, self.ed_wed_groom, self.ed_wed_bride):
            w.textChanged.connect(self._save_info)
        self.ed_wed_date.dateChanged.connect(self._save_info)
        lay.addWidget(info)
        self._load_info()

        self.tabs = QTabWidget()
        self.tabs.setObjectName("PrepTabs")
        lay.addWidget(self.tabs, 1)

        self.pane_people = ListPane(self, "people")
        self.pane_items = ListPane(self, "items")
        self.pane_flow = ListPane(self, "flow")
        self.tabs.addTab(self.pane_people, "人员清单")
        self.tabs.addTab(self.pane_items, "物品清单")
        self.tabs.addTab(self.pane_flow, "流程清单")

    def _load_info(self):
        raw = self.db.get_setting("prep_wedding_info", "")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        if data.get("date"):
            d = QDate.fromString(data["date"], "yyyy-MM-dd")
            if d.isValid():
                self.ed_wed_date.setDate(d)
        self.ed_wed_hotel.setText(data.get("hotel", ""))
        self.ed_wed_floor.setText(data.get("floor", ""))
        self.ed_wed_hall.setText(data.get("hall", ""))
        self.ed_wed_groom.setText(data.get("groom", ""))
        self.ed_wed_bride.setText(data.get("bride", ""))

    def _save_info(self, *_):
        data = {
            "date": self.ed_wed_date.date().toString("yyyy-MM-dd"),
            "hotel": self.ed_wed_hotel.text().strip(),
            "floor": self.ed_wed_floor.text().strip(),
            "hall": self.ed_wed_hall.text().strip(),
            "groom": self.ed_wed_groom.text().strip(),
            "bride": self.ed_wed_bride.text().strip(),
        }
        self.db.set_setting("prep_wedding_info", json.dumps(data, ensure_ascii=False))

    def refresh_summary(self):
        try:
            n1 = len(self.db.prep_people())
            n2 = len(self.db.prep_items())
            rows = self.db.prep_flow()
            n3 = len(rows)
            n_music = sum(1 for r in rows if r.get("music"))
            done = sum(1 for r in self.db.prep_items() if r.get("done"))
        except Exception:
            return
        self.lb_sum.setText(
            f"人员 {n1} 位　物品 {done}/{n2} 已备　流程 {n3} 个环节（{n_music} 个配乐）")

    def refresh(self):
        for p in (self.pane_people, self.pane_items, self.pane_flow):
            p.refresh()
        self.refresh_summary()
