# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.datastruct import Tree

windows = sys.platform == 'win32'
mac = sys.platform == 'darwin'
if not (windows or mac):
    raise SystemExit('Use Windows x64 or macOS arm64 to build this release.')

datas = []
binaries = []
# Use the platform-native executable from the imageio-ffmpeg wheel.
from imageio_ffmpeg import get_ffmpeg_exe
ffmpeg = get_ffmpeg_exe()
if not os.path.isabs(ffmpeg) or not os.path.exists(ffmpeg):
    raise SystemExit('Install the imageio-ffmpeg wheel before building.')
binaries.append((ffmpeg, 'assets'))

hiddenimports = collect_submodules('mutagen')
if mac:
    hiddenimports += ['mac_remote', 'AppKit', 'Quartz', 'MediaPlayer', 'objc', 'ApplicationServices']
    # PyObjC framework modules need their dylibs/data, not just the Python shim.
    from PyInstaller.utils.hooks import collect_all
    for _pkg in ('MediaPlayer', 'AppKit', 'Quartz', 'ApplicationServices', 'Foundation', 'objc'):
        try:
            _datas, _binaries, _hidden = collect_all(_pkg)
            datas += _datas
            binaries += _binaries
            hiddenimports += _hidden
        except Exception:
            pass
a = Analysis(
    ['app.py'], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=['tkinter'], noarchive=False,
)
a.binaries = [
    ('assets/ffmpeg.exe' if windows else 'assets/ffmpeg', src, kind)
    if src == ffmpeg and dst.startswith('assets/') else (dst, src, kind)
    for dst, src, kind in a.binaries
]
a.datas += Tree('assets', prefix='assets', excludes=['ffmpeg.exe', 'ffmpeg'])
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='HostWorkbench',
    console=False, upx=False, icon='assets/icon.ico' if windows else 'assets/icon.png',
    target_arch='arm64' if mac else None,
    codesign_identity=os.environ.get('HOST_WORKBENCH_CODESIGN_IDENTITY') or None,
)
dist = COLLECT(exe, a.binaries, a.datas, name='HostWorkbench', upx=False)
if mac:
    app = BUNDLE(
        dist, name='HostWorkbench.app', icon='assets/icon.png',
        bundle_identifier='com.hostworkbench.desktop',
        version='5.0',
        info_plist={'CFBundleDisplayName': '主持人工作台'},
    )
