# 测试记录（v5.0 修订源码）

## Windows 构建与成品

- Python 3.12.10 x64，PyInstaller 6.22.3，PySide6 6.12.0。
- 目录版构建：`dist/HostWorkbench/HostWorkbench.exe`，约 436 MB（含平台 FFmpeg）。
- 安装包：Inno Setup 7 构建，静默安装到独立目录后启动自检通过。
- 成品自检：逐页截图、图文设计、沙盘 PNG、沙盘 MP4、PPTX、DOCX 均通过（`selftest.txt` 最后为 `OK`）。
- 安装版正常启动显示 `主持人工作台 v5.0`，旧 v5.0 授权可用。
- Windows 媒体键钩子模拟：发送 3 次 `VK_MEDIA_NEXT_TRACK`，回调收到 3 次 `next`，未合并。
- 未用真实 N61 在本机实测；需按 BUILD.md 的现场步骤验证接收器模式 1、后台和多个播放器竞争。

## Mac 分支（Windows 上静态/模拟）

- `python -m compileall` 全部通过；`mac_remote` 在 Windows 可导入且不依赖 AppKit 才可导入。
- `python -m unittest discover -s tests`：12 项全部通过。
- 覆盖 NX 媒体键解码（播放/上一首/下一首/松开/重复位/未知键）、一次按下只执行一次、长按重复被忽略、快速连按不被 0.28 秒防抖吞掉。
- `MacMediaKeyHook` 在 Windows 上明确报告缺少 Quartz，不会静默失败。
- Mac 构建配置：`HostWorkbench.spec` 使用 `target_arch='arm64'`、`BUNDLE`，`com.hostworkbench.desktop`；隐藏导入含 `mac_remote/AppKit/Quartz/MediaPlayer/objc/ApplicationServices`；`requirements-build.txt` 含三个 PyObjC 包。

## 仍需 Mac 真机验证

1. 辅助功能（以及如出现的输入监控）授权后，N61 播放/暂停、上一首、下一首是否进入工作台。
2. 长按只执行一次、快速连按连续切歌。
3. 工作台在后台、另一个播放器在前台时，另一个播放器不跟着动；关闭演出模式后恢复。
4. 自定义普通键盘遥控器的录入、保存、重启恢复和后台使用。
5. 音量仍由 macOS 系统处理。
6. 代码签名/公证后 Gatekeeper 首次启动。

## 旧 Mac 包信息

- 新 Bundle ID：`com.hostworkbench.desktop`，版本 5.0。
- 新数据目录：`~/Library/Application Support/HostWorkbench/data`。
- 旧包实际 Bundle ID、机器码算法、数据目录尚未核对；首次升级前请备份旧数据目录。
- `licensing.py` 的机器码在 Mac 上回退为 `uuid.getnode()` + 计算机名，与旧 Mac 包是否一致未确认。
