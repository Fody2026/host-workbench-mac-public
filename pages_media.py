# -*- coding: utf-8 -*-
"""音乐库/播放/音频编辑 + 常规设置"""
import os
import sys
import logging

from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFrame, QComboBox, QSlider, QLineEdit, QFileDialog,
    QMessageBox, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox, QGridLayout,
    QAbstractItemView, QInputDialog, QScrollArea
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

import common
import theme
from common import data_dir, get_setting, set_setting

logger = logging.getLogger(__name__)

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma")


def make_card(parent=None, alt=False):
    f = QFrame(parent)
    f.setObjectName("CardAlt" if alt else "Card")
    return f


def _fmt_time(ms):
    if ms <= 0:
        return "00:00"
    s = int(ms / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


# ============================================================
#  音频编辑工作线程（pydub）
# ============================================================
class AudioWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, op, kwargs):
        super().__init__()
        self.op, self.kw = op, kwargs

    def run(self):
        try:
            from pydub import AudioSegment
            common.configure_ffmpeg()
            if self.op == "edit":
                src = self.kw["src"]
                seg = AudioSegment.from_file(src)
                start = int(self.kw["start"] * 1000)
                end = int(self.kw["end"] * 1000)
                if end > 0 and end < len(seg):
                    seg = seg[start:end]
                elif start > 0:
                    seg = seg[start:]
                speed = self.kw.get("speed", 1.0)
                if abs(speed - 1.0) > 0.01:
                    if speed > 1:
                        seg = seg.speedup(playback_speed=speed)
                    elif speed > 0:
                        seg = seg.slowdown(playback_speed=1.0 / speed)
                fi = self.kw.get("fade_in", 0)
                fo = self.kw.get("fade_out", 0)
                if fi > 0:
                    seg = seg.fade_in(int(fi * 1000))
                if fo > 0:
                    seg = seg.fade_out(int(fo * 1000))
                seg.export(self.kw["out"], format="wav")
                self.done.emit(True, self.kw["out"])
            elif self.op == "concat":
                segs = []
                for p in self.kw["paths"]:
                    segs.append(AudioSegment.from_file(p))
                total = AudioSegment.empty()
                for s in segs:
                    total += s
                total.export(self.kw["out"], format="wav")
                self.done.emit(True, self.kw["out"])
        except Exception as e:
            logger.exception("音频处理失败")
            self.done.emit(False, str(e))


