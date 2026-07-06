from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "AppData 安全清理工具"
LOG_DIR_NAME = "AppDataCleaner_logs"
REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

PROTECTED_COMPONENTS = {
    "cookie",
    "cookies",
    "network",
    "login",
    "login data",
    "local state",
    "local storage",
    "indexeddb",
    "session storage",
    "sessions",
    "webstorage",
    "databases",
    "extensions",
    "extensions_crx_cache",
    "extension state",
    "bookmarks",
    "preferences",
    "history",
    "favicons",
    "top sites",
    "web data",
    "sync data",
    "file system",
    "service worker",
}

PROTECTED_PATH_KEYWORDS = {
    "cookie",
    "login",
    "local storage",
    "indexeddb",
    "session storage",
    "webstorage",
    "service worker",
}

BROWSER_CACHE_NAMES = {
    "cache",
    "code cache",
    "gpucache",
    "grshadercache",
    "shadercache",
    "dawncache",
    "dawngraphitecache",
    "dawnwebgpucache",
    "crashpad",
    "crash reports",
    "browsermetrics",
    "component_crx_cache",
    "optimization_guide_model_store",
    "safe browsing",
    "certificaterevocation",
    "meipreload",
    "pnacl",
    "swreporter",
    "temp",
    "gpupersistentcache",
    "media cache",
    "blob_storage",
    "webstore downloads",
    "no_vary_search",
}

ROAMING_CACHE_NAMES = BROWSER_CACHE_NAMES | {
    "cache_data",
    "cacheddata",
    "cachedextensionvsixs",
    "log",
    "logs",
    "liveupdatelog",
    "crashinfo",
    "cef_cache",
    "webkitcachedata",
    "v8-compile-cache",
    "auto-updater",
    "v3update",
}

ROAMING_CACHE_NAME_PARTS = {
    "cache",
    "crash",
    "tmp",
    "temp",
    "update",
}

EMPTY_DIR_SKIP_TOP = {
    "microsoft",
    "packages",
    "programs",
}

SKIP_USER_PROFILES = {
    "all users",
    "default",
    "default user",
    "public",
}

PHOTOSHOP_PROCESSES = {
    "photoshop.exe",
}

CODEX_PROCESS_NAMES = {
    "codex.exe",
    "appdatacleaner.exe",
    "appdatacleaner_v2.exe",
    "appdatacleaner_v3.exe",
    "appdatacleaner_v4.exe",
    "appdatacleaner_v5.exe",
    "appdatacleaner_v6.exe",
}

PATH_PROCESS_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("\\microsoft\\edge\\", ("msedge.exe",)),
    ("\\google\\chrome\\", ("chrome.exe",)),
    ("\\360chrome\\", ("360chrome.exe", "360chromeX.exe", "360se.exe")),
    ("\\360chromex\\", ("360chromeX.exe", "360chrome.exe", "360se.exe")),
    ("\\360se6\\", ("360se.exe", "360chrome.exe", "360chromeX.exe")),
    ("\\360browser\\", ("360se.exe", "360chrome.exe", "360chromeX.exe")),
    ("\\kingsoft\\", ("wps.exe", "et.exe", "wpp.exe", "wpscloudsvr.exe", "qing.exe", "promecefpluginhost.exe", "aspcenter.exe")),
    ("\\qianwen\\", ("Qianwen.exe", "qianwen.exe")),
    ("\\doubao\\", ("Doubao.exe", "doubao.exe")),
    ("\\quark\\", ("Quark.exe", "quark.exe")),
    ("\\baidunetdisk\\", ("baidunetdisk.exe", "BaiduNetdisk.exe", "baidunetdiskhost.exe")),
    ("\\tencent\\xwechat\\", ("WeChat.exe", "WeChatAppEx.exe")),
    ("\\wechat\\", ("WeChat.exe", "WeChatAppEx.exe")),
    ("\\wxwork\\", ("WXWork.exe", "WXWorkWeb.exe")),
    ("\\1688cef\\", ("AliWorkbench.exe",)),
    ("\\qianniucef\\", ("AliWorkbench.exe",)),
    ("\\adspower_global\\", ("AdsPower Global.exe", "adspower_global.exe")),
    ("\\spchrome\\", ("SPChrome.exe", "chrome.exe")),
)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_process_running(names: set[str]) -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    output = completed.stdout.lower()
    return any(f'"{name.lower()}"' in output or name.lower() in output for name in names)


def norm_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def is_child_path(child: Path | str, parent: Path | str) -> bool:
    child_norm = norm_path(child)
    parent_norm = norm_path(parent)
    if child_norm == parent_norm:
        return False
    try:
        return os.path.commonpath([child_norm, parent_norm]) == parent_norm
    except ValueError:
        return False


