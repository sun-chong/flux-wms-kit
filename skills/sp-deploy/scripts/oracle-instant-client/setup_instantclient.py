#!/usr/bin/env python3
"""
Oracle Instant Client 自动下载脚本

从 Oracle 官网下载 Instant Client 19.24 Basic 包并解压到本目录，
供 oracledb thick mode 使用（连接 Oracle 11g 必需，thin mode 不支持）。
被以下 Skill 共用：sp-deploy / sp-parser / flux-extconfig-gen / flux-report-builder。

用法:
    python setup_instantclient.py                     # 自动检测平台并下载（已存在则跳过）
    python setup_instantclient.py --platform windows  # 强制指定平台（windows / linux）
    python setup_instantclient.py --force             # 删除已有目录并重新下载

说明:
    - 下载目标 instantclient_19_24/ 已加入 .gitignore，不会进入 git 仓库
    - 可在其他 Skill 执行前手动运行本脚本，提前完成下载（约 76MB / 72MB）
    - 仅使用 Python 标准库，无第三方依赖
    - 选择 19c 版本：19c 是官方支持连接 Oracle 11g 的最后版本

[作者署名] SUNC
"""

import argparse
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile

# Instant Client 版本与下载源（Oracle 官网直链，无需登录）
IC_VERSION = "19.24"
CLIENT_DIR_NAME = "instantclient_19_24"

