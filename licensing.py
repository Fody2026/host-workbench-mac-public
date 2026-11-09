# -*- coding: utf-8 -*-
"""离线授权：Ed25519 签名的 license.lic，绑定机器码与有效期"""
import base64
import ctypes
import datetime
import hashlib
import json
import os
import platform
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import common

PUBLIC_KEY_B64 = "/Nezn5FNB57Nzn0wiAzORHk0J+NnVIaLfynxchCYSbE="


def machine_code():
    """Windows 安装标识 + C 盘卷序列号 + 计算机名，重装系统/换机会变"""
    parts = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            parts.append(str(winreg.QueryValueEx(k, "MachineGuid")[0]))
    except Exception:
        parts.append(str(uuid.getnode()))
    try:
        vol = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"), None, 0, ctypes.byref(vol), None, None, None, 0)
        parts.append(str(vol.value))
    except Exception:
        pass
    parts.append(platform.node())
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20].upper()


def _license_path():
    return os.path.join(common.data_dir(), "license.lic")


def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_file(path):
    """返回 (ok, message, payload)"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        payload = data["payload"]
        sig = base64.b64decode(data["sig"])
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
        pub.verify(sig, _canonical(payload))
    except Exception:
        return False, "授权文件无效或已被篡改。", {}
    if payload.get("machine") != machine_code():
        return False, "该授权文件不是本机的（机器码不匹配）。", payload
    try:
        exp = datetime.date.fromisoformat(payload.get("expires", "1970-01-01"))
        if exp < datetime.date.today():
            return False, f"授权已于 {exp} 到期。", payload
    except Exception:
        return False, "授权有效期格式错误。", payload
    return True, "授权有效", payload


def is_licensed():
    path = _license_path()
    if not os.path.exists(path):
        return False
    ok, _msg, _p = verify_file(path)
    return ok


def license_payload():
    path = _license_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("payload", {})
    except Exception:
        return {}


class LicenseDialog(object):
    """导入授权文件；用函数形式避免循环导入 Qt 样式"""


def ensure_license(style_sheet=""):
    if is_licensed():
        return True
    from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                   QPushButton, QFileDialog, QMessageBox, QLineEdit)
    dlg = QDialog()
    dlg.setWindowTitle("软件授权")
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(26, 22, 26, 20)
    lay.setSpacing(12)
    title = QLabel("请导入本机授权文件")
    title.setObjectName("Title")
    lay.addWidget(title)
    tip = QLabel("把下面这串机器码发给作者，作者会生成专属 license.lic 发给你。\n"
                 "授权文件绑定本机，复制到其他电脑无效。")
    tip.setObjectName("SubTitle")
    tip.setWordWrap(True)
    lay.addWidget(tip)
    ed = QLineEdit(machine_code())
    ed.setReadOnly(True)
    ed.setCursorPosition(0)
    lay.addWidget(ed)
    row = QHBoxLayout()
    row.addStretch(1)
    b_quit = QPushButton("退出")
    b_quit.clicked.connect(dlg.reject)
    b_import = QPushButton("选择授权文件…")
    b_import.setObjectName("Primary")

    def do_import():
        path, _ = QFileDialog.getOpenFileName(dlg, "选择授权文件", "", "授权文件 (*.lic *.json);;所有文件 (*)")
        if not path:
            return
        ok, msg, _payload = verify_file(path)
        if not ok:
            QMessageBox.warning(dlg, "授权失败", msg)
            return
        try:
            import shutil
            shutil.copyfile(path, _license_path())
        except OSError as exc:
            QMessageBox.warning(dlg, "保存失败", str(exc))
            return
        dlg.accept()

    b_import.clicked.connect(do_import)
    row.addWidget(b_quit)
    row.addWidget(b_import)
    lay.addLayout(row)
    if style_sheet:
        dlg.setStyleSheet(style_sheet)
    return dlg.exec() == QDialog.Accepted