def format_size(size: int | None) -> str:
    if size is None:
        return "未知"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def path_components(path: Path | str) -> list[str]:
    p = Path(path)
    return [part.lower() for part in p.parts]


def contains_protected_component(path: Path | str) -> bool:
    components = path_components(path)
    if any(part in PROTECTED_COMPONENTS for part in components):
        return True
    lowered = os.fspath(path).lower()
    return any(keyword in lowered for keyword in PROTECTED_PATH_KEYWORDS)


def is_reparse_path(path: Path | str) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE_FLAG)


def is_reparse_stat(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE_FLAG)


def user_profiles() -> list[Path]:
    users_root = Path(r"C:\Users")
    profiles: list[Path] = []
    if not users_root.exists():
        return [Path.home()]
    for entry in safe_scandir(users_root):
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
            if is_reparse_stat(st):
                continue
        except OSError:
            continue
        path = Path(entry.path)
        if path.name.lower() in SKIP_USER_PROFILES:
            continue
        if (path / "AppData").exists():
            profiles.append(path)
    return profiles


def safe_scandir(path: Path | str) -> Iterable[os.DirEntry]:
    try:
        with os.scandir(path) as it:
            yield from list(it)
    except OSError:
        return


def directory_size(path: Path | str) -> tuple[int, int]:
    total = 0
    files = 0
    stack = [os.fspath(path)]
    while stack:
        current = stack.pop()
        for entry in safe_scandir(current):
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if is_reparse_stat(st):
                        continue
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    total += st.st_size
                    files += 1
            except OSError:
                continue
    return total, files


def file_size(path: Path | str) -> tuple[int, int]:
    try:
        st = os.stat(path, follow_symlinks=False)
        return st.st_size, 1
    except OSError:
        return 0, 0