# 各平台对应的 Basic 包（zip 压缩包：Windows 约 76MB，Linux 约 72MB；解压后约 234MB）
_BASE_URL = "https://download.oracle.com/otn_software"  # otn_software 为免登录直链路径
PACKAGES = {
    "windows": {
        "url": f"{_BASE_URL}/nt/instantclient/1924000/instantclient-basic-windows.x64-19.24.0.0.0dbru.zip",
        "size_hint": "约 76MB",
    },
    "linux": {
        "url": f"{_BASE_URL}/linux/instantclient/1924000/instantclient-basic-linux.x64-19.24.0.0.0dbru.zip",
        "size_hint": "约 72MB",
    },
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CLIENT_DIR = os.path.join(SCRIPT_DIR, CLIENT_DIR_NAME)


def detect_platform():
    """自动检测当前平台，返回 PACKAGES 的键（windows / linux）"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" and machine in ("amd64", "x86_64"):
        return "windows"
    if system == "linux" and machine in ("x86_64", "amd64"):
        return "linux"
    raise RuntimeError(
        f"不支持的平台: {platform.system()} {platform.machine()}。"
        f"当前仅支持 Windows x64 和 Linux x86_64，"
        f"请从 https://www.oracle.com/database/technologies/instant-client.html 手动下载"
    )


def download_file(url, dest_path, max_retries=3):
    """下载文件，支持断点续传与自动重试（弱网/代理环境下大文件传输易中断）"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        downloaded = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
        headers = {"User-Agent": "Mozilla/5.0"}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
            print(f"  第 {attempt}/{max_retries} 次重试，从 {downloaded // (1024 * 1024)}MB 处续传...")
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if downloaded and resp.status == 206:
                    # 服务器支持续传
                    total = downloaded + int(resp.headers.get("Content-Length") or 0)
                    mode = "ab"
                else:
                    # 服务器不支持续传，从头下载
                    total = int(resp.headers.get("Content-Length") or 0)
                    downloaded = 0
                    mode = "wb"
                with open(dest_path, mode) as f:
                    next_report = (downloaded // (20 * 1024 * 1024) + 1) * 20 * 1024 * 1024
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded >= next_report:
                            if total:
                                print(f"\r  下载中: {min(downloaded, total) / (1024 * 1024):.0f}MB / {total / (1024 * 1024):.0f}MB", end="", flush=True)
                            else:
                                print(f"\r  下载中: {downloaded / (1024 * 1024):.0f}MB", end="", flush=True)
                            next_report += 20 * 1024 * 1024
            print()
            if total and downloaded < total:
                raise IOError(f"下载不完整: {downloaded}/{total} 字节")
            return
        except urllib.error.HTTPError as e:
            if e.code == 416:  # 已下载字节等于总大小时服务器返回 416，视为完成
                print()
                return
            print()
            last_err = e
        except Exception as e:
            print()
            last_err = e
        if attempt < max_retries:
            print(f"  下载中断（{last_err}），准备重试...")
    raise RuntimeError(f"下载重试 {max_retries} 次后仍失败: {last_err}")


def extract_zip(zip_path, out_dir):
    """解压 zip 到 out_dir，正确处理 Linux 包内的符号链接（zipfile 默认会把链接解成空文件）"""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = os.path.join(out_dir, info.filename)
            # 防路径穿越（zip slip）
            if not os.path.abspath(target).startswith(os.path.abspath(out_dir) + os.sep):
                raise RuntimeError(f"zip 内含非法路径: {info.filename}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                link_target = zf.read(info).decode("utf-8")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.lexists(target):
                    os.remove(target)
                os.symlink(link_target, target)
            elif info.is_dir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                # 保留 Linux 包内可执行位
                if mode and mode & 0o111:
                    os.chmod(target, 0o755)


def ensure_instant_client(platform_name=None, client_dir=None, force=False, quiet=False):
    """确保 Instant Client 目录存在，缺失时自动下载并解压。

    供各 Skill 脚本导入调用：
        sys.path.insert(0, <sp-deploy>/scripts/oracle-instant-client)
        from setup_instantclient import ensure_instant_client
        ensure_instant_client()

    Args:
        platform_name: 强制指定平台（windows / linux），默认自动检测
        client_dir:    目标目录，默认为脚本同目录的 instantclient_19_24
        force:         已存在时删除并重新下载
        quiet:         已存在时不打印提示

    Returns:
        str: Instant Client 目录路径

    Raises:
        RuntimeError: 平台不支持或下载/解压失败
    """
    client_dir = os.path.abspath(client_dir) if client_dir else DEFAULT_CLIENT_DIR
    if os.path.isdir(client_dir) and os.listdir(client_dir):
        if not force:
            if not quiet:
                print(f"Oracle Instant Client 已存在: {client_dir}")
            return client_dir
        shutil.rmtree(client_dir)

    pkg_key = platform_name or detect_platform()
    pkg = PACKAGES.get(pkg_key)
    if pkg is None:
        raise RuntimeError(f"未知平台: {pkg_key}，可选值: {', '.join(PACKAGES)}")

    print(f"Oracle Instant Client {IC_VERSION} ({pkg_key}, {pkg['size_hint']}) 开始下载...")
    print(f"来源: {pkg['url']}")

    # 临时文件放在脚本目录内，保证与目标目录同盘、可原子改名，且被 .gitignore 覆盖
    zip_fd, zip_path = tempfile.mkstemp(prefix="instantclient_basic_", suffix=".zip", dir=SCRIPT_DIR)
    os.close(zip_fd)
    extract_dir = tempfile.mkdtemp(prefix="instantclient_extract_", dir=SCRIPT_DIR)
    try:
        download_file(pkg["url"], zip_path)
        print("  下载完成，解压中...")
        extract_zip(zip_path, extract_dir)

        # 定位 zip 内的客户端目录：优先 instantclient_* 命名目录
        # （部分包顶层还含 META-INF 等非客户端内容，不搬入目标目录）
        top_dirs = [e for e in os.listdir(extract_dir)
                    if os.path.isdir(os.path.join(extract_dir, e))]
        ic_dir = next((e for e in top_dirs if e.startswith("instantclient_")), None)
        if ic_dir:
            os.replace(os.path.join(extract_dir, ic_dir), client_dir)
        elif len(top_dirs) == 1:
            os.replace(os.path.join(extract_dir, top_dirs[0]), client_dir)
        else:
            # 兜底：顶层无明确目录时整体搬入
            os.makedirs(client_dir)
            for e in os.listdir(extract_dir):
                os.replace(os.path.join(extract_dir, e), os.path.join(client_dir, e))
            extract_dir = None  # 已腾空，跳过 finally 清理
        print(f"Oracle Instant Client 就绪: {client_dir}")
        return client_dir
    except Exception as e:
        raise RuntimeError(
            f"Oracle Instant Client 自动下载失败: {e}\n"
            f"请检查网络后重试，或从 https://www.oracle.com/database/technologies/instant-client.html "
            f"手动下载 {pkg_key} Basic 包并解压到 {client_dir}"
        ) from e
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if extract_dir and os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Oracle Instant Client 自动下载脚本")
    parser.add_argument("--platform", choices=sorted(PACKAGES), help="强制指定平台，默认自动检测")
    parser.add_argument("--dir", default=None, help=f"目标目录，默认 {DEFAULT_CLIENT_DIR}")
    parser.add_argument("--force", action="store_true", help="已存在时删除并重新下载")
    args = parser.parse_args()
    try:
        ensure_instant_client(platform_name=args.platform, client_dir=args.dir, force=args.force)
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
