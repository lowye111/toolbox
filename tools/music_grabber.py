# -*- coding: utf-8 -*-
"""
抓歌打包器 —— 工具箱入口
==========================
在「工具箱」里点卡片启动。

它做两件事：
  1. 找出「哪个 Python 装了抓歌引擎需要的依赖」
  2. 用那个解释器拉起同目录下 music_grabber/app.pyw

为什么需要这一层：
  工具箱主菜单用 `sys.executable` 启动子工具，也就是「跑工具箱的那个 Python」。
  本机工具箱跑在 miniconda 的 Python 3.8 上，而抓歌引擎依赖的
  musicdl / imageio-ffmpeg 装在 DSH 的 Python 3.12 里 —— 不是同一个解释器。
  直接注册 app.pyw 会在 3.8 上因缺包崩溃，所以这里做一次解释器转接。

探测顺序：
  1. 本目录 config.json 里手动指定的 grabber_python
  2. DSH 运行时 Python（依赖目前装在这里）
  3. 当前解释器（若依赖齐全，说明装在同一个环境）
  4. PATH 上的 python
全都不可用时，弹窗给出可直接照做的修复命令。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, 'music_grabber')
APP = os.path.join(PKG, 'app.pyw')
CONFIG = os.path.join(HERE, 'config.json')

# 引擎需要的第三方模块
NEEDED = ['musicdl', 'imageio_ffmpeg']

# DSH 运行时 Python（依赖目前装在这里）。
# 路径按当前用户目录推导，避免把用户名写死在代码里（换机器也能用）。
DSH_PY = os.path.join(
    os.path.expanduser('~'), '.dsh', 'dsh-runtimes', 'dsh-primary-runtime',
    'dependencies', 'python', 'python.exe')


def load_config():
    for path in (CONFIG, os.path.join(os.path.dirname(HERE), 'config.json')):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def python_has_deps(exe):
    """检查指定解释器是否具备全部依赖。
    注意：必须 import importlib.util —— 只 import importlib 拿不到 find_spec。"""
    if not exe or not os.path.exists(exe):
        return False
    code = (
        "import importlib.util, sys\n"
        "mods=%r\n"
        "bad=[m for m in mods if importlib.util.find_spec(m) is None]\n"
        "sys.exit(0 if not bad else 3)\n" % (NEEDED,)
    )
    try:
        r = subprocess.run([exe, '-c', code], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def candidate_pythons():
    """按优先级列出候选解释器（含 pythonw 变体）。"""
    cfg = load_config()
    raw = []
    for key in ('grabber_python', 'env_python', 'python'):
        v = cfg.get(key)
        if isinstance(v, str) and v.strip():
            raw.append(v.strip())
    raw.append(DSH_PY)
    raw.append(sys.executable)

    # PATH 上的 python
    import shutil
    p = shutil.which('python')
    if p:
        raw.append(p)

    seen, out = set(), []
    for p in raw:
        if not p:
            continue
        variants = [p]
        base = os.path.basename(p).lower()
        if base == 'python.exe':
            variants.append(os.path.join(os.path.dirname(p), 'pythonw.exe'))
        elif base == 'pythonw.exe':
            variants.append(os.path.join(os.path.dirname(p), 'python.exe'))
        for v in variants:
            if not os.path.exists(v):
                continue
            key = os.path.normcase(os.path.abspath(v))
            if key not in seen:
                seen.add(key)
                out.append(v)
    return out


def pick_python():
    """挑出第一个依赖齐全、且优先无控制台窗口的解释器。"""
    plain = None
    for p in candidate_pythons():
        if not python_has_deps(p):
            continue
        if os.path.basename(p).lower().startswith('pythonw'):
            return p
        if plain is None:
            plain = p
    return plain


def show_error(msg):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror('抓歌打包器 —— 无法启动', msg)
        r.destroy()
    except Exception:
        print(msg, file=sys.stderr)
        try:
            input('按回车关闭…')
        except Exception:
            pass


def main():
    if not os.path.exists(APP):
        show_error(
            '找不到程序文件：\n%s\n\n'
            'music_grabber 子目录应与本文件放在一起。' % APP)
        return 1

    exe = pick_python()
    if not exe:
        cands = candidate_pythons()
        show_error(
            '找不到具备所需依赖的 Python。\n\n'
            '抓歌引擎需要这两个包：\n'
            '    %s\n\n'
            '已检查：\n%s\n\n'
            '解决办法（任选其一）：\n\n'
            '1) 给某个 Python 装上依赖：\n'
            '   "<python路径>" -m pip install musicdl imageio-ffmpeg\n\n'
            '2) 在 toolbox\\config.json 里指定一个已装好依赖的解释器：\n'
            '   {"grabber_python": "C:\\\\路径\\\\python.exe"}'
            % ('   '.join(NEEDED),
               '\n'.join('   ' + c for c in cands) or '   （无可用解释器）'))
        return 1

    try:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.Popen([exe, APP], cwd=PKG, creationflags=flags)
    except Exception as e:
        # pythonw 失败就退回同名 python
        alt = exe.replace('pythonw.exe', 'python.exe')
        try:
            subprocess.Popen([alt if os.path.exists(alt) else exe, APP], cwd=PKG)
        except Exception as e2:
            show_error('启动失败：\n%s\n%s' % (e, e2))
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