def make_writable(path: Path | str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def remove_any(path: Path | str, errors: list[str]) -> None:
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return
    if is_reparse_path(p):
        errors.append(f"跳过符号链接/联接点: {p}")
        return
    if p.is_dir():
        for entry in safe_scandir(p):
            remove_any(entry.path, errors)
        try:
            make_writable(p)
            p.rmdir()
        except OSError as exc:
            errors.append(f"删除目录失败: {p} ({exc})")
    else:
        try:
            make_writable(p)
            p.unlink()
        except OSError as exc:
            errors.append(f"删除文件失败: {p} ({exc})")


def remove_contents(path: Path | str, errors: list[str]) -> None:
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return
    if is_reparse_path(p):
        errors.append(f"跳过符号链接/联接点: {p}")
        return
    for entry in safe_scandir(p):
        remove_any(entry.path, errors)


@dataclass
class Target:
    ident: str
    category: str
    name: str
    path: Path
    mode: str = "tree"  # tree, contents, file, command
    recommended: bool = True
    requires_admin: bool = False
    description: str = ""
    source: str = ""
    before_processes: tuple[str, ...] = ()
    command: list[str] | None = None
    selected: bool = False
    exists: bool = False
    size: int | None = 0
    files: int = 0
    status: str = "未扫描"
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def can_clean(self) -> bool:
        return self.exists and self.mode in {"tree", "contents", "file", "command", "empty_dirs"}


class TargetCollector:
    def __init__(self) -> None:
        self.targets: list[Target] = []
        self.seen: set[tuple[str, str]] = set()
        self.counter = 0

    def add(
        self,
        path: Path | str,
        category: str,
        name: str,
        *,
        mode: str = "tree",
        recommended: bool = True,
        requires_admin: bool = False,
        description: str = "",
        source: str = "",
        before_processes: tuple[str, ...] = (),
        command: list[str] | None = None,
        allow_protected: bool = False,
    ) -> None:
        p = Path(path)
        if not allow_protected and contains_protected_component(p):
            return
        key = (norm_path(p), mode)
        if key in self.seen:
            return
        self.seen.add(key)
        self.counter += 1
        self.targets.append(
            Target(
                ident=f"t{self.counter}",
                category=category,
                name=name,
                path=p,
                mode=mode,
                recommended=recommended,
                requires_admin=requires_admin,
                description=description,
                source=source,
                before_processes=before_processes,
                command=command,
            )
        )


def walk_dirs_limited(root: Path, max_depth: int = 5) -> Iterable[Path]:
    if not root.exists() or not root.is_dir() or is_reparse_path(root):
        return
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth >= max_depth:
            continue
        for entry in safe_scandir(current):
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
                if is_reparse_stat(st):
                    continue
            except OSError:
                continue
            p = Path(entry.path)
            yield p
            if not contains_protected_component(p):
                stack.append((p, depth + 1))


def is_browser_cache_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in BROWSER_CACHE_NAMES:
        return True
    return False


def collect_browser_caches(collector: TargetCollector, root: Path, label: str) -> None:
    if not root.exists():
        return
    for cache_dir in walk_dirs_limited(root, max_depth=5):
        if not is_browser_cache_dir(cache_dir):
            continue
        if contains_protected_component(cache_dir):
            continue
        collector.add(
            cache_dir,
            "浏览器/Chromium 缓存",
            f"{label} - {cache_dir.name}",
            mode="tree",
            recommended=True,
            description="浏览器缓存、渲染缓存、安全列表或崩溃日志；不包含 Cookies、Login Data、Local Storage、IndexedDB。",
            source="前面扫描 + Chrome/Chromium 保护规则",
        )


def collect_named_cache_dirs(
    collector: TargetCollector,
    root: Path,
    category: str,
    label: str,
    *,
    process: str | None = None,
) -> None:
    if not root.exists():
        return
    for d in walk_dirs_limited(root, max_depth=8):
        if "cache" not in d.name.lower():
            continue
        if contains_protected_component(d):
            continue
        processes = (process,) if process else ()
        collector.add(
            d,
            category,
            f"{label} - {d.name}",
            mode="tree",
            recommended=True,
            description="按批处理脚本规则匹配到的 cache 目录。",
            source="清理千牛和1688缓存输出日志.bat",
            before_processes=processes,
        )


def is_roaming_safe_cache_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in ROAMING_CACHE_NAMES:
        return True
    return any(part in name for part in ROAMING_CACHE_NAME_PARTS)


def collect_roaming_safe_caches(collector: TargetCollector, root: Path) -> None:
    if not root.exists():
        return
    for cache_dir in walk_dirs_limited(root, max_depth=8):
        if not is_roaming_safe_cache_dir(cache_dir):
            continue
        if contains_protected_component(cache_dir):
            continue
        collector.add(
            cache_dir,
            "Roaming 安全缓存",
            f"{cache_dir.parent.name} - {cache_dir.name}",
            mode="tree",
            recommended=True,
            description="Roaming 下自动发现的缓存、日志、崩溃记录、更新残留或临时目录；已排除登录/cookies/本地站点数据相关路径。",
            source="Roaming 扫描",
        )


def collect_photoshop_temp_targets(collector: TargetCollector) -> None:
    if is_process_running(PHOTOSHOP_PROCESSES):
        return
    for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{drive}:\\")
        if not root.exists():
            continue
        try:
            for item in root.glob("Photoshop Temp*"):
                if is_reparse_path(item):
                    continue
                collector.add(
                    item,
                    "Photoshop 缓存",
                    f"{root} Photoshop 临时文件",
                    mode="tree" if item.is_dir() else "file",
                    recommended=True,
                    description="仅在 Photoshop 未运行时清理磁盘根目录 Photoshop Temp* 临时缓存。",
                    source="用户要求",
                )
        except OSError:
            continue


def top_under(root: Path, path: Path) -> str:
    try:
        rel = path.relative_to(root)
        return rel.parts[0].lower() if rel.parts else ""
    except ValueError:
        return ""


def is_empty_dir_candidate(root: Path, path: Path) -> bool:
    if not path.exists() or not path.is_dir() or is_reparse_path(path):
        return False
    if top_under(root, path) in EMPTY_DIR_SKIP_TOP:
        return False
    if contains_protected_component(path):
        return False
    try:
        with os.scandir(path) as it:
            return next(it, None) is None
    except OSError:
        return False


def collect_empty_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    empty_dirs: list[Path] = []
    for d in walk_dirs_limited(root, max_depth=12):
        if is_empty_dir_candidate(root, d):
            empty_dirs.append(d)
    empty_dirs.sort(key=lambda p: len(p.parts), reverse=True)
    return empty_dirs


def remove_empty_dirs(root: Path, log: Callable[[str], None]) -> tuple[int, list[str]]:
    errors: list[str] = []
    removed = 0
    for d in collect_empty_dirs(root):
        if not is_empty_dir_candidate(root, d):
            continue
        try:
            d.rmdir()
            removed += 1
        except OSError as exc:
            errors.append(f"删除空目录失败: {d} ({exc})")
    log(f"已删除空目录: {removed} 个")
    return removed, errors


def collect_user_targets(c: TargetCollector, user_profile: Path) -> None:
    user_label = user_profile.name
    local = user_profile / "AppData" / "Local"
    roaming = user_profile / "AppData" / "Roaming"
    local_low = user_profile / "AppData" / "LocalLow"

    c.add(local / "Temp", "系统/临时文件", f"{user_label} 用户临时文件", mode="contents", recommended=True, source="前面扫描")
    c.add(local / "CrashDumps", "系统/临时文件", f"{user_label} 用户崩溃转储", mode="tree", recommended=True, source="帖子")
    c.add(local_low / "Temp", "系统/临时文件", f"{user_label} LocalLow 临时文件", mode="contents", recommended=True, source="前面扫描")
    c.add(local / "Microsoft" / "Windows" / "INetCache", "系统/临时文件", f"{user_label} Windows INetCache", mode="contents", recommended=True, source="前面扫描")
    c.add(local / "Microsoft" / "Windows" / "Explorer", "系统/临时文件", f"{user_label} 资源管理器缩略图/图标缓存", mode="contents", recommended=True, source="前面扫描")
    c.add(local / "Microsoft" / "Windows" / "Caches", "系统/临时文件", f"{user_label} Windows Caches", mode="contents", recommended=True, source="前面扫描")
    c.add(
        local,
        "空文件夹清理",
        f"{user_label} AppData\\Local 非系统空文件夹",
        mode="empty_dirs",
        recommended=True,
        source="用户要求",
        description="只删除 AppData\\Local 下当前仍然为空的非系统目录；跳过 Microsoft、Packages、Programs、登录/cookies/浏览器状态相关路径和联接点。",
    )

    c.add(local / "npm-cache", "开发缓存", f"{user_label} npm 缓存", mode="tree", recommended=True, source="前面扫描")
    c.add(local / "pip" / "Cache", "开发缓存", f"{user_label} pip 缓存", mode="tree", recommended=True, source="常见缓存")
    c.add(local / "NuGet" / "Cache", "开发缓存", f"{user_label} NuGet Cache", mode="tree", recommended=False, source="帖子")
    c.add(local / "NuGet" / "v3-cache", "开发缓存", f"{user_label} NuGet v3-cache", mode="tree", recommended=False, source="帖子")
    c.add(user_profile / ".nuget" / "packages", "开发缓存", f"{user_label} NuGet 全局包缓存", mode="tree", recommended=False, source="帖子")
    c.add(local / "Package Cache", "系统转储/高级项", f"{user_label} 用户级 Package Cache", mode="tree", recommended=False, source="帖子")

    known_appdata = [
        (local / "JianyingPro" / "User Data" / "Cache", "应用缓存/更新包", "剪映缓存", True),
        (local / "JianyingPro" / "User Data" / "Download", "应用缓存/更新包", "剪映下载更新包", True),
        (roaming / "Tencent" / "xwechat" / "update", "应用缓存/更新包", "微信 xwechat 更新包", True),
        (roaming / "Tencent" / "xwechat" / "log", "应用缓存/更新包", "微信 xwechat 日志", True),
        (roaming / "Tencent" / "xwechat" / "crashinfo", "应用缓存/更新包", "微信 xwechat 崩溃记录", True),
        (roaming / "kingsoft" / "office6" / "backup", "应用缓存/更新包", "WPS/Kingsoft 备份缓存", True),
        (roaming / "kingsoft" / "office6" / "update", "应用缓存/更新包", "WPS 更新包", True),
        (roaming / "kingsoft" / "office6" / "cache", "应用缓存/更新包", "WPS 缓存", True),
        (roaming / "kingsoft" / "office6" / "log", "应用缓存/更新包", "WPS 日志", True),
        (roaming / "XMind" / "Electron v3" / "vana" / "auto-updater", "应用缓存/更新包", "XMind 自动更新缓存", True),
        (local / "xmind-updater", "应用缓存/更新包", "XMind 更新器残留", True),
        (local / "Quark" / "User Data" / "QianwenInstaller", "应用缓存/更新包", "夸克里的千问安装包", True),
        (local / "Qianwen" / "User Data" / "updates", "应用缓存/更新包", "千问更新包", True),
        (roaming / "baidunetdisk" / "Cache" / "Cache_Data", "应用缓存/更新包", "百度网盘 Cache_Data", True),
        (roaming / "baidunetdisk" / "Code Cache", "应用缓存/更新包", "百度网盘 Code Cache", True),
        (roaming / "baidunetdisk" / "GPUCache", "应用缓存/更新包", "百度网盘 GPUCache", True),
    ]
    for path, category, name, recommended in known_appdata:
        c.add(path, category, f"{user_label} {name}", mode="tree", recommended=recommended, source="前面扫描")

    for base in (local, roaming):
        if not base.exists():
            continue
        for entry in safe_scandir(base):
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            p = Path(entry.path)
            lname = p.name.lower()
            if lname.endswith("-updater") or lname.endswith("_updater") or lname.endswith("updater"):
                c.add(p, "应用缓存/更新包", f"{p.name} 更新器残留", mode="tree", recommended=True, source="帖子 + 前面扫描")
            elif lname.startswith("app_shell_cache_"):
                c.add(p, "应用缓存/更新包", f"{p.name} 应用壳缓存", mode="tree", recommended=True, source="前面扫描")

    browser_roots = [
        (local / "Google" / "Chrome" / "User Data", f"{user_label} Chrome"),
        (local / "google" / "Chrome" / "User Data", f"{user_label} Chrome"),
        (local / "Microsoft" / "Edge" / "User Data", f"{user_label} Edge"),
        (local / "360Chrome" / "Chrome" / "User Data", f"{user_label} 360 极速浏览器"),
        (local / "360ChromeX" / "Chrome" / "User Data", f"{user_label} 360 极速浏览器X"),
        (local / "360Chrome" / "User Data", f"{user_label} 360 极速浏览器"),
        (local / "360ChromeX" / "User Data", f"{user_label} 360 极速浏览器X"),
        (roaming / "360se6" / "User Data", f"{user_label} 360 浏览器"),
        (roaming / "360browser" / "User Data", f"{user_label} 360 浏览器"),
        (local / "Quark" / "User Data", f"{user_label} 夸克"),
        (local / "Doubao" / "User Data", f"{user_label} 豆包"),
        (local / "Qianwen" / "User Data", f"{user_label} 千问"),
        (local / "SPChrome" / "User Data", f"{user_label} SPChrome"),
        (roaming / "adspower_global", f"{user_label} AdsPower"),
    ]
    for root, label in browser_roots:
        collect_browser_caches(c, root, label)

    collect_roaming_safe_caches(c, roaming)

    collect_named_cache_dirs(c, local / "1688CEF", "千牛/1688 缓存", f"{user_label} 1688CEF", process="AliWorkbench.exe")
    collect_named_cache_dirs(c, local / "QianniuCEF", "千牛/1688 缓存", f"{user_label} QianniuCEF", process="AliWorkbench.exe")


def collect_targets() -> list[Target]:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))

    c = TargetCollector()

    for profile in user_profiles():
        collect_user_targets(c, profile)

    collect_photoshop_temp_targets(c)

    c.add(Path(r"C:\Windows\MEMORY.DMP"), "系统转储/高级项", "Windows MEMORY.DMP", mode="file", recommended=True, requires_admin=True, source="帖子")
    for root in [Path(r"C:\Windows\LiveKernelReports"), Path(r"C:\Windows\Minidump")]:
        if root.exists():
            for dmp in root.rglob("*.dmp"):
                if dmp.is_file():
                    c.add(dmp, "系统转储/高级项", f"{root.name} 转储文件", mode="file", recommended=True, requires_admin=True, source="帖子")

    c.add(Path(r"C:\Program Files\WindowsApps.tmp"), "系统转储/高级项", "Microsoft Store 废弃 WindowsApps.tmp", mode="tree", recommended=False, requires_admin=True, source="帖子")
    c.add(
        Path(r"C:\Windows\WinSxS"),
        "系统转储/高级项",
        "WinSxS 组件存储清理（执行 DISM）",
        mode="command",
        recommended=False,
        requires_admin=True,
        source="帖子",
        command=["dism", "/online", "/Cleanup-Image", "/StartComponentCleanup"],
        description="使用系统自带 DISM 清理旧组件备份；不会手动删除 WinSxS 目录。",
        allow_protected=True,
    )
    c.add(program_data / "Intel" / "Package Cache", "系统转储/高级项", "Intel 驱动安装包缓存", mode="tree", recommended=False, requires_admin=True, source="帖子")
    c.add(
        Path(r"C:\hiberfil.sys"),
        "系统转储/高级项",
        "休眠文件 hiberfil.sys（执行 powercfg -h off）",
        mode="command",
        recommended=False,
        requires_admin=True,
        source="帖子",
        command=["powercfg", "-h", "off"],
        description="会关闭休眠功能并释放 hiberfil.sys；不会影响 cookies，但会影响休眠/快速启动。",
        allow_protected=True,
    )

    return c.targets


