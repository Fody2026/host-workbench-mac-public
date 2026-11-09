主持人工作台 Mac 版 v4.8

一、直接运行（需要 Mac 已装 Python 3.10+）
1. 打开“终端”，进入本文件夹：
   cd ~/Desktop/主持人工作台_Mac_v4.8
2. 首次执行：
   chmod +x 启动.command 打包Mac版.sh
   xattr -dr com.apple.quarantine .
3. 双击“启动.command”，或终端执行：
   ./启动.command

二、打包成 .app
双击“打包Mac版.sh”，或在终端：
   ./打包Mac版.sh
生成的文件在 dist/主持人工作台.app

三、说明
- Windows 无法交叉编译 macOS 的 .app，所以这里提供源码+脚本，必须在 Mac 上打包；
- 首次安装 PySide6 约 200MB，需要网络；
- 若提示“无法打开，因为无法验证开发者”，右键 → 打开，或执行 xattr 命令；
- 授权：首次启动会显示 Mac 机器码，用“授权生成器”生成 license.lic 导入即可；
- 音乐、图文、备婚、预演等功能与 Windows 版一致；Windows 专属的全局热键在 Mac 上不可用。
