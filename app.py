# -*- coding: utf-8 -*-
"""扶摇主持人工作台 - 主程序入口"""
import os
import math
import sys
import datetime
import json
import logging

from PySide6.QtCore import Qt, QTimer, QDate, QSize, QPoint, Signal, QRect, QRectF, QVariantAnimation, QEvent
from PySide6.QtGui import QIcon, QFont, QColor, QPainter, QPen, QBrush, QPixmap, QAction, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QStackedWidget, QFrame,
    QDialog, QDialogButtonBox, QLineEdit, QTextEdit, QComboBox, QSpinBox,
    QDateEdit, QTimeEdit, QMessageBox, QFileDialog, QScrollArea, QSystemTrayIcon,
    QMenu, QSizePolicy, QToolButton, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)

import common
import theme
import appicons
from common import (DB, APP_NAME, APP_VERSION, data_dir, asset_path,
                    export_backup, import_backup, setup_logging, get_setting, set_setting)

logger = logging.getLogger(__name__)

WINDOW_QSS = """
* { font-family: "PingFang SC", "Segoe UI Variable Text", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; }
QMainWindow, QWidget#Root { background: #111318; }
QWidget { color: #E8E6E1; font-size: 13px; }
QToolTip { background: #1A1D24; color: #E8E6E1; border: 1px solid #C9A86A; padding: 5px 8px; border-radius: 6px; }

QFrame#Card { background: #1A1D24; border: 1px solid #262A33; border-radius: 18px; }
QFrame#CardAlt { background: #151820; border: 1px solid #262A33; border-radius: 18px; }
QFrame#PlayerBar { background: #151820; border: 1px solid #262A33; border-radius: 18px; }

QLabel#Title { font-size: 24px; font-weight: 700; color: #F2EFE8; letter-spacing: 0.5px; }
QLabel#Body { color: #E8E6E1; }
QLabel#SubTitle { font-size: 12px; color: #8D919B; }
QLabel#SectionTitle { font-size: 14px; font-weight: 600; color: #E8E6E1; }
QLabel#Gold { color: #C9A86A; }
QLabel#BigNum { font-size: 28px; font-weight: 700; color: #C9A86A; }

QPushButton {
    background: #232833; color: #E8E6E1; border: 1px solid #262A33;
    border-radius: 12px; padding: 8px 18px;
}
QPushButton:hover { background: #2B3140; border-color: #3B4252; }
QPushButton:pressed { background: #1A1D24; }
QPushButton:disabled { color: #8D919B; background: #1A1D24; border-color: #262A33; }
QPushButton#Primary { background: #C9A86A; color: #14161B; font-weight: 600; border: none; }
QPushButton#Primary:hover { background: #D8BA82; }
QPushButton#Primary:pressed { background: #C9A86A; }
QPushButton#Danger { background: #4A2A2A; color: #E8C7C7; border-color: #5E3434; }
QPushButton#Danger:hover { background: #5E3434; }

QToolButton {
    background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 4px;
}
QToolButton:hover { background: #2B3140; }
QToolButton#LoopBtn { border: 1px solid #262A33; }
QToolButton#LoopBtn:hover { background: #2B3140; }
QToolButton#LoopBtn:checked { background: #2B3140; border-color: #C9A86A; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {
    background: #141720; border: 1px solid #262A33; border-radius: 10px;
    padding: 7px 10px; color: #E8E6E1; selection-background-color: #C9A86A;
    selection-color: #14161B;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus { border-color: #C9A86A; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #8D919B; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: transparent; border: none; width: 16px; margin-right: 3px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #2B3140; border-radius: 3px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid #8D919B; width: 0; height: 0;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #8D919B; width: 0; height: 0;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #1A1D24; color: #E8E6E1; border: 1px solid #262A33;
    selection-background-color: #2B3140; padding: 4px; outline: none;
}

QSlider::groove:horizontal { height: 4px; background: #2B303C; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #C9A86A; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
    background: #C9A86A; border: 2px solid #111318;
}
QSlider::handle:horizontal:hover { background: #D8BA82; }

#Side { background: #0D0F13; border-right: 1px solid #262A33; }
QListWidget#Nav {
    background: #0D0F13; border: none; outline: none; color: #9DA1AB;
    font-size: 15px;
}
QListWidget#Nav::item {
    padding-left: 20px; border-left: 3px solid transparent;
}
QListWidget#Nav::item:selected {
    background: #171B23; color: #E9E4D8; border-left: 3px solid #C9A86A;
}
QListWidget#Nav::item:hover { background: #141822; color: #E9E4D8; }

QListWidget#Plain, QTableWidget {
    background: #151820; border: 1px solid #262A33; border-radius: 14px;
    alternate-background-color: #171B23; outline: none; color: #E8E6E1;
}
QTableWidget QLineEdit { background: #1A1D24; color: #E8E6E1; border: 1px solid #C9A86A; }
QTableWidget::item { color: #E8E6E1; }
QListWidget#Plain::item { padding: 9px 10px; border-radius: 6px; }
QListWidget#Plain::item:selected { background: #2B3140; color: #E9E4D8; }
QListWidget#Plain::item:hover { background: #171B23; }

QTableWidget#PlayTable { background: #141720; border-radius: 14px; }
QTableWidget#PlayTable::item { padding: 4px 8px; }
QTableWidget#PlayTable::item:selected { background: #2B3140; color: #E9E4D8; }
QTableWidget::item { padding: 6px; }
QTableWidget::item:selected { background: #2B3140; color: #E9E4D8; }
QHeaderView::section {
    background: #1A1D24; color: #8D919B; border: none;
    border-bottom: 1px solid #262A33; padding: 8px 6px; font-weight: 600;
}
QHeaderView::section:hover { color: #E8E6E1; }

QTreeView {
    background: #141720; border: 1px solid #262A33; border-radius: 14px;
    outline: none; padding: 4px;
}
QTreeView::item { padding: 5px 4px; border-radius: 5px; }
QTreeView::item:hover { background: #1A1D24; }
QTreeView::item:selected { background: #2B3140; color: #E9E4D8; }

QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #2B303C; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #3B4252; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2B303C; border-radius: 4px; min-width: 32px; }

QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #262A33; background: #141720;
}
QCheckBox::indicator:checked { background: #C9A86A; border-color: #C9A86A; }
QTabWidget::pane { border: 1px solid #262A33; border-radius: 14px; background: #151820; }
QTabBar::tab { background: #1A1D24; color: #8D919B; padding: 9px 18px; border-radius: 7px; margin-right: 4px; }
QTabBar::tab:selected { background: #2B3140; color: #E9E4D8; }
QMenu { background: #1A1D24; color: #E8E6E1; border: 1px solid #262A33; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 7px 22px 7px 16px; border-radius: 5px; }
QMenu::item:selected { background: #2B3140; }
QMenu::separator { height: 1px; background: #262A33; margin: 4px 8px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""

BASE_QSS = WINDOW_QSS


class RegionBar(QWidget):
    """地区场次占比条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {"市区": 0, "省内": 0, "省外": 0}
        self.setMinimumHeight(44)

    def set_data(self, d):
        self.data = d
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        total = sum(self.data.values()) or 1
        colors = {"市区": "#C9A86A", "省内": "#79A6D8", "省外": "#A79CE0"}
        x = 0.0
        w = self.width()
        p.setPen(Qt.NoPen)
        for k in ("市区", "省内", "省外"):
            seg = w * self.data.get(k, 0) / total
            if seg > 0:
                p.setBrush(QBrush(QColor(colors[k])))
                p.drawRoundedRect(QRectF(x, 2, max(seg - 2, 2), 12), 6, 6)
            x += seg
        # 图例
        p.setFont(QFont("Microsoft YaHei UI", 8))
        lx = 0
        for k in ("市区", "省内", "省外"):
            p.setBrush(QBrush(QColor(colors[k])))
            p.drawEllipse(QRectF(lx, 22, 7, 7))
            p.setPen(QColor("#9DA1AB"))
            p.drawText(QRectF(lx + 11, 16, 70, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{k} {self.data.get(k, 0)}")
            lx += 92


def make_card(parent=None, alt=False) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


def h_line():
    ln = QFrame()
    ln.setFixedHeight(1)
    ln.setStyleSheet("background:%s;" % theme.THEMES[theme.current_theme()]["border"])
    return ln


# ---------------- 档期模块 ----------------
WEEK_CN = ["一", "二", "三", "四", "五", "六", "日"]


class DayCell(QFrame):
    """月历中的单日格子（单击即打开当日档期）"""
    clicked = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(theme.cell_qss("normal"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        self.day_label = QLabel("")
        self.day_label.setStyleSheet("font-weight:600;color:%s;background:transparent;border:none;" % theme.THEMES[theme.current_theme()]["text"])
        lay.addWidget(self.day_label)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-size:11px;color:%s;background:transparent;border:none;" % theme.THEMES[theme.current_theme()]["accent"])
        lay.addWidget(self.info)
        lay.addStretch()
        self.date = None

    def set_day(self, date: QDate, items, in_month=True):
        self.date = date
        self.day_label.setText(str(date.day()))
        t = theme.THEMES[theme.current_theme()]
        if not in_month:
            self.setStyleSheet(theme.cell_qss("out"))
            self.day_label.setStyleSheet(
                "font-weight:600;color:%s;background:transparent;border:none;" % t["sub"])
            self.info.setText("")
            return
        today = QDate.currentDate()
        base = theme.cell_qss("normal")
        if date == today:
            base = theme.cell_qss("today")
        elif items:
            base = theme.cell_qss("event")
        self.setStyleSheet(base)
        if items:
            # 日期标红 + 只显示场次类型
            self.day_label.setStyleSheet(
                "font-weight:700;color:#E05C5C;background:transparent;border:none;")
            slots = []
            for it in items:
                sl = (it.get("time_slot") or "").strip()
                if sl and sl not in slots:
                    slots.append(sl)
            txt = " / ".join(slots) if slots else f"{len(items)} 场"
            if len(items) > 1 and slots:
                txt += f"（{len(items)} 场）"
            self.info.setText(txt)
        else:
            self.day_label.setStyleSheet(
                "font-weight:600;color:%s;background:transparent;border:none;" % t["text"])
            self.info.setText("")
        self.setToolTip("\n".join(
            f"{i.get('time_slot','') or '未定场次'}  {i.get('client','') or '未填客户'}  "
            f"{i.get('venue','')}" for i in items) if items else "")

    def mouseReleaseEvent(self, ev):
        if self.date is not None and ev.button() == Qt.LeftButton:
            self.clicked.emit(self.date)
        super().mouseReleaseEvent(ev)


class EventDialog(QDialog):
    """某一天的档期编辑（不做必填校验，想填什么填什么）"""

    def __init__(self, db: DB, date: QDate, parent=None):
        super().__init__(parent)
        self.db = db
        self.date = date
        self.current_id = None
        self.setWindowTitle(f"档期管理 · {date.toString('yyyy年M月d日')}")
        self.setMinimumSize(640, 520)
        self.setStyleSheet(WINDOW_QSS)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.list = QListWidget()
        self.list.setObjectName("Plain")
        self.list.setFixedHeight(120)
        self.list.itemClicked.connect(self.on_select)
        lay.addWidget(self.list)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)
        self.ed_client = QLineEdit()
        self.ed_client.setPlaceholderText("客户 / 新人姓名（可空）")
        self.ed_phone = QLineEdit()
        self.ed_phone.setPlaceholderText("联系电话（可空）")
        self.ed_venue = QLineEdit()
        self.ed_venue.setPlaceholderText("酒店 / 场地（可空）")
        self.ed_slot = QComboBox()
        self.ed_slot.setEditable(False)
        self.ed_slot.addItems(["午宴", "晚宴", "午宴+晚宴"])
        self.ed_company = QLineEdit()
        self.ed_company.setPlaceholderText("合作公司 / 婚庆（可空）")
        self.cb_region = QComboBox()
        self.cb_region.addItems(["", "市区", "省内", "省外"])
        self.ed_fee = QLineEdit()
        self.ed_fee.setPlaceholderText("总费用，如 3000 或 ￥3,000")
        self.ed_deposit = QLineEdit()
        self.ed_deposit.setPlaceholderText("已收定金")
        self.lb_balance = QLabel("¥ 0")
        self.lb_balance.setStyleSheet("font-size:17px;font-weight:700;")
        self.ed_notes = QTextEdit()
        self.ed_notes.setPlaceholderText("备注：流程要点、特殊环节、客户偏好……")
        self.ed_notes.setFixedHeight(80)
        self.ed_fee.textChanged.connect(self._calc_balance)
        self.ed_deposit.textChanged.connect(self._calc_balance)

        form.addWidget(QLabel("客户"), 0, 0)
        form.addWidget(self.ed_client, 0, 1)
        form.addWidget(QLabel("电话"), 0, 2)
        form.addWidget(self.ed_phone, 0, 3)
        form.addWidget(QLabel("场地"), 1, 0)
        form.addWidget(self.ed_venue, 1, 1)
        form.addWidget(QLabel("场次"), 1, 2)
        form.addWidget(self.ed_slot, 1, 3)
        form.addWidget(QLabel("合作公司"), 2, 0)
        form.addWidget(self.ed_company, 2, 1)
        form.addWidget(QLabel("地区"), 2, 2)
        form.addWidget(self.cb_region, 2, 3)
        form.addWidget(QLabel("总费用"), 3, 0)
        form.addWidget(self.ed_fee, 3, 1)
        form.addWidget(QLabel("已收定金"), 3, 2)
        form.addWidget(self.ed_deposit, 3, 3)
        form.addWidget(QLabel("剩余尾款"), 4, 0)
        form.addWidget(self.lb_balance, 4, 1)
        tip = QLabel("尾款 = 总费用 − 已收定金，自动计算")
        tip.setObjectName("SubTitle")
        form.addWidget(tip, 4, 2, 1, 2)
        form.addWidget(QLabel("备注"), 5, 0)
        form.addWidget(self.ed_notes, 5, 1, 1, 3)
        lay.addLayout(form)

        btns = QHBoxLayout()
        btn_new = QPushButton("新增 / 清空")
        btn_save = QPushButton("保存")
        btn_save.setObjectName("Primary")
        btn_del = QPushButton("删除")
        btn_del.setObjectName("Danger")
        btn_close = QPushButton("关闭")
        btn_new.clicked.connect(self.clear_form)
        btn_save.clicked.connect(self.save)
        btn_del.clicked.connect(self.delete)
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_new)
        btns.addWidget(btn_del)
        btns.addStretch()
        btns.addWidget(btn_close)
        btns.addWidget(btn_save)
        lay.addLayout(btns)

        self.reload()

    def _calc_balance(self, *_):
        fee = common._parse_money(self.ed_fee.text())
        dep = common._parse_money(self.ed_deposit.text())
        bal = fee - dep
        txt = f"¥ {bal:,.0f}" if abs(bal - round(bal)) < 0.01 else f"¥ {bal:,.2f}"
        color = "#E05C5C" if bal < 0 else theme.THEMES[theme.current_theme()]["accent"]
        self.lb_balance.setText(txt)
        self.lb_balance.setStyleSheet(f"font-size:17px;font-weight:700;color:{color};")

    def reload(self):
        self.list.clear()
        self.items = self.db.events_on(self.date.toString("yyyy-MM-dd"))
        for it in self.items:
            text = (f"{(it.get('time_slot') or '未定').strip()}  "
                    f"{it.get('client') or '未填客户'}  ·  {it.get('venue','')}")
            row = QListWidgetItem(text)
            row.setData(Qt.UserRole, it["id"])
            self.list.addItem(row)
        if not self.items:
            self.list.addItem(QListWidgetItem("当日暂无档期，填写下方表单后点击“保存”"))

    def on_select(self, item):
        eid = item.data(Qt.UserRole)
        if not eid:
            return
        it = next((x for x in self.items if x["id"] == eid), None)
        if not it:
            return
        self.current_id = eid
        self.ed_client.setText(it.get("client", ""))
        self.ed_phone.setText(it.get("phone", ""))
        self.ed_venue.setText(it.get("venue", ""))
        self.ed_slot.setCurrentText(it.get("time_slot", "") or "午宴")
        self.ed_company.setText(it.get("company", ""))
        self.ed_fee.setText(it.get("fee", ""))
        self.ed_deposit.setText(it.get("deposit", ""))
        self.cb_region.setCurrentText(it.get("region", ""))
        self.ed_notes.setPlainText(it.get("notes", ""))
        self._calc_balance()

    def clear_form(self):
        self.current_id = None
        for w in (self.ed_client, self.ed_phone, self.ed_venue, self.ed_company,
                  self.ed_fee, self.ed_deposit):
            w.clear()
        self.ed_slot.setCurrentText("午宴")
        self.cb_region.setCurrentText("")
        self.ed_notes.clear()
        self._calc_balance()

    def collect(self):
        return {
            "date": self.date.toString("yyyy-MM-dd"),
            "client": self.ed_client.text().strip(),
            "phone": self.ed_phone.text().strip(),
            "venue": self.ed_venue.text().strip(),
            "time_slot": self.ed_slot.currentText().strip(),
            "fee": self.ed_fee.text().strip(),
            "deposit": self.ed_deposit.text().strip(),
            "company": self.ed_company.text().strip(),
            "notes": self.ed_notes.toPlainText().strip(),
            "region": self.cb_region.currentText().strip(),
        }

    def save(self):
        data = self.collect()
        if self.current_id:
            self.db.update_event(self.current_id, **data)
        else:
            self.db.add_event(**data)
        logger.info("档期保存: %s %s", data["date"], data["client"] or "(空)")
        self.accept()

    def delete(self):
        if not self.current_id:
            QMessageBox.information(self, "提示", "请先在列表中选择要删除的档期")
            return
        if QMessageBox.question(self, "确认", "确定删除这条档期吗？") == QMessageBox.Yes:
            self.db.delete_event(self.current_id)
            self.current_id = None
            self.reload()
            self.clear_form()


class CalendarPage(QWidget):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.year = datetime.date.today().year
        self.month = datetime.date.today().month
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        self.title = QLabel("档期管理")
        self.title.setObjectName("Title")
        head.addWidget(self.title)
        head.addSpacing(16)
        self.btn_prev = QPushButton("‹ 上月")
        self.btn_today = QPushButton("今天")
        self.btn_next = QPushButton("下月 ›")
        self.btn_prev.clicked.connect(lambda: self.jump(-1))
        self.btn_next.clicked.connect(lambda: self.jump(1))
        self.btn_today.clicked.connect(self.to_today)
        head.addWidget(self.btn_prev)
        head.addWidget(self.btn_today)
        head.addWidget(self.btn_next)
        head.addStretch()
        self.btn_backup = QPushButton("导出加密备份")
        self.btn_restore = QPushButton("恢复备份")
        self.btn_backup.clicked.connect(self.export_backup_dlg)
        self.btn_restore.clicked.connect(self.restore_backup_dlg)
        head.addWidget(self.btn_backup)
        head.addWidget(self.btn_restore)
        lay.addLayout(head)

        self.month_label = QLabel()
        self.month_label.setObjectName("SubTitle")
        lay.addWidget(self.month_label)

        # 年度统计
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        c_income, self.val_income = self._sum_card("今年收入")
        c_count, self.val_count = self._sum_card(f"今年场次（{datetime.date.today().year}）")
        c_mix = make_card(alt=True)
        mv = QVBoxLayout(c_mix)
        mv.setContentsMargins(16, 10, 16, 8)
        mv.setSpacing(2)
        lb_mix = QLabel("今年地区分布 · 市区 / 省内 / 省外")
        lb_mix.setStyleSheet("color:#8D919B;font-size:12px;")
        mv.addWidget(lb_mix)
        self.region_bar = RegionBar()
        mv.addWidget(self.region_bar)
        stats_row.addWidget(c_income, 1)
        stats_row.addWidget(c_count, 1)
        stats_row.addWidget(c_mix, 2)
        lay.addLayout(stats_row)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, w in enumerate(WEEK_CN):
            lb = QLabel(f"周{w}")
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet("color:#8D919B;font-weight:600;padding:4px;")
            grid.addWidget(lb, 0, i)
        self.cells = []
        for r in range(6):
            for c in range(7):
                cell = DayCell()
                cell.clicked.connect(self.open_day)
                grid.addWidget(cell, r + 1, c)
                self.cells.append(cell)
        lay.addLayout(grid, 1)

        tip = QLabel("单击日期即可查看 / 新增当日档期；同一天可分别记录午宴与晚宴。数据本地存储，可随时导出备份。")
        tip.setObjectName("SubTitle")
        lay.addWidget(tip)

        self.render()

    def jump(self, delta):
        m = self.month + delta
        y = self.year
        if m < 1:
            m = 12
            y -= 1
        elif m > 12:
            m = 1
            y += 1
        self.year, self.month = y, m
        self.render()

    def to_today(self):
        t = datetime.date.today()
        self.year, self.month = t.year, t.month
        self.render()

    def _sum_card(self, title, color="#C9A86A"):
        card = make_card(alt=True)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(2)
        lb = QLabel(title)
        lb.setStyleSheet("color:#8D919B;font-size:12px;")
        val = QLabel("—")
        val.setStyleSheet(f"font-size:22px;font-weight:700;color:{color};")
        v.addWidget(lb)
        v.addWidget(val)
        return card, val

    def render(self):
        counts = self.db.event_counts_month(self.year, self.month)
        self.month_label.setText(f"{self.year} 年 {self.month} 月   ·   本月档期 {sum(counts.values())} 场")
        # 年度统计（今年的收入 / 场次 / 地区分布）
        try:
            st = self.db.stats_year(datetime.date.today().year)
            self.val_income.setText(f"¥ {st['income']:,.0f}")
            self.val_count.setText(f"{st['count']} 场")
            self.region_bar.set_data(st["regions"])
        except Exception:
            logger.exception("年度统计失败")
        first = QDate(self.year, self.month, 1)
        start_col = first.dayOfWeek() - 1  # 周一为0
        start_day = first.addDays(-start_col)
        for idx, cell in enumerate(self.cells):
            d = start_day.addDays(idx)
            in_month = d.month() == self.month
            items = self.db.events_on(d.toString("yyyy-MM-dd")) if in_month else []
            cell.set_day(d, items, in_month)

    def open_day(self, date: QDate):
        dlg = EventDialog(self.db, date, self)
        dlg.exec()
        self.render()

    def refresh(self):
        self.render()

    # ---------- 备份 ----------
    def export_backup_dlg(self):
        out_dir = self.db.get_setting("backup_dir", "") or common.default_backup_dir()
        os.makedirs(out_dir, exist_ok=True)
        name = "档期备份_" + datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".fhbackup"
        path = os.path.join(out_dir, name)
        try:
            export_backup("", path)
            QMessageBox.information(self, "备份成功", f"已导出备份（无需密码）：\n{path}\n\n"
                                                    f"可把该文件上传到百度网盘等云盘保存。")
            logger.info("导出备份: %s", path)
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def restore_backup_dlg(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", data_dir(), "备份文件 (*.fhbackup);;所有文件 (*)")
        if not path:
            return
        if import_backup(path, ""):
            QMessageBox.information(self, "恢复成功", "备份已恢复，请重新打开应用生效。")
            self.render()
            logger.info("恢复备份: %s", path)
        else:
            QMessageBox.warning(self, "恢复失败", "备份文件损坏或格式不匹配。")


def QInputDialogGetText(parent, title, label):
    """简单密码输入对话框，返回 (text, ok)"""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet(WINDOW_QSS)
    dlg.resize(380, 140)
    v = QVBoxLayout(dlg)
    lb = QLabel(label)
    v.addWidget(lb)
    ed = QLineEdit()
    ed.setEchoMode(QLineEdit.Password)
    v.addWidget(ed)
    row = QHBoxLayout()
    ok_btn = QPushButton("确定")
    ok_btn.setObjectName("Primary")
    cancel_btn = QPushButton("取消")
    row.addStretch()
    row.addWidget(cancel_btn)
    row.addWidget(ok_btn)
    v.addLayout(row)
    result = {"ok": False}
    ok_btn.clicked.connect(lambda: (result.update(ok=True), dlg.accept()))
    cancel_btn.clicked.connect(dlg.reject)
    dlg.exec()
    return ed.text(), result["ok"]


# ---------------- 首页 ----------------
class DashboardPage(QWidget):
    navigate = Signal(int)

    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        head = QHBoxLayout()
        self.greet = QLabel()
        self.greet.setObjectName("Title")
        head.addWidget(self.greet)
        head.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("SubTitle")
        head.addWidget(self.date_label)
        lay.addLayout(head)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.card_month, self.val_month = self._stat_card("本月档期", "0")
        self.card_income, self.val_income = self._stat_card("今年收入", "¥ 0")
        self.card_next, self.val_next = self._stat_card("最近一场", "—")
        self.card_memo, self.val_memo = self._stat_card("待办提醒", "0")
        self.card_total, self.val_total = self._stat_card("累计档期", "0")
        for c in (self.card_month, self.card_income, self.card_next, self.card_memo, self.card_total):
            stats_row.addWidget(c, 1)
        lay.addLayout(stats_row)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        # 最近档期
        left = make_card()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 14, 16, 14)
        t1 = QLabel("近期档期")
        t1.setObjectName("SectionTitle")
        lv.addWidget(t1)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("Plain")
        self.recent_list.setStyleSheet("background:transparent;border:none;")
        lv.addWidget(self.recent_list)
        mid.addWidget(left, 3)

        # 待办提醒
        right = make_card()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 14, 16, 14)
        t2 = QLabel("待办提醒")
        t2.setObjectName("SectionTitle")
        rv.addWidget(t2)
        self.memo_list = QListWidget()
        self.memo_list.setObjectName("Plain")
        self.memo_list.setStyleSheet("background:transparent;border:none;")
        rv.addWidget(self.memo_list)
        mid.addWidget(right, 2)
        lay.addLayout(mid, 1)

        quick = QHBoxLayout()
        quick.setSpacing(10)
        tcol = theme.THEMES[theme.current_theme()]["text"]
        for text, idx, ico in [("新建档期", 1, "calendar"), ("AI 写主持词", 5, "ai"),
                               ("图文设计", 2, "design"), ("预演沙盘", 3, "stage"),
                               ("添加备忘", 4, "memo"), ("备婚工具", 6, "prep")]:
            b = QPushButton(text)
            b.setIcon(appicons.icon(ico, 18, tcol))
            b.setIconSize(QSize(18, 18))
            b.clicked.connect(lambda _=False, i=idx: self.navigate.emit(i))
            quick.addWidget(b)
        quick.addStretch()
        lay.addLayout(quick)

        self.refresh()

    def _stat_card(self, title, value):
        card = make_card(alt=True)
        card.setMinimumHeight(86)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        lb = QLabel(title)
        lb.setStyleSheet("color:#8D919B;font-size:12px;")
        val = QLabel(value)
        val.setObjectName("BigNum")
        v.addWidget(lb)
        v.addWidget(val)
        return card, val

    def refresh(self):
        now = datetime.datetime.now()
        h = now.hour
        greet = "上午好" if h < 12 else ("下午好" if h < 18 else "晚上好")
        self.greet.setText("主持人工作台")
        wk = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
        self.date_label.setText(now.strftime(f"%Y年%m月%d日  周{wk}"))

        today = datetime.date.today()
        ym = today.strftime("%Y-%m")
        evs = self.db.events_between(ym + "-01", ym + "-31")
        self.val_month.setText(str(len(evs)))

        all_ev = self.db.events_all()
        future = [e for e in all_ev if (e["date"] or "") >= today.strftime("%Y-%m-%d")]
        if future:
            first = future[0]
            self.val_next.setText(f"{first['date'][5:]}  {first['client'] or '未命名'}")
            self.val_next.setStyleSheet("font-size:15px;font-weight:600;color:#C9A86A;")
        else:
            self.val_next.setText("—")
        self.val_total.setText(str(len(all_ev)))
        # 今年收入
        try:
            st = self.db.stats_year(today.year)
            self.val_income.setText(f"¥ {st['income']:,.0f}")
        except Exception:
            self.val_income.setText("¥ 0")

        open_memos = self.db.memos_all(only_open=True)
        self.val_memo.setText(str(len(open_memos)))

        self.recent_list.clear()
        for e in future[:6]:
            txt = f"{e['date'][5:]}  ·  {e['client'] or '未命名'}   {e['venue']}"
            self.recent_list.addItem(txt)
        if not future:
            self.recent_list.addItem("暂无即将到来的档期")

        self.memo_list.clear()
        for m in open_memos[:6]:
            star = "★ " if m["important"] else ""
            due = m["due"][5:] if m["due"] else "未定时间"
            self.memo_list.addItem(f"{star}{m['title']}   ({due})")
        if not open_memos:
            self.memo_list.addItem("暂无待办，点击下方快速添加")


# ---------------- 主窗口 ----------------
NAV_ITEMS = [
    ("工作台", "dashboard"), ("档期管理", "calendar"), ("图文设计", "design"),
    ("预演沙盘", "stage"), ("备忘提醒", "memo"), ("主持助理", "ai"),
    ("备婚工具", "prep"), ("音乐播放器", "music"), ("设置", "settings"),
    ("开发者选项", "dev"),
]


class NavDelegate(QStyledItemDelegate):
    """悬停轻微放大，点击后轻震一下"""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.hover_row = -1
        self.hover = 0.0
        self.shake_row = -1
        self.shake = 0.0
        self.hover_anim = QVariantAnimation(self)
        self.hover_anim.setDuration(150)
        self.hover_anim.valueChanged.connect(self._on_hover)
        self.shake_anim = QVariantAnimation(self)
        self.shake_anim.setDuration(280)
        self.shake_anim.valueChanged.connect(self._on_shake)

    def _on_hover(self, v):
        self.hover = float(v)
        self.view.viewport().update()

    def _on_shake(self, v):
        self.shake = float(v)
        self.view.viewport().update()

    def set_hover(self, row):
        if row == self.hover_row:
            return
        self.hover_row = row
        self.hover_anim.stop()
        self.hover_anim.setStartValue(self.hover)
        self.hover_anim.setEndValue(1.0 if row >= 0 else 0.0)
        self.hover_anim.start()

    def shake(self, row):
        self.shake_row = row
        self.shake_anim.stop()
        self.shake_anim.setStartValue(0.0)
        self.shake_anim.setEndValue(1.0)
        self.shake_anim.start()

    def paint(self, painter, option, index):
        row = index.row()
        grow = self.hover if row == self.hover_row else 0.0
        off = 0.0
        if row == self.shake_row and 0 < self.shake < 1:
            off = math.sin(self.shake * math.pi * 4) * 11 * (1 - self.shake) ** 1.5
        if grow <= 0.001 and abs(off) < 0.5:
            super().paint(painter, option, index)
            return
        painter.save()
        c = option.rect.center()
        painter.translate(c.x() + off, c.y())
        painter.scale(1.0 + 0.075 * grow, 1.0 + 0.075 * grow)
        painter.translate(-c.x(), -c.y())
        opt = QStyleOptionViewItem(option)
        opt.rect = option.rect.adjusted(-6, -4, 6, 4)
        super().paint(painter, opt, index)
        painter.restore()


class NavList(QListWidget):
    """左侧导航：功能项按可用高度均匀分布"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self._delegate = NavDelegate(self)
        self.setItemDelegate(self._delegate)
        self.viewport().installEventFilter(self)
        self.itemClicked.connect(lambda it: self._delegate.shake(self.row(it)))

    def _distribute(self):
        n = self.count()
        if n <= 0:
            return
        h = max(38, int(self.viewport().height() / n))
        for i in range(n):
            it = self.item(i)
            it.setSizeHint(QSize(self.viewport().width() - 2, h))

    def eventFilter(self, obj, ev):
        try:
            if obj is self.viewport():
                if ev.type() == QEvent.MouseMove:
                    idx = self.indexAt(ev.position().toPoint())
                    self._delegate.set_hover(idx.row() if idx.isValid() else -1)
                elif ev.type() == QEvent.Leave:
                    self._delegate.set_hover(-1)
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._distribute()

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._distribute)


class MainWindow(QMainWindow):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.setWindowTitle(f"{self.db.get_setting('workbench_name', APP_NAME)}  v{APP_VERSION}")
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1280, 800)
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(WINDOW_QSS)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # 左侧导航
        side = QWidget()
        side.setObjectName("Side")
        side.setFixedWidth(220)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 22, 0, 16)
        sv.setSpacing(0)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(20, 0, 16, 0)
        icon_lb = QLabel()
        if os.path.exists(icon_path):
            icon_lb.setPixmap(QIcon(icon_path).pixmap(QSize(30, 30)))
            icon_lb.setFixedSize(32, 32)
        logo_row.addWidget(icon_lb)
        name_lb = QLabel(self.db.get_setting("workbench_name", APP_NAME))
        self.logo_name = name_lb
        self.brand_name = name_lb
        name_lb.setStyleSheet("font-size:15px;font-weight:600;color:%s;letter-spacing:1px;"
                          % theme.THEMES[theme.current_theme()]["title"])
        logo_row.addWidget(name_lb)
        logo_row.addStretch()
        sv.addLayout(logo_row)
        sv.addSpacing(18)

        self.nav = NavList()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(220)
        self.nav.setIconSize(QSize(26, 26))
        for title, ico in NAV_ITEMS:
            it = QListWidgetItem(f"    {title}")
            it.setIcon(appicons.icon(ico, 26, "#9DA1AB"))
            self.nav.addItem(it)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.switch_page)
        self.nav.currentRowChanged.connect(self._tint_nav)
        sv.addWidget(self.nav, 1)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet("color:#3E434E;font-size:10px;padding-left:22px;")
        sv.addWidget(ver)
        self.side = side
        h.addWidget(side)

        # 右侧页面
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(26, 20, 26, 18)
        rv.setSpacing(0)
        self.stack = QStackedWidget()
        rv.addWidget(self.stack)
        h.addWidget(right, 1)

        # 页面实例
        from pages_design import DesignPage
        from pages_rehearsal import RehearsalPage
        from pages_music import MusicPage
        from pages_media import SettingsPage
        from pages_misc import MemoPage, AIWriterPage, DeveloperPage
        from pages_prep import PrepPage

        self.dashboard = DashboardPage(db)
        self.calendar = CalendarPage(db)
        self.design = DesignPage(db)
        self.rehearsal = RehearsalPage(db)
        self.memo = MemoPage(db)
        self.ai_page = AIWriterPage(db)
        self.prep = PrepPage(db)
        self.music = MusicPage()
        self.settings = SettingsPage()
        self.dev = DeveloperPage(db)

        self.pages = [self.dashboard, self.calendar, self.design, self.rehearsal,
                      self.memo, self.ai_page, self.prep, self.music, self.settings, self.dev]
        for p in self.pages:
            self.stack.addWidget(p)

        self.dashboard.navigate.connect(self.go)

        # 系统托盘
        self.tray = QSystemTrayIcon(QIcon(icon_path) if os.path.exists(icon_path) else self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self.show_normal)
        menu.addSeparator()
        act_play = menu.addAction("播放 / 暂停")
        act_play.triggered.connect(lambda: self.music.toggle_play())
        act_prev = menu.addAction("上一曲")
        act_prev.triggered.connect(lambda: self.music.play_prev())
        act_next = menu.addAction("下一曲")
        act_next.triggered.connect(lambda: self.music.play_next())
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(lambda r: self.show_normal() if r == QSystemTrayIcon.DoubleClick else None)

        # 定时提醒检查
        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(30000)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start()
        self._notified = set()

        self.switch_page(0)

    def go(self, idx):
        self.nav.setCurrentRow(idx)

    def apply_name(self, name):
        name = (name or "主持人工作台").strip() or "主持人工作台"
        self.setWindowTitle(f"{name}  v{APP_VERSION}")
        if hasattr(self, "brand_name"):
            self.brand_name.setText(name)
        if hasattr(self, "logo_name"):
            self.logo_name.setText(name)

    def _tint_nav(self, idx):
        try:
            for i in range(self.nav.count()):
                color = "#C9A86A" if i == idx else "#A9A39A"
                self.nav.item(i).setIcon(appicons.icon(NAV_ITEMS[i][1], 26, color))
        except Exception:
            pass

    def switch_page(self, idx):
        if idx < 0:
            return
        self.stack.setCurrentIndex(idx)
        if idx == 0:
            self.dashboard.refresh()
        elif idx == 1:
            self.calendar.refresh()
        elif idx == 2:
            pass
        elif idx == 3:
            self.rehearsal.refresh()
        elif idx == 4:
            self.memo.refresh()
        elif idx == 6:
            self.prep.refresh()
        elif idx == 7:
            self.music.refresh()
        elif idx == 8:
            self.settings.load_values()

    def apply_theme(self, name):
        """选择/保存后立即换肤；同时强制刷新 macOS 下的原生控件与窗口"""
        global WINDOW_QSS
        WINDOW_QSS = theme.build_qss(BASE_QSS, name)
        t = theme.THEMES.get(name, theme.THEMES["暗夜金"])
        logger.info("切换主题: %s", name)

        app = QApplication.instance()
        if app is not None:
            # 只在 MainWindow 上设置样式时，macOS 的部分原生子控件/对话框不会跟着换色；
            # 这里同时设到 QApplication，并同步 palette 兜底。
            app.setStyleSheet(WINDOW_QSS)
            try:
                pal = QPalette()
                pal.setColor(QPalette.Window, QColor(t["bg"]))
                pal.setColor(QPalette.WindowText, QColor(t["text"]))
                pal.setColor(QPalette.Base, QColor(t["input"]))
                pal.setColor(QPalette.AlternateBase, QColor(t["card_alt"]))
                pal.setColor(QPalette.Text, QColor(t["text"]))
                pal.setColor(QPalette.Button, QColor(t["btn"]))
                pal.setColor(QPalette.ButtonText, QColor(t["text"]))
                pal.setColor(QPalette.Highlight, QColor(t["accent"]))
                pal.setColor(QPalette.HighlightedText, QColor("#14161B" if name == "日间白" else "#FFFFFF"))
                pal.setColor(QPalette.ToolTipBase, QColor(t["card"]))
                pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
                pal.setColor(QPalette.PlaceholderText, QColor(t["sub"]))
                app.setPalette(pal)
            except Exception:
                logger.exception("设置主题 palette 失败")

        self.setStyleSheet(WINDOW_QSS)
        try:
            if self.centralWidget() is not None:
                self.centralWidget().setStyleSheet(WINDOW_QSS)
            self.logo_name.setStyleSheet(
                "font-size:15px;font-weight:600;color:%s;letter-spacing:1px;" % t["title"])
            for w in self.findChildren(QLabel):
                if w.objectName() == "Title":
                    w.setStyleSheet("")
        except Exception:
            pass

        for page in getattr(self, "pages", []):
            for fn in ("render", "refresh"):
                if hasattr(page, fn):
                    try:
                        getattr(page, fn)()
                    except Exception:
                        pass
                    break

        # 让已经创建的原生控件重新 polish，避免 macOS 缓存旧调色板
        try:
            if app is not None:
                for w in app.allWidgets():
                    try:
                        w.style().unpolish(w)
                        w.style().polish(w)
                        w.update()
                    except Exception:
                        pass
                for w in app.topLevelWidgets():
                    try:
                        w.setStyleSheet(WINDOW_QSS)
                        w.update()
                    except Exception:
                        pass
        except Exception:
            logger.exception("刷新主题控件失败")
        self.update()

    def show_normal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def check_reminders(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        due = self.db.due_memos(now)
        for m in due:
            if m["id"] in self._notified:
                continue
            self._notified.add(m["id"])
            self.show_reminder(m)

    def show_reminder(self, m):
        title = "重要提醒" if m["important"] else "备忘提醒"
        msg = f"{m['title']}\n\n提醒时间：{m['due']}"
        self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 5000)
        self._play_alert(m)
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.setStandardButtons(QMessageBox.Ok)
        box.setStyleSheet(WINDOW_QSS)
        box.exec()

    def _play_alert(self, m):
        """按设置为提醒播放提示音：关闭 / 系统提示音 / 内置铃声 / 自选文件"""
        snd = get_setting("memo_sound", "1")
        if snd in ("0", "off", ""):
            return
        try:
            if snd in ("1", "beep", "system"):
                import winsound
                if m["important"]:
                    for _ in range(3):
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                else:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                return
            path = snd
            if snd in ("ring1", "ring2", "ring3"):
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "sounds", snd + ".wav")
            if not os.path.exists(path):
                return
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            if getattr(self, "_snd", None) is None:
                self._snd = QSoundEffect(self)
                self._snd.setVolume(0.85)
            self._snd.setSource(QUrl.fromLocalFile(path))
            self._snd.play()
            if m["important"]:
                QTimer.singleShot(900, self._snd.play)
        except Exception:
            logger.exception("播放提醒铃声失败")

    def _cleanup(self):
        """退出前收尾：停播放、停定时器、保存状态、隐藏托盘"""
        try:
            self.reminder_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "music", None):
                self.music.save_state()
                if self.music.player:
                    self.music.player.stop()
                if self.music.audio:
                    self.music.audio.setVolume(0)
        except Exception:
            logger.exception("关闭音乐模块失败")
        try:
            self.tray.hide()
        except Exception:
            pass

    def quit_app(self):
        self._cleanup()
        QApplication.quit()

    def closeEvent(self, ev):
        # 关闭到托盘（可在设置中关闭该行为）
        if get_setting("minimize_tray", "0") == "1" and self.tray.isVisible():
            ev.ignore()
            self.hide()
            self.tray.showMessage(APP_NAME, "已最小化到托盘，提醒功能持续运行。",
                                  QSystemTrayIcon.Information, 3000)
        else:
            self._cleanup()
            ev.accept()
            QTimer.singleShot(0, QApplication.quit)


def _run_selftest(app, win, db, outdir):
    """打包后自检：逐页截图 + 导出样例，结果写入 outdir"""
    import os
    os.makedirs(outdir, exist_ok=True)
    report = []

    def shot(name):
        win.grab().save(os.path.join(outdir, name + ".png"))
        report.append("shot " + name)

    def run():
        try:
            for idx, name in [(0, "0-dashboard"), (2, "1-design"), (5, "4-ai"),
                              (6, "2-prep"), (3, "3-sandbox"), (7, "5-music")]:
                win.switch_page(idx)
                for _ in range(4):
                    app.processEvents()
                shot(name)
            p = win.prep
            win.switch_page(6)
            for _ in range(3):
                app.processEvents()
            p.tabs.setCurrentIndex(2)
            for _ in range(3):
                app.processEvents()
            shot("2b-prep-flow")
            # 导出 Word
            import pages_prep as P
            for kind, pane, fname in (("people", p.pane_people, "人员清单.docx"),
                                      ("items", p.pane_items, "物品清单.docx"),
                                      ("flow", p.pane_flow, "流程安排.docx")):
                P.export_word(os.path.join(outdir, fname), kind, pane.headers, pane.keys, pane.rows)
                report.append("docx " + fname)
            # 沙盘
            win.switch_page(3)
            for _ in range(3):
                app.processEvents()
            r = win.rehearsal
            r.sp_phases.setValue(3)
            r.add_prop("圆桌")
            r.add_prop("长条凳")
            try:
                if len(r.canvas.actors) >= 2:
                    r.canvas.actors[-2]["x"], r.canvas.actors[-2]["y"] = 0.24, 0.62
                    r.canvas.actors[-1]["x"], r.canvas.actors[-1]["y"] = 0.77, 0.50
            except Exception:
                pass
            r.preset_aisle_path()
            r.tabs.setCurrentIndex(0)
            for _ in range(3):
                app.processEvents()
            shot("3b-sandbox-scene")
            r.tabs.setCurrentIndex(1)
            for _ in range(2):
                app.processEvents()
            shot("3c-sandbox-people")
            r.tabs.setCurrentIndex(2)
            r.canvas.set_progress(0.55)
            for _ in range(2):
                app.processEvents()
            shot("3d-sandbox-path")
            img = r.canvas.to_image(1.5)
            img.save(os.path.join(outdir, "沙盘画面.png"), "PNG")
            report.append("png 沙盘画面")
            r.sp_secs.setValue(8)
            r.export_mp4(os.path.join(outdir, "沙盘演示.mp4"), fps=20, silent=True)
            report.append("mp4 沙盘演示")
            # 图文设计导出
            d = win.design
            win.switch_page(2)
            for _ in range(3):
                app.processEvents()
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtCore import QRectF, Qt
            img = QImage(d.canvas_w, d.canvas_h, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            pt = QPainter(img)
            d.scene.clearSelection()
            d.scene.render(pt, QRectF(0, 0, d.canvas_w, d.canvas_h),
                           QRectF(0, 0, d.canvas_w, d.canvas_h))
            pt.end()
            img.save(os.path.join(outdir, "图文设计.png"), "PNG")
            report.append("png 图文设计")
            d.export_ppt(os.path.join(outdir, "婚礼提案.pptx"), silent=True)
            report.append("pptx 婚礼提案")
            report.append("OK")
        except Exception:
            import traceback
            report.append("ERROR\n" + traceback.format_exc())
        finally:
            with open(os.path.join(outdir, "selftest.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(report))
            app.quit()

    from PySide6.QtCore import QTimer
    QTimer.singleShot(1200, run)


def main():
    setup_logging("INFO")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    app.setStyle("Fusion")
    # 内置可商用艺术字体
    try:
        import fonts
        fonts.load_builtin_fonts()
    except Exception:
        logger.exception("加载内置字体失败")
    db = DB()
    # 主题（设置中可选多套风格）
    global WINDOW_QSS
    WINDOW_QSS = theme.build_qss(BASE_QSS, db.get_setting("theme", "暗夜金"))
    import licensing
    if "--selftest" not in sys.argv and not licensing.ensure_license(WINDOW_QSS):
        sys.exit(0)
    win = MainWindow(db)
    win.show()
    logger.info("应用启动")
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        outdir = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.join(
            data_dir(), "selftest")
        _run_selftest(app, win, db, outdir)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