def scan_targets(targets: list[Target]) -> list[Target]:
    for target in targets:
        p = target.path
        if target.mode == "empty_dirs":
            empty_dirs = collect_empty_dirs(p)
            target.exists = p.exists() and bool(empty_dirs)
            target.size = 0
            target.files = len(empty_dirs)
            target.status = "可清理空目录" if empty_dirs else "没有空目录"
        elif target.mode == "command":
            target.exists = p.exists()
            if target.exists and p.is_file():
                target.size, target.files = file_size(p)
            else:
                target.size, target.files = (None, 0)
            target.status = "可执行命令" if target.exists else "不存在"
        elif target.mode == "file":
            target.exists = p.exists() and p.is_file()
            target.size, target.files = file_size(p) if target.exists else (0, 0)
            target.status = "可清理" if target.exists and target.size else "不存在"
        else:
            target.exists = p.exists() and p.is_dir()
            if target.exists and is_reparse_path(p):
                target.exists = False
                target.size = 0
                target.files = 0
                target.status = "跳过联接点"
            elif target.exists:
                target.size, target.files = directory_size(p)
                target.status = "可清理" if target.size else "空目录"
            else:
                target.size = 0
                target.files = 0
                target.status = "不存在"
        target.selected = target.recommended and target.exists and (bool(target.size) or target.mode == "empty_dirs")
    return targets