# ============================================================
#  音乐页
# ============================================================
class MusicPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = None
        self.audio = None
        self.playlist = []
        self.current_idx = -1
        self.editing_src = ""
        self.concat_list = []
        self.worker = None
        self._build_ui()
        self._init_player()
        self.scan_library()

    def _init_player(self):
        self.audio = QAudioOutput(self)
        try:
            vol = int(get_setting("music_volume", "70"))
        except Exception:
            vol = 70
        self.audio.setVolume(vol / 100)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.mediaStatusChanged.connect(self._on_status)

    # ---------- UI ----------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("音乐库 · 播放与剪辑")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addSpacing(10)
        b_add = QPushButton("添加音乐")
        b_add.clicked.connect(self.add_files)
        b_folder = QPushButton("添加文件夹")
        b_folder.clicked.connect(self.add_folder)
        b_refresh = QPushButton("刷新")
        b_refresh.clicked.connect(self.scan_library)
        head.addWidget(b_add)
        head.addWidget(b_folder)
        head.addWidget(b_refresh)
        head.addStretch()
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(12)

        # 左：库
        left = make_card()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 12, 14, 12)
        lv.setSpacing(8)
        self.lb_count = QLabel("音乐库")
        self.lb_count.setObjectName("SectionTitle")
        lv.addWidget(self.lb_count)
        self.list = QListWidget()
        self.list.setObjectName("Plain")
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setAlternatingRowColors(False)
        self.list.itemDoubleClicked.connect(lambda _: self.play_selected())
        self.list.currentRowChanged.connect(self._on_select)
        lv.addWidget(self.list, 1)
        body.addWidget(left, 3)

        # 右：播放器 + 编辑
        right = QVBoxLayout()
        right.setSpacing(12)

        # 播放器
        player_card = make_card()
        pv = QVBoxLayout(player_card)
        pv.setContentsMargins(18, 14, 18, 16)
        pv.setSpacing(10)
        pv.addWidget(QLabel("播放器", objectName="SectionTitle"))
        self.lb_now = QLabel("未选择曲目")
        self.lb_now.setObjectName("Strong")
        pv.addWidget(self.lb_now)

        row_prog = QHBoxLayout()
        self.lb_cur = QLabel("00:00")
        self.lb_cur.setFixedWidth(52)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self._seek)
        self.lb_dur = QLabel("00:00")
        self.lb_dur.setFixedWidth(52)
        row_prog.addWidget(self.lb_cur)
        row_prog.addWidget(self.slider, 1)
        row_prog.addWidget(self.lb_dur)
        pv.addLayout(row_prog)

        row_ctl = QHBoxLayout()
        row_ctl.setSpacing(8)
        b_prev = QPushButton("⏮")
        b_prev.setFixedWidth(52)
        b_prev.clicked.connect(self.play_prev)
        self.b_play = QPushButton("▶ 播放")
        self.b_play.setObjectName("Primary")
        self.b_play.clicked.connect(self.toggle_play)
        b_stop = QPushButton("■ 停止")
        b_stop.clicked.connect(self.stop)
        b_next = QPushButton("⏭")
        b_next.setFixedWidth(52)
        b_next.clicked.connect(self.play_next)
        self.cb_loop = QComboBox()
        self.cb_loop.addItems(["顺序播放", "列表循环", "单曲循环"])
        self.cb_loop.setCurrentIndex(1 if get_setting("loop_mode", "1") == "1" else 0)
        row_ctl.addWidget(b_prev)
        row_ctl.addWidget(self.b_play, 1)
        row_ctl.addWidget(b_stop)
        row_ctl.addWidget(b_next)
        row_ctl.addWidget(self.cb_loop)
        pv.addLayout(row_ctl)

        row_vol = QHBoxLayout()
        row_vol.addWidget(QLabel("音量"))
        self.sl_vol = QSlider(Qt.Horizontal)
        self.sl_vol.setRange(0, 100)
        self.sl_vol.setValue(70)
        self.sl_vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        row_vol.addWidget(self.sl_vol, 1)
        pv.addLayout(row_vol)
        right.addWidget(player_card)

        # 编辑
        edit_card = make_card()
        ev = QVBoxLayout(edit_card)
        ev.setContentsMargins(18, 14, 18, 16)
        ev.setSpacing(8)
        ev.addWidget(QLabel("音频剪辑（裁剪 / 变速 / 淡入淡出 / 拼接）", objectName="SectionTitle"))
        self.lb_src = QLabel("剪辑对象：未选择（在上方列表选择一首曲目）")
        self.lb_src.setObjectName("SubTitle")
        ev.addWidget(self.lb_src)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("裁剪起止（秒）"), 0, 0)
        self.sp_start = QDoubleSpinBox()
        self.sp_start.setRange(0, 99999)
        self.sp_start.setDecimals(1)
        self.sp_start.setSuffix(" s")
        self.sp_end = QDoubleSpinBox()
        self.sp_end.setRange(0, 99999)
        self.sp_end.setDecimals(1)
        self.sp_end.setSuffix(" s")
        row = QHBoxLayout()
        row.addWidget(self.sp_start)
        row.addWidget(QLabel("→"))
        row.addWidget(self.sp_end)
        grid.addLayout(row, 0, 1)

        grid.addWidget(QLabel("变速"), 1, 0)
        self.sp_speed = QDoubleSpinBox()
        self.sp_speed.setRange(0.5, 2.0)
        self.sp_speed.setSingleStep(0.1)
        self.sp_speed.setValue(1.0)
        self.sp_speed.setDecimals(1)
        self.sp_speed.setSuffix(" x")
        grid.addWidget(self.sp_speed, 1, 1)

        grid.addWidget(QLabel("淡入 / 淡出（秒）"), 2, 0)
        self.sp_fi = QDoubleSpinBox()
        self.sp_fi.setRange(0, 10)
        self.sp_fi.setDecimals(1)
        self.sp_fi.setSuffix(" s")
        self.sp_fo = QDoubleSpinBox()
        self.sp_fo.setRange(0, 10)
        self.sp_fo.setDecimals(1)
        self.sp_fo.setSuffix(" s")
        row2 = QHBoxLayout()
        row2.addWidget(self.sp_fi)
        row2.addWidget(QLabel("/"))
        row2.addWidget(self.sp_fo)
        grid.addLayout(row2, 2, 1)
        ev.addLayout(grid)

        row_btns = QHBoxLayout()
        b_mark_start = QPushButton("起点=当前播放位置")
        b_mark_start.clicked.connect(self._mark_start)
        b_export = QPushButton("导出剪辑 WAV")
        b_export.setObjectName("Primary")
        b_export.clicked.connect(self.export_edit)
        row_btns.addWidget(b_mark_start)
        row_btns.addWidget(b_export)
        row_btns.addStretch()
        ev.addLayout(row_btns)

        # 拼接
        ev.addWidget(QLabel("拼接队列（按顺序合并）", objectName="SmallTitle"))
        self.concat_ui = QListWidget()
        self.concat_ui.setObjectName("Plain")
        self.concat_ui.setFixedHeight(88)
        ev.addWidget(self.concat_ui)
        row_concat = QHBoxLayout()
        b_cadd = QPushButton("加入当前曲目")
        b_cadd.clicked.connect(self.concat_add)
        b_cdel = QPushButton("移除选中")
        b_cdel.clicked.connect(self.concat_del)
        b_cclear = QPushButton("清空队列")
        b_cclear.clicked.connect(self.concat_clear)
        b_cgo = QPushButton("导出拼接 WAV")
        b_cgo.setObjectName("Primary")
        b_cgo.clicked.connect(self.concat_export)
        row_concat.addWidget(b_cadd)
        row_concat.addWidget(b_cdel)
        row_concat.addWidget(b_cclear)
        row_concat.addWidget(b_cgo)
        ev.addLayout(row_concat)
        right.addWidget(edit_card, 1)
        body.addLayout(right, 4)
        lay.addLayout(body, 1)

        self.lb_status = QLabel("")
        self.lb_status.setObjectName("SubTitle")
        lay.addWidget(self.lb_status)

    # ---------- 库 ----------
    def music_dir(self):
        d = get_setting("music_dir", "") or os.path.join(data_dir(), "music")
        os.makedirs(d, exist_ok=True)
        return d

    def scan_library(self):
        self.list.clear()
        self.playlist = []
        d = self.music_dir()
        files = []
        for root, _, fns in os.walk(d):
            for fn in fns:
                if fn.lower().endswith(AUDIO_EXTS):
                    files.append(os.path.join(root, fn))
        files.sort()
        for f in files:
            self.playlist.append(f)
            item = QListWidgetItem("♪  " + os.path.basename(f))
            item.setToolTip(f)
            self.list.addItem(item)
        self.lb_count.setText(f"音乐库 · {len(files)} 首")
        self.lb_status.setText(f"音乐库目录：{d}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "添加音乐", "",
            "音频文件 (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.wma)")
        if not files:
            return
        d = self.music_dir()
        import shutil
        for f in files:
            try:
                dst = os.path.join(d, os.path.basename(f))
                if os.path.abspath(f) != os.path.abspath(dst):
                    shutil.copy2(f, dst)
            except Exception as e:
                logger.warning("复制音乐失败: %s %s", f, e)
        self.scan_library()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择音乐文件夹", self.music_dir())
        if not folder:
            return
        d = self.music_dir()
        import shutil
        for fn in os.listdir(folder):
            p = os.path.join(folder, fn)
            if os.path.isfile(p) and fn.lower().endswith(AUDIO_EXTS):
                try:
                    dst = os.path.join(d, fn)
                    if os.path.abspath(p) != os.path.abspath(dst):
                        shutil.copy2(p, dst)
                except Exception:
                    pass
        self.scan_library()

    def _on_select(self, row):
        if 0 <= row < len(self.playlist):
            f = self.playlist[row]
            self.editing_src = f
            self.lb_src.setText(f"剪辑对象：{os.path.basename(f)}")
            self.lb_now.setText(os.path.basename(f))
            self.sp_start.setValue(0)
            self.sp_end.setValue(0)

    # ---------- 播放 ----------
    def play_selected(self):
        row = self.list.currentRow()
        if row < 0 and self.playlist:
            row = 0
        if row < 0 or row >= len(self.playlist):
            return
        self.current_idx = row
        f = self.playlist[row]
        self.player.setSource(QUrl.fromLocalFile(f))
        self.player.play()
        self.b_play.setText("⏸ 暂停")
        self.lb_now.setText(os.path.basename(f))
        self.editing_src = f
        self.lb_src.setText(f"剪辑对象：{os.path.basename(f)}")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.b_play.setText("▶ 继续")
        else:
            if not self.player.source() or self.player.source().isEmpty():
                self.play_selected()
            else:
                self.player.play()
                self.b_play.setText("⏸ 暂停")

    def stop(self):
        self.player.stop()
        self.b_play.setText("▶ 播放")
        self.slider.setValue(0)
        self.lb_cur.setText("00:00")

    def play_prev(self):
        if not self.playlist:
            return
        self.list.setCurrentRow((self.current_idx - 1) % len(self.playlist))
        self.play_selected()

    def play_next(self):
        if not self.playlist:
            return
        self.list.setCurrentRow((self.current_idx + 1) % len(self.playlist))
        self.play_selected()

    def _seek(self, v):
        self.player.setPosition(v)

    def _on_pos(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.lb_cur.setText(_fmt_time(pos))

    def _on_dur(self, dur):
        self.slider.setRange(0, max(dur, 1))
        self.lb_dur.setText(_fmt_time(dur))

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            mode = self.cb_loop.currentText()
            if mode == "单曲循环":
                self.player.setPosition(0)
                self.player.play()
            elif mode == "列表循环":
                self.play_next()
            else:
                if self.current_idx + 1 < len(self.playlist):
                    self.play_next()
                else:
                    self.stop()

    # ---------- 编辑 ----------
    def _mark_start(self):
        self.sp_start.setValue(self.player.position() / 1000.0)

    def export_edit(self):
        if not self.editing_src or not os.path.exists(self.editing_src):
            QMessageBox.information(self, "提示", "请先在左侧列表选择一首曲目")
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "导出剪辑结果",
            os.path.join(self.music_dir(), "剪辑_" + os.path.basename(self.editing_src).rsplit(".", 1)[0] + ".wav"),
            "WAV 音频 (*.wav)")
        if not out:
            return
        kw = {"src": self.editing_src, "out": out,
              "start": self.sp_start.value(), "end": self.sp_end.value(),
              "speed": self.sp_speed.value(),
              "fade_in": self.sp_fi.value(), "fade_out": self.sp_fo.value()}
        self._start_worker("edit", kw)

    def concat_add(self):
        if not self.editing_src or not os.path.exists(self.editing_src):
            QMessageBox.information(self, "提示", "请先在左侧选择曲目")
            return
        self.concat_list.append(self.editing_src)
        self.concat_ui.addItem("♪ " + os.path.basename(self.editing_src))

    def concat_del(self):
        row = self.concat_ui.currentRow()
        if row >= 0:
            self.concat_ui.takeItem(row)
            self.concat_list.pop(row)

    def concat_clear(self):
        self.concat_ui.clear()
        self.concat_list = []

    def concat_export(self):
        if len(self.concat_list) < 1:
            QMessageBox.information(self, "提示", "拼接队列为空")
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "导出拼接结果",
            os.path.join(self.music_dir(), "拼接结果.wav"), "WAV 音频 (*.wav)")
        if not out:
            return
        self._start_worker("concat", {"paths": list(self.concat_list), "out": out})

    def _start_worker(self, op, kw):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "处理中", "上一次音频处理还没完成，请稍候")
            return
        self.lb_status.setText("正在处理音频…（首次处理较长曲目需要几秒钟）")
        self.worker = AudioWorker(op, kw)
        self.worker.done.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, ok, msg):
        self.lb_status.setText("")
        if ok:
            QMessageBox.information(self, "处理完成", f"已导出：\n{msg}")
            logger.info("音频导出: %s", msg)
        else:
            QMessageBox.critical(self, "处理失败", msg)


