# -*- coding: utf-8 -*-
"""工具箱环境检测与配置

- 检查依赖是否安装，缺失时可一键 pip 安装
- 自动检测 conda 训练环境（模型训练工具用）与 yolov5 仓库目录
- 读写根目录 config.json（首次运行自动生成，不纳入 git）
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    "conda_env": "yolov5",  # 模型训练使用的 conda 环境名
    "env_python": "",       # 可选：直接指定该环境的 python.exe 路径（优先级最高）
    "yolov5_dir": "",       # 可选：yolov5 仓库目录（使用 yolov5 系列模型训练/测试时）
    "deepseek_api_key": "",              # 可选：参数扫描工具 AI 识别用的 DeepSeek API Key
    "deepseek_model": "deepseek-flash",  # 可选：DeepSeek 模型名（官方列表：deepseek-flash / deepseek-v4-pro）
    "notes_dir": "",                     # 可选：参数扫描工具说明文件的保存目录（留空=工具目录下 notes 文件夹）
}

# 模块名 -> pip 包名
MODULE_TO_PIP = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "PIL": "Pillow",
}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_config():
    """读取 config.json，不存在则用默认值创建"""
    config = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        else:
            save_config(config)
    except Exception:
        pass
    return config


def save_config(config):
    """保存 config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def missing_modules(modules):
    """返回当前解释器中缺失的模块名列表"""
    missing = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    return missing


def module_available(name):
    """快速判断模块是否可导入（不会真正导入，速度快）"""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def env_missing_modules(python_exe, modules):
    """检查指定解释器中缺失的模块；无法检查时返回 None（视为未知）"""
    try:
        result = subprocess.run(
            [python_exe, "-c", "import " + ", ".join(modules)],
            capture_output=True, timeout=30, creationflags=_NO_WINDOW)
        if result.returncode == 0:
            return []
        missing = []
        for name in modules:
            r = subprocess.run([python_exe, "-c", f"import {name}"],
                               capture_output=True, timeout=30, creationflags=_NO_WINDOW)
            if r.returncode != 0:
                missing.append(name)
        return missing
    except Exception:
        return None


def pip_names(modules):
    """模块名转 pip 包名"""
    return [MODULE_TO_PIP.get(m, m) for m in modules]


def install_in_console(packages, python_exe=None):
    """弹出安装窗口，用 pip 安装指定包"""
    python_exe = python_exe or sys.executable
    try:
        subprocess.Popen([python_exe, "-m", "pip", "install", *packages],
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return True
    except Exception:
        return False


def ensure_modules(modules, title="缺少依赖", parent=None):
    """检查当前解释器依赖；缺失时询问是否自动安装。返回是否已就绪"""
    missing = missing_modules(modules)
    if not missing:
        return True
    from tkinter import messagebox
    pkgs = pip_names(missing)
    if messagebox.askyesno(
            title,
            "缺少以下依赖：\n\n" + "\n".join(pkgs) +
            "\n\n是否现在自动安装？（将弹出安装窗口，完成后重新启动对应工具）",
            parent=parent):
        if not install_in_console(pkgs):
            messagebox.showerror(
                "安装失败",
                "无法启动安装窗口，请手动执行：\n\n"
                f'"{sys.executable}" -m pip install {" ".join(pkgs)}',
                parent=parent)
    return False


def _find_conda_envs():
    """返回 {环境名: python.exe 路径}，探测失败返回空字典"""
    envs = {}
    try:
        result = subprocess.run("conda info --json", shell=True,
                                capture_output=True, timeout=15, creationflags=_NO_WINDOW)
        data = json.loads(result.stdout.decode("utf-8", "ignore"))
        for env_dir in data.get("envs", []):
            name = os.path.basename(os.path.normpath(env_dir))
            python_exe = os.path.join(env_dir, "python.exe")
            if os.path.exists(python_exe):
                envs[name] = python_exe
    except Exception:
        pass

    if not envs:
        # conda 命令不可用时的兜底：扫描常见安装位置
        common_roots = [
            Path.home() / "anaconda3" / "envs",
            Path.home() / "miniconda3" / "envs",
            Path("C:/ProgramData/Anaconda3/envs"),
            Path("C:/ProgramData/miniconda3/envs"),
        ]
        for envs_root in common_roots:
            if envs_root.is_dir():
                for d in envs_root.iterdir():
                    python_exe = d / "python.exe"
                    if python_exe.exists():
                        envs[d.name] = str(python_exe)
    return envs


def find_env_python(env_name=None):
    """定位训练环境的 python.exe：优先 config.json 指定，其次按环境名匹配，最后自动挑选 yolo 环境"""
    config = load_config()
    user_python = config.get("env_python", "")
    if user_python and os.path.exists(user_python):
        return user_python

    env_name = env_name or config.get("conda_env", "yolov5")
    envs = _find_conda_envs()
    if not envs:
        return None

    for name, python_exe in envs.items():
        if name.lower() == str(env_name).lower():
            return python_exe

    yolo_envs = [(n, p) for n, p in envs.items() if "yolo" in n.lower()]
    if yolo_envs:
        yolo_envs.sort(key=lambda item: (item[0].lower() not in ("yolov5", "yolo"), item[0].lower()))
        return yolo_envs[0][1]
    return None


def find_yolov5_dir():
    """自动查找 yolov5 仓库目录（需包含 train.py）；找不到返回 None"""
    config = load_config()
    user_dir = config.get("yolov5_dir", "")
    if user_dir and (Path(user_dir) / "train.py").exists():
        return user_dir

    candidates = []
    for base in [Path.home() / "Desktop", Path.home(), ROOT]:
        if base.is_dir():
            try:
                candidates.extend(d for d in sorted(base.glob("yolov5*"))
                                  if d.is_dir() and (d / "train.py").exists())
            except Exception:
                pass
    return str(candidates[0]) if candidates else None