def prune_nested_targets(targets: list[Target]) -> list[Target]:
    kept: list[Target] = []
    for target in sorted(targets, key=lambda t: (len(Path(t.path).parts), norm_path(t.path))):
        if (
            target.category == "Roaming 安全缓存"
            and target.size is not None
            and target.size < 1 * 1024 * 1024
        ):
            continue
        nested = False
        for parent in kept:
            if parent.mode not in {"tree", "contents"}:
                continue
            if not parent.recommended and target.recommended:
                continue
            if is_child_path(target.path, parent.path):
                nested = True
                break
        if not nested:
            kept.append(target)
    return kept


def run_command(command: list[str], log: Callable[[str], None]) -> bool:
    try:
        log(f"执行命令: {' '.join(command)}")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=None)
        if completed.stdout.strip():
            log(completed.stdout.strip())
        if completed.stderr.strip():
            log(completed.stderr.strip())
        if completed.returncode != 0:
            log(f"命令返回错误码: {completed.returncode}")
            return False
        return True
    except Exception as exc:
        log(f"命令执行失败: {exc}")
        return False


def kill_processes(process_names: Iterable[str], log: Callable[[str], None]) -> None:
    for name in sorted({p for p in process_names if p and p.lower() not in CODEX_PROCESS_NAMES}):
        if not name:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/IM", name, "/T"], capture_output=True, text=True, timeout=15)
            log(f"已尝试结束进程: {name}")
        except Exception as exc:
            log(f"结束进程失败 {name}: {exc}")


