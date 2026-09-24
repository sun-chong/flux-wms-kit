#!/usr/bin/env python3
"""
清理 flux-report-builder 执行过程中产生的临时文件。

安全策略（重要）：
  接受 --function-id 参数，仅清理与该功能编号（FUNCTIONID）相关的输出文件，
  避免误删用户其他任务或历史的文件。

清理范围：
  项目 outputs/ 目录：
    - 仅清理匹配 {FUNCTIONID}_* 前缀的文件（如 _CONVERTED.sql、_config.json）
    - 其他文件不受影响
  Skill 本地 outputs/ 目录：
    - 清理所有中间产物（skill 专属目录，不影响项目）
  Skill scripts/ 缓存：
    - __pycache__/、.pyc 文件
  系统临时目录：
    - flux_report_* 相关临时文件

保留内容：
  - outputs/ 下非本次任务的文件
  - .claude/ 下的配置文件
  - src/ 下的源码文件
  - docs/ 下的文档
  - .gitkeep / .gitignore 等占位文件
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path


def get_project_outputs_dir():
    """
    定位项目主 outputs/ 目录。
    脚本位于 .claude/skills/flux-report-builder/scripts/，
    项目根目录为上溯 4 层，再进入 outputs/。
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    return project_root / "outputs"


def get_skill_outputs_dir():
    """定位 skill 本地的 outputs/ 目录（如有）"""
    return Path(__file__).resolve().parent.parent / "outputs"


def get_skill_scripts_dir():
    """定位 skill 本地的 scripts/ 目录"""
    return Path(__file__).resolve().parent


def clean_by_prefix(directory, prefix, label=""):
    """
    清理指定目录下匹配前缀的文件/目录，返回清理的文件列表。
    跳过隐藏的占位文件（.gitkeep、.gitignore）。
    """
    cleaned = []
    if not directory.exists():
        return cleaned

    for item in directory.iterdir():
        if item.name.startswith('.'):
            continue  # 跳过所有隐藏文件（.gitkeep 等）
        if item.name.startswith(prefix):
            try:
                if item.is_file():
                    item.unlink()
                    cleaned.append(str(item))
                elif item.is_dir():
                    shutil.rmtree(item)
                    cleaned.append(str(item))
            except PermissionError:
                print(f"  [警告] 无权限删除：{item}", file=sys.stderr)
            except OSError as e:
                print(f"  [警告] 删除失败 ({e})：{item}", file=sys.stderr)

    return cleaned


def clean_directory(directory, protect_names=None, label=""):
    """
    安全清空目录下所有内容，但保留指定名称的文件/目录。
    仅用于 skill 专属目录（非项目 outputs/）。
    """
    if protect_names is None:
        protect_names = set()

    cleaned = []
    if not directory.exists():
        return cleaned

    for item in directory.iterdir():
        if item.name in protect_names:
            continue
        if item.name.startswith('.') and item.name in {'.gitkeep', '.gitignore'}:
            continue

        try:
            if item.is_file():
                item.unlink()
                cleaned.append(str(item))
            elif item.is_dir():
                shutil.rmtree(item)
                cleaned.append(str(item))
        except PermissionError:
            print(f"  [警告] 无权限删除：{item}", file=sys.stderr)
        except OSError as e:
            print(f"  [警告] 删除失败 ({e})：{item}", file=sys.stderr)

    return cleaned


def clean_pycache_and_pyc(directory, label=""):
    """清理指定目录下的 __pycache__ 和 .pyc 文件"""
    cleaned = []
    if not directory.exists():
        return cleaned

    for pycache in directory.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache)
            cleaned.append(str(pycache))
        except (PermissionError, OSError) as e:
            print(f"  [警告] 删除失败 ({e})：{pycache}", file=sys.stderr)

    for pyc in directory.rglob("*.pyc"):
        try:
            pyc.unlink()
            cleaned.append(str(pyc))
        except (PermissionError, OSError) as e:
            print(f"  [警告] 删除失败 ({e})：{pyc}", file=sys.stderr)

    return cleaned


def main():
    parser = argparse.ArgumentParser(
        description='FLUX WMS 报表构建器 - 临时文件清理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
安全策略：仅清理与 --function-id 相关的输出文件，不影响其他任务的历史文件。

示例：
  python cleanup_temp_files.py --function-id C0104_MY_REPORT
        """
    )
    parser.add_argument(
        '--function-id', required=True,
        help='功能编号 (FUNCTIONID)，仅清理 outputs/ 中与该编号相关的文件'
    )

    args = parser.parse_args()
    function_id = args.function_id
    all_cleaned = []

    # ──────────────────────────────────────────────
    # 区域 1：项目主 outputs/ 目录（安全清理）
    # 仅清理匹配 {FUNCTIONID}_* 前缀的文件
    # ──────────────────────────────────────────────
    project_outputs = get_project_outputs_dir()
    prefix = f"{function_id}_"
    print(f"[区域1] 项目 outputs/ 目录（仅清理 {prefix}* 前缀的文件）：{project_outputs}")
    items = clean_by_prefix(project_outputs, prefix)
    all_cleaned.extend(items)
    print(f"  已清理 {len(items)} 项")

    # ──────────────────────────────────────────────
    # 区域 2：Skill 本地 outputs/ 目录（如有）
    # ──────────────────────────────────────────────
    skill_outputs = get_skill_outputs_dir()
    print(f"[区域2] Skill outputs/ 目录：{skill_outputs}")
    items = clean_directory(skill_outputs)
    all_cleaned.extend(items)
    print(f"  已清理 {len(items)} 项")

    # ──────────────────────────────────────────────
    # 区域 3：Skill scripts/ 目录下的 __pycache__ 和 .pyc
    # ──────────────────────────────────────────────
    skill_scripts = get_skill_scripts_dir()
    print(f"[区域3] Skill scripts/ 缓存清理：{skill_scripts}")
    items = clean_pycache_and_pyc(skill_scripts)
    all_cleaned.extend(items)
    print(f"  已清理 {len(items)} 项")

    # ──────────────────────────────────────────────
    # 区域 4：系统临时目录中与本 skill 相关的文件
    # ──────────────────────────────────────────────
    temp_dir = Path(tempfile.gettempdir())
    print(f"[区域4] 系统临时目录：{temp_dir}")
    temp_patterns = [
        "flux_report_*",
        "generate_form_*",
        "generate_json_*",
        "insert_query_*",
        "tmp*_CONVERTED*",
        "tmp*.sql",
        "tmp*.json",
    ]
    for pat in temp_patterns:
        for f in temp_dir.glob(pat):
            try:
                if f.is_file():
                    f.unlink()
                    all_cleaned.append(str(f))
                elif f.is_dir():
                    shutil.rmtree(f)
                    all_cleaned.append(str(f))
            except (PermissionError, OSError):
                pass
    print(f"  已清理临时目录中相关文件")

    # ──────────────────────────────────────────────
    # 汇总报告
    # ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    if all_cleaned:
        print(f"[完成] 共清理 {len(all_cleaned)} 个临时文件/目录：")
        for item in all_cleaned:
            print(f"  ✓ {item}")
    else:
        print("[完成] 未发现需要清理的临时文件")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()