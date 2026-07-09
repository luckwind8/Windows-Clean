# Windows-Clean

一个面向 Windows 的 AppData / 缓存清理小工具。当前版本基于 Python + Tkinter 编写，并使用 PyInstaller 打包为单文件 EXE。

## 快速使用

直接运行：

```text
dist\AppDataCleaner.exe
```

建议右键选择“以管理员身份运行”，这样才能处理部分系统缓存、高级清理项和其他用户目录。

## 主要功能

- 扫描并计算可清理项目占用空间。
- 勾选后清理，支持“推荐项全选”“全选/全不选”。
- 底部绿色进度条显示扫描/清理进度；清理时成功完成的条目会从列表中逐项消失，失败或跳过的条目会留下并显示状态。
- 清理日志输出到桌面：

```text
%USERPROFILE%\Desktop\AppDataCleaner_logs
```

- 默认保护登录态和站点数据，不清理：

```text
Cookies
Login Data
Local State
Local Storage
IndexedDB
Session Storage
Sessions
WebStorage
Network
Service Worker
Bookmarks
Preferences
Extensions
```

扫描规则按系统环境变量、`C:\Users\*` 用户目录、磁盘根目录特征和通用缓存目录名发现目标，不绑定本机用户名或固定软件安装位置。

运行中的 Codex 数据目录和当前清理器自身的 PyInstaller 解压目录会自动跳过，避免清理时把正在使用的文件扫入列表。

## 已覆盖的清理范围

- 用户临时目录：`AppData\Local\Temp`
- AppData 下常见缓存、日志、更新包、崩溃记录
- Chrome / Edge / 360 浏览器 / 360 极速浏览器 / 夸克 / 豆包 / 千问 / SPChrome 等 Chromium 系缓存
- Chromium / Electron 常见缓存名：`Cache`、`Code Cache`、`GPUCache`、`DawnWebGPUCache`、`DawnGraphiteCache`、`GraphiteDawnCache`、`image_cache`、`remote_resource_cache`
- WPS / 金山 Office 缓存、日志、更新包、备份缓存
- 百度网盘缓存
- 千牛 / 1688 CEF 缓存
- QQ NT、Cherry Studio、Adobe / Photoshop WebView 的渲染缓存和日志
- QQ 音乐磁盘缓存：会在各磁盘根目录查找 `QQMusicCache\Temp`、`QQMusicCache\downloadproxy*`
- npm / pip / NuGet / Gradle 等开发缓存，其中 Gradle 缓存默认不推荐勾选，避免下次构建大量重新下载
- 非系统空文件夹清理，例如空的 `AppData\Local\VirtualStore`
- 多用户扫描：会扫描 `C:\Users\*\AppData`，跳过 `Default`、`Public`、`All Users` 等模板/公共目录
- Photoshop 根目录临时缓存：如 `C:\Photoshop Temp*`、`D:\Photoshop Temp*`
- WDC 报告借鉴的通用 Windows 缓存/日志：
  - `AppData\Local\D3DSCache`
  - `AppData\LocalLow\Microsoft\CryptnetUrlCache`
  - Windows WebCache 的日志文件，不清理 WebCache 主数据库
  - OneDrive 安装日志
  - 开始菜单 `TileCache_*`
  - `C:\Windows\Temp`
  - CBS 归档日志 `CbsPersist_*`
  - WinSAT、USOShared、MoSetup、NetSetup、RecEnv_Ramdisk、SetupCleanupTask、SleepStudy 等日志
  - Windows Search `GatherLogs`，管理员权限下可见
  - Windows 字体缓存，默认不推荐勾选
- 系统高级项：
  - `C:\Windows\MEMORY.DMP`
  - `C:\Windows\LiveKernelReports\*.dmp`
  - `C:\Windows\Minidump\*.dmp`
  - `C:\Program Files\WindowsApps.tmp`
  - `C:\hiberfil.sys`，通过 `powercfg -h off`
  - WinSxS 组件存储，通过 `dism /online /Cleanup-Image /StartComponentCleanup`

## 强制关闭相关软件

界面里有复选框：

```text
清理前强制关闭相关软件（不关闭 Codex）
```

默认不勾选。勾选后，工具会根据已选清理项尝试结束相关软件进程，例如 Edge、Chrome、360 / 360 极速浏览器、WPS、千问、豆包、夸克、百度网盘、微信 / xwechat、企业微信、千牛 / 1688、QQ、QQ 音乐等。

对 360 缓存、Windows 字体缓存、Windows Search GatherLogs 等顽固项，工具还会尝试停止匹配到的服务，例如 `360bpsvc`、`FontCache`、`WSearch`。如果清理系统缩略图、图标缓存等项目时临时结束了 `explorer.exe`，清理后会自动重新启动资源管理器。

清理文件时会先解除只读/隐藏/系统属性，并对被占用或刚释放的缓存做短暂重试，减少 `WinError 5`、`WinError 32`、`WinError 145` 造成的残留。

工具会跳过 Codex、自身进程、Codex 运行缓存和当前 EXE 的运行时解压目录，避免中断当前会话。

## 注意事项

- 浏览器、微信、WPS、开始菜单、搜索索引等正在运行时，缓存文件可能会因为占用而清理失败。勾选强制关闭/停止相关服务后再清理会更干净。
- WPS、微信、千问、豆包等常驻后台的软件可能会锁定日志或缓存文件。
- `WinError 32` 通常表示文件正在被使用。
- `WinError 5` 通常表示权限不足或文件被系统/软件保护。
- `WinError 145` 通常是因为目录里仍有文件没删掉，所以父目录不能删除。
- WPS `backup` 可能包含文档恢复副本，清理前请确认不再需要。
- WDC 报告里的 TokenBroker、浏览器 Cookies/Network/Local Storage/Service Worker、Recent 历史记录、注册表 MRU、CatRoot2、Search 主数据库、WebCache 主数据库没有加入默认清理，避免影响登录态、站点数据或系统组件状态。

## 从源码运行

```powershell
python .\src\appdata_cleaner.py
```

只读扫描并输出 JSON：

```powershell
python .\src\appdata_cleaner.py --scan-json
```

## 构建 EXE

安装 PyInstaller：

```powershell
python -m pip install pyinstaller
```

构建：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name AppDataCleaner .\src\appdata_cleaner.py
```

生成文件：

```text
dist\AppDataCleaner.exe
```