# ============================================================
#  设置页
# ============================================================
ACCENTS = {
    "香槟金": "#C9A86A",
    "冷银": "#AEB6C4",
    "玫瑰金": "#D4A0A8",
}


# -*- coding: utf-8 -*-
class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.load_values()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 12, 12)
        lay.setSpacing(12)

        title = QLabel("设置")
        title.setObjectName("Title")
        lay.addWidget(title)

        # 常规
        card1 = make_card()
        v1 = QVBoxLayout(card1)
        v1.setContentsMargins(20, 16, 20, 18)
        v1.setSpacing(10)
        v1.addWidget(QLabel("常规", objectName="SectionTitle"))
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(12)
        g.addWidget(QLabel("界面主题风格"), 0, 0)
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(theme.theme_names())
        self.cb_theme.setMinimumWidth(200)
        self.cb_theme.currentTextChanged.connect(self._preview_theme)
        g.addWidget(self.cb_theme, 0, 1)
        tp = QLabel("选择后立即生效，无需重启")
        tp.setObjectName("SubTitle")
        g.addWidget(tp, 0, 2)
        g.addWidget(QLabel("工作台名称"), 1, 0)
        self.ed_appname = QLineEdit()
        self.ed_appname.setPlaceholderText("显示在窗口标题与左上角，如：鹏飞婚礼工作台")
        self.ed_appname.setMinimumWidth(200)
        g.addWidget(self.ed_appname, 1, 1, 1, 2)
        v1.addLayout(g)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(14)
        g2.setVerticalSpacing(12)
        g2.addWidget(QLabel("备忘提示铃声"), 0, 0)
        self.cb_sound = QComboBox()
        self.cb_sound.addItem("关闭提示音", "0")
        self.cb_sound.addItem("系统提示音（叮）", "1")
        self.cb_sound.addItem("铃声一 · 叮咚双音", "ring1")
        self.cb_sound.addItem("铃声二 · 三音上扬", "ring2")
        self.cb_sound.addItem("铃声三 · 双短促", "ring3")
        self.cb_sound.setMinimumWidth(200)
        g2.addWidget(self.cb_sound, 0, 1)
        b_preview = QPushButton("试听")
        b_preview.setFixedWidth(76)
        b_preview.clicked.connect(self.preview_sound)
        g2.addWidget(b_preview, 0, 2)
        b_custom = QPushButton("自定义铃声…")
        b_custom.clicked.connect(self.pick_sound)
        g2.addWidget(b_custom, 0, 3)
        v1.addLayout(g2)

        self.chk_minimize = QCheckBox("关闭窗口时最小化到系统托盘（不勾选则直接退出）")
        v1.addWidget(self.chk_minimize)
        lay.addWidget(card1)

        # 目录
        card2 = make_card()
        v2 = QVBoxLayout(card2)
        v2.setContentsMargins(20, 16, 20, 18)
        v2.setSpacing(10)
        v2.addWidget(QLabel("目录", objectName="SectionTitle"))
        rowm = QHBoxLayout()
        rowm.addWidget(QLabel("音乐库目录"))
        self.ed_music = QLineEdit()
        self.ed_music.setReadOnly(True)
        b_m = QPushButton("选择…")
        b_m.clicked.connect(self.pick_music_dir)
        rowm.addWidget(self.ed_music, 1)
        rowm.addWidget(b_m)
        v2.addLayout(rowm)
        rowb = QHBoxLayout()
        rowb.addWidget(QLabel("备份目录"))
        self.ed_backup = QLineEdit()
        self.ed_backup.setReadOnly(True)
        b_b = QPushButton("选择…")
        b_b.clicked.connect(self.pick_backup_dir)
        rowb.addWidget(self.ed_backup, 1)
        rowb.addWidget(b_b)
        v2.addLayout(rowb)
        tip = QLabel("提示：备份目录默认 D:\\主持人工作台；如果它在百度网盘的同步范围内，备份会随网盘自动上传。")
        tip.setObjectName("SubTitle")
        tip.setWordWrap(True)
        v2.addWidget(tip)
        lay.addWidget(card2)

        # 音乐播放
        card3 = make_card()
        v3 = QVBoxLayout(card3)
        v3.setContentsMargins(20, 16, 20, 18)
        v3.setSpacing(10)
        v3.addWidget(QLabel("音乐播放", objectName="SectionTitle"))
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("默认音量"))
        self.sl_vol = QSlider(Qt.Horizontal)
        self.sl_vol.setRange(0, 100)
        row3.addWidget(self.sl_vol, 1)
        self.lb_vol = QLabel("70%")
        self.lb_vol.setFixedWidth(60)
        self.sl_vol.valueChanged.connect(lambda v: self.lb_vol.setText(f"{v}%"))
        row3.addWidget(self.lb_vol)
        v3.addLayout(row3)
        self.chk_loop = QCheckBox("默认列表循环")
        v3.addWidget(self.chk_loop)
        lay.addWidget(card3)

        # AI 模型
        card4 = make_card()
        v4 = QVBoxLayout(card4)
        v4.setContentsMargins(20, 16, 20, 18)
        v4.setSpacing(8)
        v4.addWidget(QLabel("主持助理模型", objectName="SectionTitle"))
        row4 = QHBoxLayout()
        self.lb_ai = QLabel("未连接")
        self.lb_ai.setStyleSheet("color:#8D919B;")
        row4.addWidget(self.lb_ai, 1)
        b_ai = QPushButton("打开连接设置…")
        b_ai.clicked.connect(self.open_ai_connect)
        row4.addWidget(b_ai)
        v4.addLayout(row4)
        tip4 = QLabel("支持 DeepSeek 官方 API / 本机 Ollama / 任意 OpenAI 兼容接口；"
                      "主持助理页的对话、台词与创意都使用同一套连接。")
        tip4.setObjectName("SubTitle")
        tip4.setWordWrap(True)
        v4.addWidget(tip4)
        lay.addWidget(card4)

        # 图片素材
        card5 = make_card()
        v5 = QVBoxLayout(card5)
        v5.setContentsMargins(20, 16, 20, 18)
        v5.setSpacing(8)
        v5.addWidget(QLabel("文字生图（图文设计用）", objectName="SectionTitle"))
        row5a = QHBoxLayout()
        row5a.addWidget(QLabel("生图渠道"))
        self.cb_img_provider = QComboBox()
        self.cb_img_provider.addItem("Hugging Face · FLUX.1-schnell（免费，无需 Key）", "hf")
        self.cb_img_provider.addItem("Pollinations · 免费（无需 Key，备用）", "pollinations")
        self.cb_img_provider.addItem("智谱 CogView-3-Flash · 免费额度（需 Key）", "zhipu")
        self.cb_img_provider.addItem("豆包 Seedream · 火山方舟（需 Key）", "doubao")
        self.cb_img_provider.addItem("自定义 OpenAI 兼容接口", "custom")
        self.cb_img_provider.currentIndexChanged.connect(self._sync_img_provider)
        row5a.addWidget(self.cb_img_provider, 1)
        v5.addLayout(row5a)
        row5b = QHBoxLayout()
        row5b.addWidget(QLabel("生图接口地址"))
        self.ed_img_base = QLineEdit()
        self.ed_img_base.setPlaceholderText("如 https://dashscope.aliyuncs.com/api/v1 或 OpenAI 兼容地址")
        row5b.addWidget(self.ed_img_base, 1)
        v5.addLayout(row5b)
        row5c = QHBoxLayout()
        row5c.addWidget(QLabel("生图 Key"))
        self.ed_img_key = QLineEdit()
        self.ed_img_key.setEchoMode(QLineEdit.Password)
        row5c.addWidget(self.ed_img_key, 1)
        row5c.addWidget(QLabel("模型"))
        self.ed_img_model = QLineEdit()
        self.ed_img_model.setPlaceholderText("如 qwen-image")
        self.ed_img_model.setFixedWidth(160)
        row5c.addWidget(self.ed_img_model)
        v5.addLayout(row5c)
        tip5 = QLabel("默认用 Pollinations 免费接口（无需 Key，可能较慢）；"
                      "也可以切换成自己的 OpenAI 兼容接口。")
        tip5.setObjectName("SubTitle")
        tip5.setWordWrap(True)
        v5.addWidget(tip5)
        lay.addWidget(card5)

        # 数据与备份
        card6 = make_card()
        v6 = QVBoxLayout(card6)
        v6.setContentsMargins(20, 16, 20, 18)
        v6.setSpacing(8)
        v6.addWidget(QLabel("数据与备份", objectName="SectionTitle"))
        row6 = QHBoxLayout()
        b_export = QPushButton("导出加密备份")
        b_export.clicked.connect(self.export_backup_now)
        b_import = QPushButton("恢复备份")
        b_import.clicked.connect(self.restore_backup_now)
        b_open = QPushButton("打开数据目录")
        b_open.clicked.connect(lambda: common.open_path(data_dir()))
        row6.addWidget(b_export)
        row6.addWidget(b_import)
        row6.addWidget(b_open)
        row6.addStretch()
        v6.addLayout(row6)
        lay.addWidget(card6)

        row_save = QHBoxLayout()
        b_save = QPushButton("保存设置")
        b_save.setObjectName("Primary")
        b_save.setFixedWidth(160)
        b_save.clicked.connect(self.save)
        row_save.addWidget(b_save)
        row_save.addStretch()
        lay.addLayout(row_save)
        lay.addStretch()

    def load_values(self):
        self.cb_theme.setCurrentText(get_setting("theme", "暗夜金"))
        self.ed_appname.setText(get_setting("workbench_name", "主持人工作台"))
        cur = get_setting("memo_sound", "1")
        idx = self.cb_sound.findData(cur)
        if idx < 0:
            idx = self.cb_sound.findData("1")
        self.cb_sound.setCurrentIndex(max(0, idx))
        self.chk_minimize.setChecked(get_setting("minimize_tray", "0") == "1")
        self.ed_music.setText(get_setting("music_dir", "") or os.path.join(data_dir(), "music"))
        self.ed_backup.setText(get_setting("backup_dir", "") or common.default_backup_dir())
        try:
            self.sl_vol.setValue(int(get_setting("music_volume", "70")))
        except Exception:
            self.sl_vol.setValue(70)
        self.chk_loop.setChecked(get_setting("loop_mode", "1") == "1")
        base = get_setting("ai_base_url", "")
        model = get_setting("ai_model", "") or "deepseek-chat"
        self.lb_ai.setText(f"已连接：{model}  ·  {base}" if base else "未连接（在「主持助理」页右上角配置）")
        self.ed_img_base.setText(get_setting("img_base_url", ""))
        self.ed_img_key.setText(get_setting("img_api_key", ""))
        self.ed_img_model.setText(get_setting("img_model", ""))
        idxp = self.cb_img_provider.findData(get_setting("img_provider", "hf"))
        self.cb_img_provider.setCurrentIndex(max(0, idxp))
        self._sync_img_provider()

    def _sync_img_provider(self):
        prov = self.cb_img_provider.currentData() or "hf"
        custom = prov == "custom"
        need = prov not in ("pollinations", "hf")
        for w in (getattr(self, "ed_img_key", None), getattr(self, "ed_img_model", None)):
            if w is not None:
                w.setEnabled(need)
        if hasattr(self, "ed_img_base"):
            self.ed_img_base.setEnabled(custom)
            if prov == "zhipu":
                self.ed_img_base.setText("https://open.bigmodel.cn/api/paas/v4")
                if hasattr(self, "ed_img_model") and not self.ed_img_model.text().strip():
                    self.ed_img_model.setText("cogview-3-flash")
            elif prov == "doubao":
                self.ed_img_base.setText("https://ark.cn-beijing.volces.com/api/v3")
                if hasattr(self, "ed_img_model") and not self.ed_img_model.text().strip():
                    self.ed_img_model.setText("doubao-seedream-3-0-t2i-250415")
            self.ed_img_base.setPlaceholderText(
                "如 https://dashscope.aliyuncs.com/api/v1 或 OpenAI 兼容地址" if custom
                else "该渠道地址已内置，无需填写")

    def open_ai_connect(self):
        try:
            from pages_misc import ConnectDialog
            dlg = ConnectDialog(common._shared(), self)
            if dlg.exec():
                self.load_values()
        except Exception as e:
            QMessageBox.warning(self, "无法打开", str(e))

    # ---------- 铃声 ----------
    def preview_sound(self):
        val = self.cb_sound.currentData() or "1"
        if val == "0":
            QMessageBox.information(self, "提示", "当前设置为关闭提示音")
            return
        if val in ("1", "beep"):
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            return
        path = val
        if val in ("ring1", "ring2", "ring3"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "assets", "sounds", val + ".wav")
        if not os.path.exists(path):
            QMessageBox.warning(self, "提示", "铃声文件不存在")
            return
        from PySide6.QtMultimedia import QSoundEffect
        from PySide6.QtCore import QUrl
        if getattr(self, "_pre", None) is None:
            self._pre = QSoundEffect(self)
            self._pre.setVolume(0.9)
        self._pre.setSource(QUrl.fromLocalFile(path))
        self._pre.play()

    def pick_sound(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择提示铃声", "",
                                           "音频文件 (*.wav *.mp3 *.ogg *.m4a)")
        if not f:
            return
        if self.cb_sound.findData(f) < 0:
            self.cb_sound.addItem("自定义：" + os.path.basename(f), f)
        self.cb_sound.setCurrentIndex(self.cb_sound.findData(f))

    def pick_music_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择音乐库目录", self.ed_music.text())
        if d:
            self.ed_music.setText(d)

    def pick_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择备份目录", self.ed_backup.text())
        if d:
            self.ed_backup.setText(d)

    # ---------- 备份 ----------
    def export_backup_now(self):
        from PySide6.QtWidgets import QInputDialog
        pwd, ok = QInputDialog.getText(self, "导出加密备份", "设置备份密码：", QLineEdit.Password)
        if not ok or not pwd:
            return
        out_dir = self.ed_backup.text() or common.default_backup_dir()
        os.makedirs(out_dir, exist_ok=True)
        name = "档期备份_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M") + ".fhbackup"
        path = os.path.join(out_dir, name)
        try:
            common.export_backup(pwd, path)
            QMessageBox.information(self, "备份成功", f"已导出：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def restore_backup_now(self):
        from PySide6.QtWidgets import QInputDialog
        path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", self.ed_backup.text() or data_dir(),
                                              "备份文件 (*.fhbackup)")
        if not path:
            return
        pwd, ok = QInputDialog.getText(self, "恢复备份", "请输入备份密码：", QLineEdit.Password)
        if not ok or not pwd:
            return
        if common.import_backup(path, pwd):
            QMessageBox.information(self, "恢复成功", "备份已恢复，请重新打开应用生效。")
        else:
            QMessageBox.warning(self, "恢复失败", "密码错误或备份文件损坏。")

    def _preview_theme(self, name):
        """下拉框选择后立即应用并记住，不必再点保存。"""
        if not name:
            return
        try:
            set_setting("theme", name)
            win = self.window()
            if hasattr(win, "apply_theme"):
                win.apply_theme(name)
        except Exception:
            logger.exception("即时切换主题失败")

    def save(self):
        set_setting("theme", self.cb_theme.currentText())
        set_setting("workbench_name", self.ed_appname.text().strip() or "主持人工作台")
        set_setting("memo_sound", self.cb_sound.currentData() or "1")
        set_setting("minimize_tray", "1" if self.chk_minimize.isChecked() else "0")
        set_setting("music_dir", self.ed_music.text())
        set_setting("backup_dir", self.ed_backup.text())
        set_setting("music_volume", str(self.sl_vol.value()))
        set_setting("loop_mode", "1" if self.chk_loop.isChecked() else "0")
        prov = self.cb_img_provider.currentData() or "hf"
        base = self.ed_img_base.text().strip()
        model = self.ed_img_model.text().strip()
        if prov == "zhipu":
            base = base or "https://open.bigmodel.cn/api/paas/v4"
            model = model or "cogview-3-flash"
        elif prov == "doubao":
            base = base or "https://ark.cn-beijing.volces.com/api/v3"
            model = model or "doubao-seedream-3-0-t2i-250415"
        set_setting("img_provider", prov)
        set_setting("img_base_url", base)
        set_setting("img_api_key", self.ed_img_key.text().strip())
        set_setting("img_model", model)
        win = self.window()
        if hasattr(win, "apply_theme"):
            win.apply_theme(self.cb_theme.currentText())
        if hasattr(win, "apply_name"):
            win.apply_name(self.ed_appname.text().strip() or "主持人工作台")
        QMessageBox.information(self, "已保存", "设置已保存，主题已即时生效。")

