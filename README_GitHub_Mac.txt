# 主持人工作台 Mac 版 · GitHub Actions 打包

1. 在 GitHub 新建一个空仓库（Private/Public 都行）。
2. 把本文件夹里的所有文件上传到仓库根目录（保留 .github 文件夹）。
3. 进入仓库 → Actions → 左侧「Build macOS App」→ Run workflow。
4. 等 5–10 分钟，在运行记录底部下载：
   - 主持人工作台-macOS-arm64.zip（Apple 芯片 M1/M2/M3）
   - 主持人工作台-macOS-x64.zip（Intel Mac）
5. 解压得到「主持人工作台.app」，拖进“应用程序”。
6. 首次打开若提示未验证：右键 → 打开，或终端执行：
   xattr -dr com.apple.quarantine /Applications/主持人工作台.app

说明：
- 这是未签名包，能运行，但没有 Apple 开发者签名/公证；
- 授权：首次启动显示 Mac 机器码，用 Windows 上的「授权生成器」生成 license.lic 导入；
- 全局快捷键、Windows 提示音等 Windows 专属功能在 Mac 上不可用。
