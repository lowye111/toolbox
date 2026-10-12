#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把仓库内的 git 钩子安装到 .git/hooks（git 不会自动分发钩子，需要手动装一次）。

用法：
    python tools/install_hooks.py
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK_SRC = ROOT / "tools" / "git-hooks"
HOOK_DST = ROOT / ".git" / "hooks"


def main():
    if not (ROOT / ".git").is_dir():
        print("× 当前目录不是 git 仓库，未安装")
        return 1
    if not HOOK_SRC.is_dir():
        print("× 找不到钩子源目录：%s" % HOOK_SRC)
        return 1

    HOOK_DST.mkdir(parents=True, exist_ok=True)
    installed = []
    for src in sorted(HOOK_SRC.iterdir()):
        if not src.is_file():
            continue
        dst = HOOK_DST / src.name
        shutil.copyfile(src, dst)
        # 在 POSIX 上需要可执行位；Windows 下 git 会按 shebang 处理
        try:
            os.chmod(dst, 0o755)
        except Exception:
            pass
        installed.append(src.name)

    if not installed:
        print("× 没有找到可安装的钩子")
        return 1
    print("已安装钩子到 %s：" % HOOK_DST)
    for name in installed:
        print("  -", name)
    print("\n这些钩子会在 git commit 时自动运行，拦截疑似 API Key 的提交。")
    print("如需卸载，删除 .git/hooks/ 下对应文件即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
