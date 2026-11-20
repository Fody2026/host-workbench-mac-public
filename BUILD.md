# 主持人工作台 v5.0 修订源码

从 Windows v5.0 源码更新。保留原版本号与授权校验，以兼容同一机器上原有的 v5.0 授权规则。Mac 版以此工程重新构建，原 Mac 包的机器码、应用标识和数据目录尚未核对。升级前先备份原应用内的数据。

## 构建

在对应系统的项目目录里使用 Python 3.12。Windows 使用 x64 Python，Mac 使用 Apple 芯片原生 arm64 Python。

```text
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --noconfirm HostWorkbench.spec
```

- Windows 运行 `dist/HostWorkbench/HostWorkbench.exe`。分发时压缩整个 `dist/HostWorkbench` 目录。
- macOS 生成 `dist/HostWorkbench.app`。使用 `ditto -c -k --keepParent dist/HostWorkbench.app HostWorkbench-macOS-arm64.zip` 压缩。面向他人发布时，使用 Developer ID 签名并完成 Apple 公证。构建脚本可读取 `HOST_WORKBENCH_CODESIGN_IDENTITY`。
- 构建会打入 imageio-ffmpeg 提供的对应平台 FFmpeg。原包附带的 Windows FFmpeg 可执行文件无需另行复制。
- PyInstaller 使用本机目标系统。Linux 上完成源码检查后，仍需分别执行 Windows 和 macOS 构建。

## 现场验证

1. 在工作台设置中选择「冰蓝」。新安装默认使用此主题，已有主题选择可在设置中切换。
2. N61 接收器切到模式 1。进入「音乐播放器 → 快捷键设置」打开「演出模式」。在 Mac 上允许工作台使用「辅助功能」权限后重启。若系统另提示「输入监控」，按系统提示授权。
3. 在工作台载入至少两首曲目，逐个验证播放、暂停、上一首、下一首和调音量。媒体传输按键进入工作台，音量仍由系统处理。
4. 同时打开其他播放器，切换前台和后台，反复验证按一次只触发一次。再关闭演出模式，检查其他播放器恢复接收媒体键。系统按键分发取决于当前会话和软件权限。
5. 其他遥控器若发送普通键盘键，在快捷键设置中录入并勾选「全局」。macOS 上的全局普通按键需要开启演出模式，按 ANSI 物理键位注册。全局普通按键会在其他应用里被截取，建议绑定遥控器的专用按键，避免占用日常打字键。
6. 在低内存机器上冷启动后依次打开工作台、音乐、图文和预演页，检查中文标签、按钮和播放状态以及运行时内存。页面在首次访问时加载，软件在识别为低内存时关闭导航动画。

当前版本已在 Windows x64 完成原生构建、安装包安装、逐页自检与 Windows 媒体键钩子模拟；macOS 原生构建、签名、真实遥控器及多播放器竞争仍需在 Mac 真机验证。


## Apple 芯片 Mac 构建与核对

在 Apple 芯片 Mac 上先确认使用 arm64 Python，而不是 Rosetta 的 x64 Python：

```bash
python3 -c "import platform; print(platform.machine())"   # 必须输出 arm64
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --clean --noconfirm HostWorkbench.spec
ditto -c -k --keepParent dist/HostWorkbench.app HostWorkbench-macOS-arm64.zip
```

产物是 `dist/HostWorkbench.app`，Bundle ID 为 `com.hostworkbench.desktop`，版本 5.0。若要分发，先设置 `HOST_WORKBENCH_CODESIGN_IDENTITY` 再构建，并用 `codesign --verify --deep --strict` 与 `spctl --assess` 检查。

### Mac 数据目录与旧包兼容

新包数据目录：`~/Library/Application Support/HostWorkbench/data`。首次启动如果新目录不存在，会依次尝试旧目录：`~/Library/Application Support/FuyaoHostTool/data`、`~/AppData/Local/HostWorkbench/data`、`~/Library/Application Support/主持人工作台/data`。旧 Mac 包的实际数据目录、机器码算法如果与上述不同，升级前先手工备份整个旧数据目录；不要直接覆盖。

### Mac 遥控测试

1. 系统设置 → 隐私与安全性 → 辅助功能，允许主持人工作台；如出现输入监控提示也允许，然后重启应用。
2. 音乐播放器 → 快捷键设置，勾选「演出模式」，N61 接收器切模式 1，保存。
3. 用 N61 按播放/暂停、上一首、下一首各一次；再快速连按下一首三次；再长按播放键三秒。日志应只有按下事件，长按不重复，快速连按不合并。
4. 同时打开另一个播放器并切到前台，重复测试：工作台应响应，另一个播放器不应跟着动。关闭「演出模式」后另一个播放器应恢复接收。
5. 若失败，查看应用日志中的 `macOS 媒体键` / `媒体键动作` / `启动演出模式` 记录，区分权限、未收到事件、收到未执行三类问题。
