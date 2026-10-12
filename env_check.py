# -*- coding: utf-8 -*-
"""工具箱环境检测与配置

- 检查依赖是否安装，缺失时可一键 pip 安装
- 自动检测 conda 训练环境（模型训练工具用）与 yolov5 仓库目录
- 读写根目录 config.json（首次运行自动生成，不纳入 git）
"""
import base64
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

# ==================== API Key 保护 ====================
# 目的：即使 config.json 被误提交/误分享，里面的 Key 也不能被别人直接拿去用。
#
# 优先级（高 → 低）：
#   1. 环境变量 DEEPSEEK_API_KEY   —— 推荐；Key 完全不落盘
#   2. config.json 中的密文 *_enc  —— 用 Windows DPAPI 加密，绑定当前 Windows 账户
#   3. config.json 中的明文（旧格式）—— 仍可读，但首次保存会自动迁移成密文
#
# 关键点：DPAPI 的密钥由 Windows 用当前用户账户托管，密文拷到别的机器/别的账户
# 无法解密。因此这不是"把密钥和密文放一起"的假加密。
ENV_API_KEY = "DEEPSEEK_API_KEY"
ENC_FIELD = "deepseek_api_key_enc"   # config.json 里保存密文的字段
_DPAPI_ENTROPY = b"toolbox/deepseek-api-key/v1"   # 用途绑定，别的程序拿到密文也解不开


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_libs():
    """按需加载 crypt32/kernel32（仅 Windows 有），失败返回 None"""
    if not sys.platform.startswith("win"):
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        return crypt32, kernel32
    except Exception:
        return None


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _blob_bytes(blob):
    return ctypes.string_at(blob.pbData, blob.cbData)


def encrypt_secret(text):
    """用 Windows DPAPI 加密，返回 base64 字符串；不可用时返回 None"""
    libs = _dpapi_libs()
    if not libs or not text:
        return None
    crypt32, kernel32 = libs
    try:
        blob_in, _k1 = _blob(text.encode("utf-8"))
        blob_ent, _k2 = _blob(_DPAPI_ENTROPY)
        blob_out = _DATA_BLOB()
        ok = crypt32.CryptProtectData(ctypes.byref(blob_in), "toolbox", ctypes.byref(blob_ent),
                                      None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return base64.b64encode(_blob_bytes(blob_out)).decode("ascii")
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def decrypt_secret(token):
    """解密 encrypt_secret 的产物；失败（换机器/换账户/被篡改）返回 None"""
    libs = _dpapi_libs()
    if not libs or not token:
        return None
    crypt32, kernel32 = libs
    try:
        blob_in, _k1 = _blob(base64.b64decode(token))
        blob_ent, _k2 = _blob(_DPAPI_ENTROPY)
        blob_out = _DATA_BLOB()
        ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
                                       None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return _blob_bytes(blob_out).decode("utf-8")
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def protect_config_secret(config):
    """把 config 里的明文 deepseek_api_key 转成密文 *_enc，返回是否有改动。

    仅在本机支持 DPAPI 且确实存在明文时改写；转换成功后删除明文字段。
    """
    plain = (config.get("deepseek_api_key") or "").strip()
    if not plain:
        return False
    token = encrypt_secret(plain)
    if not token:
        return False          # 无法加密就保留明文，不破坏可用性
    config[ENC_FIELD] = token
    config["deepseek_api_key"] = ""
    return True


def get_api_key(config=None):
    """按 环境变量 → 密文 → 明文 的顺序取 API Key（返回空串表示未配置）"""
    env_key = (os.environ.get(ENV_API_KEY) or "").strip()
    if env_key:
        return env_key
    cfg = config if config is not None else load_config()
    token = (cfg.get(ENC_FIELD) or "").strip()
    if token:
        decrypted = decrypt_secret(token)
        if decrypted:
            return decrypted.strip()
    return (cfg.get("deepseek_api_key") or "").strip()

DEFAULT_CONFIG = {
    "conda_env": "yolov5",  # 模型训练使用的 conda 环境名
    "env_python": "",       # 可选：直接指定该环境的 python.exe 路径（优先级最高）
    "yolov5_dir": "",       # 可选：yolov5 仓库目录（使用 yolov5 系列模型训练/测试时）
    "deepseek_api_key": "",              # 已废弃的明文字段；请改用环境变量 DEEPSEEK_API_KEY
    "deepseek_api_key_enc": "",          # 加密后的 API Key（由工具自动生成，绑定本机 Windows 账户）
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

# ---- 缓存 ----
# load_config 会被 model_train 的预览函数在每次按键时调用，_find_conda_envs 会执行
# `conda info --json`（最长 15 秒）。这里做缓存，避免重复读盘与反复启动子进程。
_CONFIG_CACHE = {"key": None, "data": None}
_CONDA_ENVS_CACHE = {"time": 0.0, "data": None}
_YOLOV5_DIR_CACHE = {"time": 0.0, "data": None}
_CONDA_ENVS_TTL = 60.0  # 秒；conda 环境在会话期间很少变化


def _config_cache_key():
    """用 mtime+size 作为缓存键：既能省掉重复读盘，也能感知外部手工修改"""
    try:
        st = CONFIG_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def load_config():
    """读取 config.json，不存在则用默认值创建（带缓存，文件变化时自动失效）"""
    key = _config_cache_key()
    if key is not None and _CONFIG_CACHE["key"] == key:
        return dict(_CONFIG_CACHE["data"])

    config = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config.update(json.load(f))
            # 老版本留下的明文 Key：读到时顺手迁移成密文，避免明文长期留在磁盘上
            if (config.get("deepseek_api_key") or "").strip() and not (config.get(ENC_FIELD) or "").strip():
                migrated = dict(config)
                if protect_config_secret(migrated):
                    save_config(migrated)
                    config = migrated
        else:
            save_config(config)
    except Exception:
        pass

    _CONFIG_CACHE["key"] = _config_cache_key()
    _CONFIG_CACHE["data"] = dict(config)
    return config


def save_config(config):
    """保存 config.json（成功后让配置缓存失效）

    保存前会尝试把明文 API Key 加密成密文，避免明文落在磁盘上。
    """
    try:
        config = dict(config)
        protect_config_secret(config)   # 明文 -> 密文（不可加密时保持原样）
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        return False
    _CONFIG_CACHE["key"] = _config_cache_key()
    _CONFIG_CACHE["data"] = dict(config)
    return True


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
    """返回 {环境名: python.exe 路径}，探测失败返回空字典（结果带 TTL 缓存）"""
    now = time.time()
    if _CONDA_ENVS_CACHE["data"] is not None and now - _CONDA_ENVS_CACHE["time"] < _CONDA_ENVS_TTL:
        return dict(_CONDA_ENVS_CACHE["data"])

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

    # 探测到结果才缓存；空结果也缓存，避免反复启动 conda 拖慢界面
    _CONDA_ENVS_CACHE["time"] = now
    _CONDA_ENVS_CACHE["data"] = dict(envs)
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
    """自动查找 yolov5 仓库目录（需包含 train.py）；找不到返回 None（带 TTL 缓存）"""
    now = time.time()
    if _YOLOV5_DIR_CACHE["time"] and now - _YOLOV5_DIR_CACHE["time"] < _CONDA_ENVS_TTL:
        return _YOLOV5_DIR_CACHE["data"]

    result = _locate_yolov5_dir()
    _YOLOV5_DIR_CACHE["time"] = now
    _YOLOV5_DIR_CACHE["data"] = result
    return result


def _locate_yolov5_dir():
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