def infer_processes_for_target(target: Target) -> tuple[str, ...]:
    lowered = os.fspath(target.path).lower()
    if "\\roaming\\codex\\" in lowered or "\\appdatacleaner" in lowered:
        return ()
    processes: list[str] = list(target.before_processes)
    for marker, names in PATH_PROCESS_RULES:
        if marker in lowered:
            processes.extend(names)
    return tuple(processes)


def clean_target(target: Target, log: Callable[[str], None]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if target.requires_admin and not is_admin():
        errors.append("需要管理员权限，请右键以管理员身份运行。")
        return False, errors
    if not target.exists:
        errors.append("目标不存在。")
        return False, errors
    if target.mode != "command" and contains_protected_component(target.path):
        errors.append("命中登录/cookies/站点数据保护名单，已阻止。")
        return False, errors

    if target.mode == "empty_dirs":
        removed, empty_errors = remove_empty_dirs(target.path, log)
        errors.extend(empty_errors)
        if removed == 0 and not errors:
            errors.append("没有可删除的空目录。")
        return removed > 0 and not errors, errors

    if target.mode == "command":
        ok = run_command(target.command or [], log)
        return ok, errors

    if target.mode in {"tree", "contents"} and is_reparse_path(target.path):
        errors.append("目标是符号链接/联接点，已跳过。")
        return False, errors

    if target.path == Path(r"C:\Program Files\WindowsApps.tmp") and target.requires_admin:
        run_command(["takeown", "/f", os.fspath(target.path), "/r", "/d", "y"], log)
        run_command(["icacls", os.fspath(target.path), "/grant", "administrators:F", "/t"], log)

    try:
        if target.mode == "file":
            remove_any(target.path, errors)
        elif target.mode == "contents":
            remove_contents(target.path, errors)
        else:
            remove_any(target.path, errors)
    except Exception as exc:
        errors.append(str(exc))

    return not errors, errors


class CleanerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1160x720")
        self.root.minsize(920, 560)

        self.targets: list[Target] = []
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_log_path: Path | None = None
        self.force_close_var = tk.BooleanVar(value=False)

        self.build_ui()
        self.root.after(100, self.poll_queue)
        self.scan_async()

    def build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=(12, 10))
        top.pack(side=tk.TOP, fill=tk.X)

        title = ttk.Label(top, text=APP_NAME, font=("Microsoft YaHei UI", 14, "bold"))
        title.pack(side=tk.LEFT)

        admin_text = "管理员: 是" if is_admin() else "管理员: 否"
        self.admin_label = ttk.Label(top, text=admin_text)
        self.admin_label.pack(side=tk.RIGHT)

        hint = ttk.Label(
            self.root,
            text="默认只选缓存、日志、更新包、临时文件；程序内置保护名单，会阻止 Cookies、Login Data、Local Storage、IndexedDB 等登录相关数据。",
            padding=(12, 0),
        )
        hint.pack(side=tk.TOP, fill=tk.X)

        button_frame = ttk.Frame(self.root, padding=(12, 8))
        button_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(button_frame, text="重新扫描占用", command=self.scan_async).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="推荐项全选", command=self.select_recommended).pack(side=tk.LEFT, padx=(0, 8))
        self.toggle_select_button = ttk.Button(button_frame, text="全不选", command=self.toggle_select_all_none)
        self.toggle_select_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="清理勾选项", command=self.clean_selected_async).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="一键清理推荐项", command=self.clean_recommended_async).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="打开日志目录", command=self.open_log_dir).pack(side=tk.RIGHT)

        options_frame = ttk.Frame(self.root, padding=(12, 0))
        options_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Checkbutton(
            options_frame,
            text="清理前强制关闭相关软件（不关闭 Codex）",
            variable=self.force_close_var,
        ).pack(side=tk.LEFT)

        self.summary_var = tk.StringVar(value="准备扫描...")
        ttk.Label(self.root, textvariable=self.summary_var, padding=(12, 0)).pack(side=tk.TOP, fill=tk.X)

        main = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=8)

        table_frame = ttk.Frame(main)
        main.add(table_frame, weight=4)

        columns = ("selected", "category", "size", "files", "mode", "admin", "path", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "selected": "选择",
            "category": "类别",
            "size": "占用",
            "files": "文件数",
            "mode": "方式",
            "admin": "管理员",
            "path": "路径/动作",
            "status": "状态",
        }
        widths = {
            "selected": 56,
            "category": 150,
            "size": 100,
            "files": 80,
            "mode": 82,
            "admin": 70,
            "path": 520,
            "status": 120,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor=tk.W, stretch=(col == "path"))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<space>", self.on_space_toggle)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        log_frame = ttk.Frame(main)
        main.add(log_frame, weight=1)
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def log(self, message: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{stamp}] {message}\n")
        self.log_text.see(tk.END)

    def poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "scan_done":
                    self.targets = payload  # type: ignore[assignment]
                    self.refresh_tree()
                    self.log("扫描完成。")
                elif kind == "clean_done":
                    self.log("清理完成，正在重新扫描。")
                    self.scan_async()
                elif kind == "log":
                    self.log(str(payload))
                elif kind == "error":
                    messagebox.showerror(APP_NAME, str(payload))
                    self.log(str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self.poll_queue)

    def scan_async(self) -> None:
        self.summary_var.set("正在扫描，请稍候...")
        self.log("开始扫描缓存和垃圾目录。")

        def worker() -> None:
            try:
                targets = prune_nested_targets(scan_targets(collect_targets()))
                targets = [t for t in targets if t.exists and ((t.size or 0) > 0 or t.mode in {"command", "empty_dirs"})]
                targets.sort(key=lambda x: (x.category, -(x.size or 0), os.fspath(x.path).lower()))
                self.worker_queue.put(("scan_done", targets))
            except Exception as exc:
                self.worker_queue.put(("error", f"扫描失败: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        total = sum((t.size or 0) for t in self.targets)
        selected = sum((t.size or 0) for t in self.targets if t.selected)
        for target in self.targets:
            self.tree.insert("", tk.END, iid=target.ident, values=self.row_values(target))
        self.update_toggle_select_button()
        self.summary_var.set(
            f"发现 {len(self.targets)} 项，可选总占用 {format_size(total)}；当前勾选 {format_size(selected)}。"
        )

    def row_values(self, target: Target) -> tuple[str, str, str, str, str, str, str, str]:
        mode_text = {
            "tree": "删目录",
            "contents": "清内容",
            "file": "删文件",
            "command": "执行命令",
            "empty_dirs": "删空目录",
        }.get(target.mode, target.mode)
        admin_text = "需要" if target.requires_admin else ""
        path_text = " ".join(target.command or []) if target.mode == "command" else os.fspath(target.path)
        return (
            "[x]" if target.selected else "[ ]",
            target.category,
            format_size(target.size),
            str(target.files),
            mode_text,
            admin_text,
            path_text,
            target.status,
        )

    def find_target(self, ident: str) -> Target | None:
        for target in self.targets:
            if target.ident == ident:
                return target
        return None

    def on_tree_click(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if col == "#1" and item:
            self.toggle_item(item)

    def on_space_toggle(self, _event: tk.Event) -> str:
        item = self.tree.focus()
        if item:
            self.toggle_item(item)
        return "break"

    def toggle_item(self, ident: str) -> None:
        target = self.find_target(ident)
        if not target:
            return
        target.selected = not target.selected
        self.tree.item(ident, values=self.row_values(target))
        self.update_toggle_select_button()
        selected = sum((t.size or 0) for t in self.targets if t.selected)
        total = sum((t.size or 0) for t in self.targets)
        self.summary_var.set(
            f"发现 {len(self.targets)} 项，可选总占用 {format_size(total)}；当前勾选 {format_size(selected)}。"
        )

    def select_recommended(self) -> None:
        for target in self.targets:
            target.selected = target.recommended and target.exists and (bool(target.size) or target.mode == "empty_dirs")
        self.refresh_tree()

    def select_none(self) -> None:
        for target in self.targets:
            target.selected = False
        self.refresh_tree()

    def select_all(self) -> None:
        for target in self.targets:
            target.selected = target.exists and target.can_clean
        self.refresh_tree()

    def toggle_select_all_none(self) -> None:
        if any(target.selected for target in self.targets):
            self.select_none()
        else:
            self.select_all()

    def update_toggle_select_button(self) -> None:
        if hasattr(self, "toggle_select_button"):
            text = "全不选" if any(target.selected for target in self.targets) else "全选"
            self.toggle_select_button.configure(text=text)

    def clean_recommended_async(self) -> None:
        self.select_recommended()
        self.clean_selected_async()

    def clean_selected_async(self) -> None:
        selected = [t for t in self.targets if t.selected and t.can_clean]
        if not selected:
            messagebox.showinfo(APP_NAME, "没有勾选可清理项目。")
            return
        total = sum((t.size or 0) for t in selected)
        admin_count = sum(1 for t in selected if t.requires_admin)
        message = f"即将清理 {len(selected)} 项，预计释放 {format_size(total)}。"
        if admin_count:
            message += f"\n其中 {admin_count} 项需要管理员权限。"
        if self.force_close_var.get():
            process_count = len({p.lower() for target in selected for p in infer_processes_for_target(target)})
            if process_count:
                message += f"\n已勾选强制关闭：清理前会尝试结束 {process_count} 类相关软件进程，不会关闭 Codex。"
        message += "\n\n会继续保护 Cookies、Login Data、Local Storage、IndexedDB 等登录相关数据。确认开始？"
        if not messagebox.askyesno(APP_NAME, message):
            return

        force_close = self.force_close_var.get()

        def worker() -> None:
            log_path = self.make_log_path()
            self.last_log_path = log_path
            process_names = []
            if force_close:
                for target in selected:
                    process_names.extend(infer_processes_for_target(target))
            if force_close and process_names:
                self.worker_queue.put(("log", "已勾选强制关闭，清理前先结束相关后台进程（跳过 Codex）。"))
                kill_processes(process_names, lambda msg: self.worker_queue.put(("log", msg)))

            with log_path.open("a", encoding="utf-8") as fp:
                fp.write(f"{APP_NAME} 清理日志\n")
                fp.write(f"时间: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
                fp.write(f"管理员: {'是' if is_admin() else '否'}\n\n")
                fp.write(f"强制关闭相关软件: {'是' if force_close else '否'}\n\n")
                for target in selected:
                    before = target.size or 0
                    self.worker_queue.put(("log", f"清理: {target.name} - {target.path}"))
                    ok, errors = clean_target(target, lambda msg: self.worker_queue.put(("log", msg)))
                    status = "成功" if ok else "部分失败/跳过"
                    fp.write(f"[{status}] {target.category} | {target.name}\n")
                    fp.write(f"路径/动作: {target.path if target.mode != 'command' else ' '.join(target.command or [])}\n")
                    fp.write(f"扫描占用: {format_size(before)}\n")
                    if errors:
                        fp.write("错误:\n")
                        for err in errors:
                            fp.write(f"  - {err}\n")
                            self.worker_queue.put(("log", err))
                    fp.write("\n")
            self.worker_queue.put(("log", f"日志已写入: {log_path}"))
            self.worker_queue.put(("clean_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def make_log_path(self) -> Path:
        desktop = Path.home() / "Desktop"
        log_dir = desktop / LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"clean_{dt.datetime.now():%Y%m%d_%H%M%S}.txt"

    def open_log_dir(self) -> None:
        log_dir = Path.home() / "Desktop" / LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(log_dir)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"打开日志目录失败: {exc}")


def cli_scan_json() -> None:
    targets = prune_nested_targets(scan_targets(collect_targets()))
    rows = [
        {
            "category": t.category,
            "name": t.name,
            "path": os.fspath(t.path),
            "mode": t.mode,
            "recommended": t.recommended,
            "requires_admin": t.requires_admin,
            "exists": t.exists,
            "size": t.size,
            "size_text": format_size(t.size),
            "files": t.files,
            "status": t.status,
        }
        for t in targets
        if t.exists and ((t.size or 0) > 0 or t.mode in {"command", "empty_dirs"})
    ]
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def main() -> None:
    if "--scan-json" in sys.argv:
        cli_scan_json()
        return
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    CleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
