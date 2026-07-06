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

## 已覆盖的清理范围

- 用户临时目录：`AppData\Local\Temp`
- AppData 下常见缓存、日志、更新包、崩溃记录
- Chrome / Edge / 360 浏览器 / 360 极速浏览器 / 夸克 / 豆包 / 千问 / SPChrome 等 Chromium 系缓存
- WPS / 金山 Office 缓存、日志、更新包、备份缓存
- 百度网盘缓存
- 千牛 / 1688 CEF 缓存
- npm / pip / NuGet 等开发缓存
- 非系统空文件夹清理，例如空的 `AppData\Local\VirtualStore`
- 多用户扫描：会扫描 `C:\Users\*\AppData`，跳过 `Default`、`Public`、`All Users` 等模板/公共目录
- Photoshop 根目录临时缓存：如 `C:\Photoshop Temp*`、`D:\Photoshop Temp*`
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

默认不勾选。勾选后，工具会根据已选清理项尝试结束相关软件进程，例如 Edge、Chrome、360、WPS、千问、豆包、夸克、百度网盘、微信、企业微信、千牛等。

工具会跳过 Codex 和自身进程，避免中断当前会话。

## 注意事项

- 浏览器正在运行时，缓存文件可能会因为占用而清理失败。关闭浏览器后再清理会更干净。
- WPS、微信、千问、豆包等常驻后台的软件可能会锁定日志或缓存文件。
- `WinError 32` 通常表示文件正在被使用。
- `WinError 5` 通常表示权限不足或文件被系统/软件保护。
- `WinError 145` 通常是因为目录里仍有文件没删掉，所以父目录不能删除。
- WPS `backup` 可能包含文档恢复副本，清理前请确认不再需要。

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
