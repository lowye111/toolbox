import os
import re
import sys
import json
import codecs
import shutil
import hashlib
import queue
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# 引入根目录的环境检测模块（复用 config.json）与统一 UI 主题
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui_theme
try:
    import env_check
except Exception:
    env_check = None

VERSION = "AI 识别版"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODELS_URL = "https://api.deepseek.com/models"

# 界面上可选的模型（也可手工输入其它名字）
KNOWN_MODELS = ["deepseek-flash", "deepseek-v4-pro"]


def debug_log(message):
    """调试输出：pythonw 启动时 sys.stdout 为 None，直接 print 会抛异常中断扫描，这里做保护"""
    if sys.stdout is None:
        return
    try:
        print(message)
    except Exception:
        pass

# 强化匹配规则，确保单冒号参数不遗漏
PATTERNS = {
    "naked_param": re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+)'),
    "macro_define": re.compile(r'^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+([^\n]+)'),
    "global_const": re.compile(r'^\s*(static\s+const|const)\s+\w+\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+)'),
    "global_var": re.compile(r'^\s*\w+\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+)'),
    # 新增：单冒号参数匹配
    "colon_param": re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^;\n]+)'),
}

EXCLUDE_PATTERNS = [
    re.compile(r'\benum\b'), re.compile(r'\bcase\b'), re.compile(r'\bfor\b'),
    re.compile(r'\bif\b'), re.compile(r'\breturn\b'),
    re.compile(r'\b(P|K|Q|R|X|result)\s*='),
]


def read_file_with_meta(path):
    """读取文件，返回 (lines, encoding)。

    保留原始行尾（LF/CRLF 不被翻译）并记录原编码，供 write_file_lines 原样写回，
    避免把 GBK 源文件静默转成 UTF-8、或把 LF 文件整篇改成 CRLF。
    """
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(codecs.BOM_UTF8):
        try:
            return raw.decode('utf-8-sig').splitlines(keepends=True), 'utf-8-sig'
        except UnicodeDecodeError:
            pass
    for enc in ('utf-8', 'gbk'):
        try:
            return raw.decode(enc).splitlines(keepends=True), enc
        except UnicodeDecodeError:
            continue
    # 兜底：仍按 utf-8 强解，保证工具可用（替换字符只在极端情况下出现）
    return raw.decode('utf-8', 'replace').splitlines(keepends=True), 'utf-8'


def read_file_lines(path):
    """读取文件行：utf-8 优先，兼容 gbk（Windows 中文文件）"""
    return read_file_with_meta(path)[0]


def write_file_lines(path, lines, encoding):
    """按原编码、原行尾写回文件；写前先备份为同名 .bak。

    用二进制写入，避免 text 模式把 LF 翻译成 CRLF。
    """
    data = "".join(lines).encode(encoding)
    try:
        shutil.copy2(path, path + ".bak")   # 每次保存前留一份原始备份
    except Exception:
        pass
    # 原子写：先写临时文件再替换，避免写到一半崩溃/断电把用户源码留成半截
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def _find_value_end(line, start, colon_mode):
    """从取值起点扫描到该取值结束位置。

    跳过字符串/字符字面量与括号嵌套，遇到行内注释（// 或 #）或语句结束符即停：
    - C/C++ 风格（colon_mode=False）：以 depth==0 的 ';' 结束
    - 冒号风格（YAML/INI，colon_mode=True）：以 depth==0 的 ',' 或行尾结束
    """
    i = start
    n = len(line)
    quote = None
    depth = 0
    while i < n:
        ch = line[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '"\'':
            quote = ch
            i += 1
            continue
        if ch == '#' or (ch == '/' and i + 1 < n and line[i + 1] == '/'):
            return i
        if ch in '([{':
            depth += 1
            i += 1
            continue
        if ch in ')]}':
            if depth > 0:
                depth -= 1
            i += 1
            continue
        if depth == 0:
            if ch == ';' and not colon_mode:
                return i
            if ch == ',' and colon_mode:
                return i
        i += 1
    return n


def _splice_value(line, value_start, new_value, colon_mode):
    """把 [value_start, 取值末尾) 换成 new_value，其余（同行其它语句、注释、空白）原样保留"""
    end = _find_value_end(line, value_start, colon_mode)
    while end > value_start and line[end - 1] in ' \t':
        end -= 1      # 取值后的空白留给原行，避免吞掉间隔
    return line[:value_start] + new_value + line[end:]


def replace_param_value(line, name, new_value):
    """只替换指定参数的取值片段，返回新行；无法安全定位时返回 None。

    支持 `NAME = v`、`NAME: v`（YAML/INI）与 `#define NAME v` 三种形式。
    """
    esc = re.escape(name)

    # 1) 宏：#define NAME value（没有等号）
    m = re.match(r'(\s*#\s*define\s+)' + esc + r'(?![A-Za-z0-9_])([ \t]+)', line)
    if m:
        value_start = m.end()
        if value_start < len(line) and line[value_start] == '(':
            return None      # 函数式宏（#define F(x) ...），不做自动改写
        return _splice_value(line, value_start, new_value, colon_mode=False)

    # 2) NAME = value / NAME: value（跳过 ==、!=、<=、>= 这类比较）
    for m in re.finditer(r'(?<![A-Za-z0-9_])' + esc + r'(?![A-Za-z0-9_])[ \t]*(==|!=|<=|>=|=|:)[ \t]*', line):
        sep = m.group(1)
        if sep in ('==', '!=', '<=', '>='):
            continue
        return _splice_value(line, m.end(), new_value, colon_mode=(sep == ':'))
    return None


def make_param(path, line_num, type_name, name, value, original_line):
    """构造统一结构的参数项"""
    return {
        "file_path": path, "file_name": os.path.basename(path),
        "line": line_num, "type": type_name,
        "name": name, "value": value, "original_line": original_line,
        "new_value": None, "is_modified": False, "is_priority": False,
        "hidden": False,
        "ai_note": "", "ai_filtered": False, "ai_recommend": False,
        "note_manual": "",
        # 已成功写回磁盘时记录"原值"，供调参日志统计真正落盘的修改
        "saved_from": None,
    }


def scan_file(path):
    results = []
    try:
        lines = read_file_lines(path)
    except Exception as e:
        debug_log(f"读取文件失败：{path} - {e}")
        return results

    in_enum = False
    brace_count = 0
    line_num = 1

    for line in lines:
        stripped = line.strip()
        # 跳过注释和空行；# 开头的行跳过（保留 #define，兼容 YAML/INI 的 # 注释）
        if not stripped or stripped.startswith(('//', '/*')):
            line_num += 1
            continue
        if stripped.startswith('#') and not stripped.startswith('#define'):
            line_num += 1
            continue

        # ===================== 跳过双冒号 :: =====================
        if "::" in line:
            line_num += 1
            continue
        # =========================================================

        # 跳过enum块
        if 'enum' in stripped:
            in_enum = True
        if '{' in stripped:
            brace_count += 1
        if '}' in stripped:
            brace_count -= 1
            if brace_count <= 0:
                in_enum = False
        if in_enum:
            line_num += 1
            continue

        # 跳过排除模式
        if any(p.search(line) for p in EXCLUDE_PATTERNS):
            line_num += 1
            continue

        # 匹配裸参数（= 格式）
        match = PATTERNS['naked_param'].search(line)
        if match:
            name = match.group(1).strip()
            value = match.group(2).rstrip(';').strip()
            if name and value and name != value:
                results.append(make_param(path, line_num, "变量", name, value, line))
            line_num += 1
            continue

        # ===================== 匹配单冒号参数 =====================
        match = PATTERNS['colon_param'].search(line)
        if match:
            name = match.group(1).strip()
            value = match.group(2).strip()
            if name and value and name != value:
                results.append(make_param(path, line_num, "参数", name, value, line))
            line_num += 1
            continue
        # =========================================================

        # 匹配其他类型参数（= 格式）
        for typ, reg in PATTERNS.items():
            if typ in ("naked_param", "colon_param"):
                continue
            match = reg.search(line)
            if not match:
                continue

            if typ == "macro_define":
                name = match.group(1).strip()
                value = match.group(2).strip()
                type_name = "宏"
            elif typ == "global_const":
                name = match.group(2).strip()
                value = match.group(3).strip()
                type_name = "常量"
            else:
                # global_var 只有两组：名称、值（原代码取错分组，导致顶层变量被漏掉）
                name = match.group(1).strip()
                value = match.group(2).strip()
                type_name = "全局变量"

            value = value.rstrip(';').strip()
            if name and value and name != value:
                results.append(make_param(path, line_num, type_name, name, value, line))
            break

        line_num += 1

    # 打印扫描结果，方便调试（可删除）
    debug_log(f"文件 {os.path.basename(path)} 扫描到 {len(results)} 个参数")
    return results


def match_param_line(line):
    """对单行尝试匹配参数，返回 (类型, 名称, 值) 或 None（用于核对 AI 补充发现的行）"""
    if not line.strip():
        return None
    m = PATTERNS['macro_define'].search(line)
    if m:
        name, value = m.group(1).strip(), m.group(2).strip()
        return ("宏", name, value) if name and value and name != value else None
    m = PATTERNS['naked_param'].search(line)
    if m:
        name, value = m.group(1).strip(), m.group(2).rstrip(';').strip()
        return ("变量", name, value) if name and value and name != value else None
    m = PATTERNS['colon_param'].search(line)
    if m:
        name, value = m.group(1).strip(), m.group(2).strip()
        return ("参数", name, value) if name and value and name != value else None
    m = PATTERNS['global_const'].search(line)
    if m:
        name, value = m.group(2).strip(), m.group(3).strip()
        if name and value and name != value:
            return ("常量", name, value)
    m = PATTERNS['global_var'].search(line)
    if m:
        name, value = m.group(1).strip(), m.group(2).strip()
        if name and value and name != value:
            return ("全局变量", name, value)
    # 宽松兜底：处理 "static float kp = 1.2;" 这类多修饰词形式（仅用于核对 AI 补充发现）
    m = (re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!=)([^;{}]+?)\s*;?\s*$', line)
         or re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?![=:])([^;{}]+?)\s*;?\s*$', line))
    if m:
        name, value = m.group(1).strip(), m.group(2).strip()
        if name and value and name != value:
            return ("变量", name, value)
    return None


# 扫描时跳过的目录（ROS 构建产物 devel/build/install，以及版本库/缓存/依赖目录，
# 避免扫到自动生成的样板文件或第三方代码）
SKIP_DIRS = {
    "devel", "build", "install",
    ".git", ".svn", ".hg", "__pycache__", "node_modules",
    ".idea", ".vscode", ".venv", "venv", "site-packages",
}


def scan_folder(folder):
    exts = ('.h', '.hpp', '.hh', '.hxx', '.c', '.cpp', '.cc', '.cxx', '.ino',
            '.yaml', '.yml', '.ini', '.cfg', '.conf')
    param_map = {}
    all_files = []

    for root, dirs, files in os.walk(folder):
        # 原地剪枝：跳过构建产物目录（不区分大小写）
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
        for fn in files:
            if fn.lower().endswith(exts):
                fp = os.path.abspath(os.path.join(root, fn))
                all_files.append(fp)
                params = scan_file(fp)
                if params:
                    param_map[fp] = params
                else:
                    # 即使无参数也保留文件记录
                    param_map[fp] = []

    return param_map, all_files


def group_files(files, threshold=10):
    """按扩展名分组：数量超过阈值的类型各自成组（如 ".cpp"），其余合并到"其他文件"。
    未达到"至少一个类型超阈值 + 至少两个组"时返回空列表（保持平铺显示）。"""
    if not files:
        return []
    by_ext = {}
    for fp in files:
        ext = os.path.splitext(fp)[1].lower() or "无扩展名"
        by_ext.setdefault(ext, []).append(fp)
    groups = []
    others = []
    for ext in sorted(by_ext):
        flist = by_ext[ext]
        if len(flist) > threshold:
            groups.append((ext, flist))
        else:
            others.extend(flist)
    if others:
        groups.append(("其他文件", others))
    if len(groups) < 2:
        return []
    return groups


def save_param(item, new_value):
    fp = item["file_path"]
    line_idx = item["line"] - 1
    name = item["name"]

    try:
        lines, encoding = read_file_with_meta(fp)
    except Exception as e:
        messagebox.showerror("错误", f"读取文件失败：{e}")
        return False

    if line_idx < 0 or line_idx >= len(lines):
        messagebox.showerror("错误", "行号超出范围")
        return False

    line = lines[line_idx]
    new_line = replace_param_value(line, name, new_value)
    if new_line is None:
        messagebox.showerror("错误", f"未找到参数 {name} 的可替换取值位置（该行可能已被外部修改，或该宏是函数式宏）")
        return False

    lines[line_idx] = new_line

    try:
        write_file_lines(fp, lines, encoding)
    except Exception as e:
        messagebox.showerror("错误", f"保存文件失败：{e}")
        return False

    return True


def generate_tune_log(param_map, quiet=False):
    """生成调参日志：统计本次真正写回磁盘的修改（saved_from 非空）。

    quiet=True 时（关闭窗口自动调用）没有任何修改就静默返回，不弹窗。
    """
    modified = []
    for params in param_map.values():
        for p in params:
            if p.get("saved_from") is not None and p["saved_from"] != p["value"]:
                modified.append(p)

    if not modified:
        if not quiet:
            messagebox.showinfo("提示", "本次未修改任何参数")
        return

    today = datetime.now().strftime("%m%d")
    log_count = 1
    while os.path.exists(f"调参日志{today}_第{log_count}次调参.txt"):
        log_count += 1

    fname = f"调参日志{today}_第{log_count}次调参.txt"
    try:
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(f"========== 调参日志 ==========\n")
            f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"修改总数：{len(modified)}\n\n")
            for i, p in enumerate(modified, 1):
                f.write(f"【{i}】\n文件：{p['file_name']}\n参数：{p['name']}\n"
                        f"原值：{p['saved_from']}\n新值：{p['value']}\n\n")
        if not quiet:
            messagebox.showinfo("成功", f"日志已生成：{fname}")
    except Exception as e:
        if not quiet:
            messagebox.showerror("错误", f"日志生成失败：{e}")


# ==================== AI 识别（DeepSeek） ====================

def get_ai_settings():
    """读取 API Key 与模型名。

    Key 的来源优先级（见 env_check）：环境变量 DEEPSEEK_API_KEY > config.json 密文 > 明文。
    """
    key, model = "", "deepseek-flash"
    if env_check:
        cfg = env_check.load_config()
        key = env_check.get_api_key(cfg)
        model = (cfg.get("deepseek_model") or "deepseek-flash").strip()
    return key, model


def key_source():
    """返回当前 Key 的来源说明，供界面提示用"""
    if not env_check:
        return "unavailable"
    if (os.environ.get(env_check.ENV_API_KEY) or "").strip():
        return "env"
    cfg = env_check.load_config()
    if (cfg.get(env_check.ENC_FIELD) or "").strip():
        return "encrypted"
    if (cfg.get("deepseek_api_key") or "").strip():
        return "plain"
    return "none"


def mask_key(key):
    """把 Key 打码显示（只留前 6 位和后 4 位）"""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 12:
        return key[:2] + "*" * max(0, len(key) - 2)
    return key[:6] + "…" + key[-4:]


def save_ai_settings(key, model):
    """保存 API Key 与模型名到 config.json，返回 (是否成功, 说明文字)。

    写盘时会由 env_check.save_config 自动把明文 Key 加密成密文
    （DPAPI，绑定本机 Windows 账户），不会以明文留在磁盘上。
    """
    if not env_check:
        return False, "缺少 env_check 模块，无法保存配置"
    cfg = env_check.load_config()
    cfg["deepseek_model"] = (model or "deepseek-flash").strip() or "deepseek-flash"

    key = (key or "").strip()
    if key:
        cfg["deepseek_api_key"] = key      # save_config 内会自动加密并清空该字段
    ok = env_check.save_config(cfg)
    if not ok:
        return False, "写入 config.json 失败（文件可能被占用或目录不可写）"

    # 校验密文确实写进去了
    if key and not (env_check.load_config().get(env_check.ENC_FIELD) or "").strip():
        return False, "Key 已保存但加密失败，请检查系统 DPAPI 是否可用"
    return True, "已保存"


def test_api_connection(api_key, model):
    """测试 API Key 是否可用，返回 (是否可用, 说明文字)"""
    if not (api_key or "").strip():
        return False, "未填写 API Key"
    req = urllib.request.Request(
        DEEPSEEK_MODELS_URL,
        headers={"Authorization": "Bearer " + api_key.strip()},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # 把服务端的原始提示带出来，并说明常见原因：Key 被轮换/删除、复制不全、多了空格
            detail = ""
            try:
                raw = e.read().decode("utf-8", "ignore")
                info = json.loads(raw).get("error", {})
                detail = (info.get("message") or "").strip()
            except Exception:
                pass
            msg = f"Key 无效或已失效（HTTP {e.code}）"
            if detail:
                msg += f"\n服务端返回：{detail}"
            msg += ("\n\n请确认：① 该 Key 是否已在服务商后台被轮换或删除；"
                    "② 是否复制完整（无多余空格）；③ 账号是否欠费/受限。")
            return False, msg
        return False, f"请求失败 HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"网络错误：{e.reason}"
    except Exception as e:
        return False, f"请求异常：{e}"

    ids = [d.get("id") for d in (body.get("data") or []) if isinstance(d, dict)]
    if ids and model not in ids:
        return True, f"Key 可用，但当前模型「{model}」不在可用列表（{', '.join(ids[:4])}）"
    return True, "Key 可用" + (f"（可用模型：{', '.join(ids[:3])}）" if ids else "")


# ==================== 参数说明（手动备注，集中保存） ====================

def get_notes_dir():
    """说明文件的保存目录：config.json 的 notes_dir，留空则用工具目录下的 notes 文件夹"""
    if env_check:
        cfg = env_check.load_config()
        d = (cfg.get("notes_dir") or "").strip()
        if d:
            return d
        return str(env_check.ROOT / "notes")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notes")


def workspace_notes_path(folder):
    """按工作区路径生成说明文件：<说明目录>/<目录名>_<路径hash>.json（同一工作区固定同名，便于自动加载）"""
    folder = os.path.abspath(folder)
    base = os.path.basename(os.path.normpath(folder)) or "workspace"
    tag = hashlib.md5(folder.lower().encode("utf-8")).hexdigest()[:8]
    return os.path.join(get_notes_dir(), f"{base}_{tag}.json")


def notes_param_key(file_path, folder):
    """说明条目的键：工作区相对路径::参数名（不用行号，代码增删行后依然有效）"""
    try:
        rel = os.path.relpath(file_path, folder)
    except Exception:
        rel = file_path
    return rel.replace("\\", "/")


def load_notes(notes_path):
    """读取说明文件，返回 {键: 说明}；失败返回空字典"""
    try:
        with open(notes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("notes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_atomic(path, payload):
    """原子写 JSON：先写临时文件再替换，避免崩溃时把说明/会话文件留成半截损坏"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False


def save_notes(notes_path, notes):
    """保存说明文件（自动创建目录），成功返回 True"""
    return _write_json_atomic(notes_path, {"version": 1, "notes": notes})


def workspace_session_path(folder):
    """会话状态文件：与说明文件同目录，命名 <目录名>_<hash>_session.json"""
    folder = os.path.abspath(folder)
    base = os.path.basename(os.path.normpath(folder)) or "workspace"
    tag = hashlib.md5(folder.lower().encode("utf-8")).hexdigest()[:8]
    return os.path.join(get_notes_dir(), f"{base}_{tag}_session.json")


def load_session(session_path):
    """读取会话状态文件（上次保留的文件/置顶/隐藏），失败返回空字典"""
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_session_file(session_path, session):
    """保存会话状态文件（自动创建目录），成功返回 True"""
    return _write_json_atomic(session_path, {"version": 1, **session})


def _ssl_context():
    """优先用 certifi 证书（requests 的证书包），失败则用系统默认"""
    try:
        import ssl
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def call_deepseek(file_text, candidates_text, api_key, model):
    """调用 DeepSeek 分析文件，返回解析后的 JSON 字典"""
    system_prompt = "你是嵌入式 C/C++ 代码参数分析助手，只输出 JSON，不要输出其它内容。"
    user_prompt = f"""下面是一个源文件的全部内容（行号: 内容）：
{file_text}

正则预筛出的候选参数（行号: 参数名）：
{candidates_text}

请逐一判断每个候选行是否适合作为"可调参数"（tunable），按 JSON 返回：
{{
  "params": [
    {{"line": 12, "name": "SPEED_KP", "tunable": true, "note": "速度环比例系数", "recommend": true}}
  ]
}}

要求：
1. tunable=false：函数体内的临时变量、循环变量、中间计算、外设寄存器/结构体成员赋值、状态机内部变量等不适合手动调节的；
2. note：不超过 12 个字的中文用途说明（如"速度环比例系数"）；
3. recommend：全文件最值得调节的参数，最多推荐 5 个；
4. 只针对候选清单里的行；如果你发现清单漏掉了明显的可调参数，也可以补充返回；
5. 严格输出 JSON。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("API Key 无效（401），请检查环境变量 DEEPSEEK_API_KEY 或 config.json 中的 Key")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        raise RuntimeError(f"请求失败 HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误：{e.reason}")

    content = body["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) >= 3:
            content = parts[1]
            if content.lower().startswith("json"):
                content = content[4:]
        content = content.strip()
    return json.loads(content)


def build_numbered_text(lines, params, whole_file_limit=800, window=12):
    """生成发给 AI 的文件文本：小文件发全文，大文件只发候选行附近的窗口"""
    if len(lines) <= whole_file_limit:
        return "\n".join(f"{i + 1}: {t.rstrip()}" for i, t in enumerate(lines))

    cand_lines = sorted({p["line"] for p in params})
    blocks = []
    for ln in cand_lines:
        start = max(1, ln - window)
        end = min(len(lines), ln + window)
        if blocks and start <= blocks[-1][1] + 1:
            blocks[-1][1] = max(blocks[-1][1], end)
        else:
            blocks.append([start, end])

    out = []
    for idx, (s, e) in enumerate(blocks):
        if idx:
            out.append(f"... (省略 {blocks[idx - 1][1] + 1}~{s - 1} 行)")
        out.extend(f"{i}: {lines[i - 1].rstrip()}" for i in range(s, e + 1))
    return "\n".join(out)


def apply_ai_result(params, ai_data, lines=None, path="", ):
    """把 AI 结果合并进参数列表；返回 (过滤数, 补充数, 推荐数)"""
    by_line = {p["line"]: p for p in params}
    filtered = added = recommended = 0
    for item in ai_data.get("params", []):
        try:
            line = int(item.get("line"))
        except (TypeError, ValueError):
            continue
        note = str(item.get("note") or "").strip()
        if line in by_line:
            p = by_line[line]
            p["ai_filtered"] = item.get("tunable") is False
            if note:
                p["ai_note"] = note
            p["ai_recommend"] = bool(item.get("recommend"))
            if p["ai_filtered"]:
                filtered += 1
            if p["ai_recommend"]:
                recommended += 1
        elif item.get("tunable") and lines and 1 <= line <= len(lines):
            # AI 补充发现：与真实文件行核对后再加入，防止幻觉
            matched = match_param_line(lines[line - 1])
            if matched:
                type_name, name, value = matched
                new_p = make_param(path, line, type_name, name, value, lines[line - 1])
                new_p["ai_note"] = note
                new_p["ai_recommend"] = bool(item.get("recommend"))
                params.append(new_p)
                added += 1
                if new_p["ai_recommend"]:
                    recommended += 1
    params.sort(key=lambda x: x["line"])
    return filtered, added, recommended


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"参数编辑工具 {VERSION}")
        ui_theme.apply(self)
        ui_theme.center(self, 1100, 800, min_w=940, min_h=600)
        self.param_map = {}
        self.all_files = []
        self.current_file = ""
        self.last_folder = ""
        self.notes_path = ""       # 当前工作区的说明文件路径
        self.notes_data = {}       # 说明数据：键 -> 说明内容
        self._notes_warned = False
        self.session_path = ""     # 当前工作区的会话状态文件路径
        self.session_data = {}     # 上次会话数据（保留文件/置顶/隐藏）
        self.closed_files = set()  # 被 × 掉的文件（参数保留在内存，可恢复）
        self._scanned_all = []     # 本次扫描到的全部含参数文件
        self.unsaved_tag = "unsaved"
        self.ai_rec_tag = "ai_rec"
        self.ai_filtered_tag = "ai_filtered"
        self.item_map = {}  # (tree, item_id) -> 参数项
        self.ai_queue = queue.Queue()  # AI 识别线程 -> 主线程消息队列
        self._ai_total = 0
        self.ai_done_count = 0
        self._ai_total_f = self._ai_total_a = self._ai_total_r = 0
        self._ai_errors = []
        self.selected_param = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 顶部工具栏
        c = ui_theme.COLORS
        top_frame = tk.Frame(self, bg=c["bg"])
        top_frame.pack(fill=tk.X, padx=12, pady=(12, 4))

        row1 = tk.Frame(top_frame, bg=c["bg"])
        row1.pack(fill=tk.X)
        self.btn_select_folder = ttk.Button(row1, text="📂 选择文件夹", style="Primary.TButton",
                                            command=self.select_folder)
        self.btn_select_folder.pack(side=tk.LEFT)
        self.btn_ai = ttk.Button(row1, text="🤖 AI 识别", style="Success.TButton", command=self.ai_scan_all)
        self.btn_ai.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_ai_cfg = ttk.Button(row1, text="🔑 API 设置", command=self.open_ai_settings)
        self.btn_ai_cfg.pack(side=tk.LEFT, padx=(6, 0))
        self.btn_apply_rec = ttk.Button(row1, text="📌 采用AI推荐", command=self.apply_ai_recommend)
        self.btn_apply_rec.pack(side=tk.LEFT, padx=(8, 0))
        self.show_filtered_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="显示AI过滤项", variable=self.show_filtered_var,
                        command=self.refresh_tables).pack(side=tk.LEFT, padx=12)
        self.show_hidden_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="显示隐藏项", variable=self.show_hidden_var,
                        command=self.refresh_tables).pack(side=tk.LEFT)
        self.ai_status_var = tk.StringVar(value="")
        ttk.Label(row1, textvariable=self.ai_status_var, style="Accent.TLabel").pack(side=tk.LEFT, padx=6)
        self.ai_progress = ttk.Progressbar(row1, orient="horizontal", length=160, mode="determinate")
        self.ai_progress.pack(side=tk.LEFT, padx=(0, 10))

        # 右上角：文件名搜索（实时过滤标签栏）
        self.search_var = tk.StringVar(value="")
        search_entry = ttk.Entry(row1, textvariable=self.search_var, width=18)
        search_entry.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(row1, text="🔍 文件名：", style="Tip.TLabel").pack(side=tk.RIGHT)
        self.btn_restore = ttk.Button(row1, text="↩ 恢复关闭文件", command=self.restore_closed_files)
        self.btn_restore.pack(side=tk.RIGHT, padx=(0, 10))
        self.search_var.trace("w", lambda *a: self.apply_tab_filter())

        self.info_label = tk.Label(
            top_frame,
            text="未选择文件夹 | 支持 .h/.c/.cpp/.yaml/.ini 等文件 | 单冒号=参数，双冒号=跳过 | AI 识别需配置环境变量 DEEPSEEK_API_KEY（或 config.json）",
            anchor="w", bg=c["bg"], fg=c["text_muted"], font=ui_theme.ui_font(9))
        self.info_label.pack(fill=tk.X, pady=(6, 0))

        # 文件标签栏（多行自动换行 + 垂直滚动 + 每个文件可关闭）
        # 不用单行横向滚动：文件很多时单行总宽度会超过 Tk 坐标上限（约32767像素），后端会截断显示
        tab_frame = tk.Frame(self, bg=c["bg"])
        tab_frame.pack(fill=tk.X, padx=12, pady=(2, 0))
        self.tab_canvas = tk.Canvas(tab_frame, bg=c["bg"], height=36, highlightthickness=0)
        self.tab_scroll = ttk.Scrollbar(tab_frame, orient=tk.VERTICAL, command=self.tab_canvas.yview)
        self.tab_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tab_canvas.configure(yscrollcommand=self.tab_scroll.set)
        self.tab_inner = tk.Frame(self.tab_canvas, bg=c["bg"])
        self._tab_win = self.tab_canvas.create_window((0, 0), window=self.tab_inner, anchor="nw")
        self.tab_canvas.bind("<MouseWheel>", self._tab_wheel)
        self.tab_canvas.bind("<Configure>", self._on_tab_resize)
        self.tab_widgets = {}  # 文件路径 -> 标签控件
        self.tab_buttons = {}  # 文件路径 -> 标签按钮（用于高亮当前文件）
        self.tab_groups = {}   # 分组名 -> 标题控件（文件多时按类型分组）
        self.expanded_groups = set()  # 已展开的分组（默认折叠）

        # 底部编辑区（先于双栏面板打包，保证窗口较小时不被挤压隐藏）
        bot_frame = tk.Frame(self, bg=c["surface"], highlightthickness=1,
                             highlightbackground=c["border"], highlightcolor=c["border"])
        bot_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 10))
        tk.Label(bot_frame, text="新值：", bg=c["surface"], fg=c["text"],
                 font=ui_theme.ui_font(10)).pack(side=tk.LEFT, padx=(10, 0), pady=6)
        self.entry_val = ttk.Entry(bot_frame)
        self.entry_val.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)
        self.entry_val.bind("<Return>", lambda e: self.apply_val())
        self.btn_apply = ttk.Button(bot_frame, text="应用", style="Primary.TButton",
                                    state=tk.DISABLED, command=self.apply_val)
        self.btn_apply.pack(side=tk.LEFT, padx=3, pady=6)
        self.btn_save = ttk.Button(bot_frame, text="保存选中", state=tk.DISABLED, command=self.save_one)
        self.btn_save.pack(side=tk.LEFT, padx=3, pady=6)
        self.btn_save_all = ttk.Button(bot_frame, text="💾 保存全部", style="Success.TButton",
                                       state=tk.DISABLED, command=self.save_all)
        self.btn_save_all.pack(side=tk.LEFT, padx=3, pady=6)

        # 手动说明（选中参数后填写，回车/失焦自动保存）
        self.entry_note = ttk.Entry(bot_frame, width=36)
        self.entry_note.pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        tk.Label(bot_frame, text="📝 说明：", bg=c["surface"], fg=c["text"],
                 font=ui_theme.ui_font(10)).pack(side=tk.RIGHT)
        self.entry_note.bind("<Return>", lambda e: self.save_note())
        self.entry_note.bind("<FocusOut>", lambda e: self.save_note())

        # 双栏面板
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.FLAT,
                               bd=0, bg=c["bg"])
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))

        # 预调栏
        prio_frame = tk.Frame(paned, bg=c["bg"])
        paned.add(prio_frame, minsize=160)
        ttk.Label(prio_frame, text="📌 预调整栏", style="Section.TLabel").pack(anchor="w", pady=(2, 2))
        cols = ("type", "name", "value", "note", "pos", "up", "del")
        col_defs = [("type", 70, "类型"), ("name", 200, "参数名"), ("value", 150, "值"),
                    ("note", 250, "说明"), ("pos", 100, "位置"), ("up", 36, "↑"), ("del", 36, "×")]
        self.tree_prio = ttk.Treeview(prio_frame, columns=cols, show="headings", height=6, selectmode="browse")
        for col, w, t in col_defs:
            self.tree_prio.heading(col, text=t)
            self.tree_prio.column(col, width=w, anchor="center")
        self.tree_prio.heading("up", text="↓")  # 预调栏：下箭头=退回参数列表
        self._config_tree_tags(self.tree_prio)
        self.tree_prio.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree_prio.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree_prio.bind("<ButtonRelease-1>", lambda e: self.on_click(True, e, self.tree_prio))

        # 参数列表
        norm_frame = tk.Frame(paned, bg=c["bg"])
        paned.add(norm_frame, minsize=200)
        ttk.Label(norm_frame, text="📋 参数列表", style="Section.TLabel").pack(anchor="w", pady=(4, 2))
        self.tree_norm = ttk.Treeview(norm_frame, columns=cols, show="headings", height=12, selectmode="browse")
        for col, w, t in col_defs:
            self.tree_norm.heading(col, text=t)
            self.tree_norm.column(col, width=w, anchor="center")
        self._config_tree_tags(self.tree_norm)
        self.tree_norm.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree_norm.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree_norm.bind("<ButtonRelease-1>", lambda e: self.on_click(False, e, self.tree_norm))

    def _config_tree_tags(self, tree):
        tree.tag_configure(self.unsaved_tag, background="#fff3cd")
        tree.tag_configure(self.ai_rec_tag, background="#e8f5e9")
        tree.tag_configure(self.ai_filtered_tag, background="#f0f0f0", foreground="#999999")

    def on_close(self):
        self.save_note()     # 保存尚在输入框中的说明
        self.save_session()  # 保存会话状态，下次打开同一工作区可恢复
        generate_tune_log(self.param_map, quiet=True)  # 有实际落盘修改才写日志，未改不弹窗
        self.destroy()

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.last_folder = folder
        self.param_map, scanned_files = scan_folder(folder)
        # 本次扫描到的含参数文件（完整集合，关闭文件时可从中恢复）
        self._scanned_all = [fp for fp in scanned_files if self.param_map.get(fp)]
        # 加载该工作区的说明与会话状态（集中存放在说明目录，按工作区路径区分）
        self.notes_path = workspace_notes_path(folder)
        self.session_path = workspace_session_path(folder)
        self.notes_data = load_notes(self.notes_path)
        self.session_data = load_session(self.session_path)
        loaded = 0
        for fp, params in self.param_map.items():
            for p in params:
                key = notes_param_key(fp, folder) + "::" + p["name"]
                if key in self.notes_data:
                    p["note_manual"] = self.notes_data[key]
                    loaded += 1
        # 恢复上次会话：已关闭的文件、置顶、隐藏
        self.closed_files = set()
        self.expanded_groups = set()  # 分组默认折叠
        for rel in (self.session_data.get("closed") or []):
            for fp in self._scanned_all:
                if notes_param_key(fp, folder) == rel:
                    self.closed_files.add(fp)
                    break
        prio_set = set(self.session_data.get("priority") or [])
        hid_set = set(self.session_data.get("hidden") or [])
        for fp, params in self.param_map.items():
            base = notes_param_key(fp, folder)
            for p in params:
                key = base + "::" + p["name"]
                if key in prio_set:
                    p["is_priority"] = True
                if key in hid_set:
                    p["hidden"] = True
        self.all_files = [fp for fp in self._scanned_all if fp not in self.closed_files]
        info = f"{os.path.basename(folder)} | 已扫描：{len(scanned_files)} | 含参数文件：{len(self._scanned_all)}"
        if loaded:
            info += f" | 已载说明：{loaded} 条"
        if self.closed_files or prio_set or hid_set:
            info += " | 已恢复上次工作状态"
        self.info_label.config(text=info)
        self.rebuild_tabs()
        # 恢复上次打开的文件
        cur_rel = self.session_data.get("current") or ""
        target = None
        for fp in self.all_files:
            if notes_param_key(fp, folder) == cur_rel:
                target = fp
                break
        if target:
            self.switch_file(target)
        elif self.all_files:
            self.switch_file(self.all_files[0])

    def _tab_wheel(self, event):
        """标签栏滚动"""
        self.tab_canvas.yview_scroll(int(-event.delta / 120) * 2, "units")
        return "break"

    def _on_tab_resize(self, event):
        """标签栏宽度变化时重新排版"""
        if abs(event.width - getattr(self, "_tab_layout_width", 0)) > 40:
            self._layout_tabs()

    def _filtered_files(self):
        """按搜索关键字过滤文件列表（匹配文件名，忽略大小写）"""
        kw = self.search_var.get().strip().lower()
        if not kw:
            return list(self.all_files)
        return [fp for fp in self.all_files if kw in os.path.basename(fp).lower()]

    def apply_tab_filter(self):
        """搜索内容变化：匹配集合变了才重建标签（打字流畅）"""
        if self._filtered_files() != getattr(self, "_shown_files", None):
            self.rebuild_tabs()

    def _highlight_current_tab(self):
        """高亮当前选中的文件标签，其余恢复默认样式"""
        c = ui_theme.COLORS
        for fp, btn in self.tab_buttons.items():
            if fp == self.current_file:
                btn.config(bg=c["primary"], fg="#ffffff",
                           activebackground=c["primary_active"], activeforeground="#ffffff")
            else:
                btn.config(bg="#f0f3f9", fg=c["text"],
                           activebackground=c["hover"], activeforeground=c["text"])

    def _create_tab(self, fp):
        """创建单个文件标签（右上角 × 可关闭）"""
        c = ui_theme.COLORS
        fn = os.path.basename(fp)
        holder = tk.Frame(self.tab_inner, bg=c["bg"])
        btn = tk.Button(holder, text=fn + "   ", padx=4, pady=1, relief=tk.FLAT, bd=0,
                        bg="#f0f3f9", fg=c["text"],
                        activebackground=c["hover"], activeforeground=c["text"],
                        cursor="hand2", font=ui_theme.ui_font(9),
                        command=lambda p=fp: self.switch_file(p))
        btn.pack()
        close = tk.Label(holder, text="×", fg=c["text_muted"], bg="#e2e8f1",
                         cursor="hand2", font=("", 8, "bold"))
        close.place(relx=1.0, rely=0.0, anchor="ne")
        close.bind("<Button-1>", lambda e, p=fp: self.close_file_tab(p))
        close.bind("<Enter>", lambda e, w=close: w.config(fg=c["danger"]))
        close.bind("<Leave>", lambda e, w=close: w.config(fg=c["text_muted"]))
        for w in (holder, btn, close):
            w.bind("<MouseWheel>", self._tab_wheel)
        self.tab_widgets[fp] = holder
        self.tab_buttons[fp] = btn

    def rebuild_tabs(self):
        """重新创建文件标签（选文件夹/搜索过滤时调用；文件多时按类型分组）"""
        c = ui_theme.COLORS
        # 清空现有标签
        for w in self.tab_inner.winfo_children():
            w.destroy()
        self.tab_widgets = {}
        self.tab_buttons = {}
        self.tab_groups = {}

        files = self._filtered_files()
        kw = self.search_var.get().strip()
        # 搜索时平铺显示匹配结果；否则文件多时按类型分组（>10 个的类型各自成组）
        groups = [] if kw else group_files(files)
        if groups:
            for gname, gfiles in groups:
                collapsed = gname not in self.expanded_groups
                arrow = "▸" if collapsed else "▾"
                header = tk.Label(self.tab_inner, text=f"📁 {gname}（{len(gfiles)} 个）{arrow}",
                                  bg=c["primary_soft"], fg=c["text_secondary"], padx=6, pady=2,
                                  font=ui_theme.ui_font(9, True), cursor="hand2")
                header.bind("<Button-1>", lambda e, g=gname: self.toggle_group(g))
                header.bind("<MouseWheel>", self._tab_wheel)
                self.tab_groups[gname] = header
                if not collapsed:
                    for fp in gfiles:
                        self._create_tab(fp)
        else:
            for fp in files:
                self._create_tab(fp)
        self._shown_files = list(self.tab_widgets.keys())
        self._layout_tabs(reset_scroll=True)
        self._highlight_current_tab()

    def toggle_group(self, gname):
        """折叠/展开一个文件分组"""
        if gname in self.expanded_groups:
            self.expanded_groups.discard(gname)
        else:
            self.expanded_groups.add(gname)
        self.rebuild_tabs()

    def _layout_units(self):
        """标签栏当前的显示顺序：(kind, 控件) 列表；kind="header" 的分组标题独占一行"""
        files = self._filtered_files()
        kw = self.search_var.get().strip()
        groups = [] if kw else group_files(files)
        units = []
        if groups:
            for gname, gfiles in groups:
                header = self.tab_groups.get(gname)
                if header is not None:
                    units.append(("header", header))
                if gname not in self.expanded_groups:
                    continue
                for fp in gfiles:
                    holder = self.tab_widgets.get(fp)
                    if holder is not None:
                        units.append(("file", holder))
        else:
            for fp in files:
                holder = self.tab_widgets.get(fp)
                if holder is not None:
                    units.append(("file", holder))
        return units

    def _layout_tabs(self, reset_scroll=False):
        """把文件标签按容器宽度排成多行，高度超出部分垂直滚动（不重建控件，速度快）"""
        canvas_w = self.tab_canvas.winfo_width()
        if canvas_w < 50:
            canvas_w = 900  # 窗口尚未显示时的兜底宽度
        self.tab_inner.update_idletasks()

        cur_x = row_y = row_h = 0
        total_h = 0
        for kind, wdg in self._layout_units():
            w = wdg.winfo_reqwidth()
            h = wdg.winfo_reqheight()
            if kind == "header":
                # 分组标题独占一行（先结束当前行，放完后强制换行）
                if cur_x > 0:
                    row_y += row_h + 4
                    cur_x = row_h = 0
                wdg.place(x=0, y=row_y)
                row_y += h + 4
                row_h = 0
                total_h = row_y
                continue
            if cur_x > 0 and cur_x + w > canvas_w - 4:
                row_y += row_h + 4
                cur_x = row_h = 0
            wdg.place(x=cur_x, y=row_y)
            cur_x += w + 6
            row_h = max(row_h, h)
            total_h = row_y + row_h

        total_h = max(total_h, 30)
        self.tab_canvas.itemconfigure(self._tab_win, width=canvas_w, height=total_h)
        self.tab_canvas.configure(scrollregion=(0, 0, canvas_w, total_h))
        self.tab_canvas.configure(height=min(total_h, 96))
        self._tab_layout_width = canvas_w
        if reset_scroll:
            self.tab_canvas.yview_moveto(0)

    def close_file_tab(self, fp):
        """关闭文件标签：仅从当前列表移除，不改动磁盘文件（可用「恢复关闭文件」找回）"""
        self.closed_files.add(fp)
        if fp in self.all_files:
            self.all_files.remove(fp)
        if self.current_file == fp:
            self.current_file = ""
            if self.all_files:
                self.switch_file(self.all_files[0])
            else:
                self.selected_param = None
                self.entry_val.delete(0, tk.END)
                self.btn_apply.config(state=tk.DISABLED)
                self.btn_save.config(state=tk.DISABLED)
                self.refresh_tables()
        else:
            # 预调栏是跨文件的，被关文件的置顶参数需要从预调栏移除
            self.refresh_tables()
        if self.tab_groups:
            # 分组视图：整体重建以刷新分组数量
            self.rebuild_tabs()
        else:
            # 只销毁被关闭的标签控件，不重建全部（避免文件多时卡顿）
            holder = self.tab_widgets.pop(fp, None)
            self.tab_buttons.pop(fp, None)
            if holder:
                holder.destroy()
            self._shown_files = list(self.tab_widgets.keys())
            self._layout_tabs()
        self.save_session()

    def save_session(self):
        """保存会话状态（保留文件/置顶/隐藏/当前文件），下次打开同一工作区自动恢复"""
        if not (self.last_folder and self.session_path):
            return
        root = self.last_folder
        self.session_data = {
            "closed": [notes_param_key(fp, root) for fp in self.closed_files],
            "current": notes_param_key(self.current_file, root) if self.current_file else "",
            "priority": [notes_param_key(fp, root) + "::" + p["name"]
                         for fp, plist in self.param_map.items() for p in plist if p["is_priority"]],
            "hidden": [notes_param_key(fp, root) + "::" + p["name"]
                       for fp, plist in self.param_map.items() for p in plist if p["hidden"]],
        }
        save_session_file(self.session_path, self.session_data)

    def restore_closed_files(self):
        """把被 × 掉的文件重新加回标签栏"""
        if not self.last_folder:
            return
        if not self.closed_files:
            messagebox.showinfo("提示", "当前没有关闭过的文件")
            return
        self.closed_files = set()
        self.all_files = [fp for fp in self._scanned_all if self.param_map.get(fp)]
        self.rebuild_tabs()
        if self.all_files and not self.current_file:
            self.switch_file(self.all_files[0])
        self.refresh_tables()
        self.save_session()

    def switch_file(self, fp):
        self.current_file = fp
        self.selected_param = None
        self.entry_val.delete(0, tk.END)
        self.entry_note.delete(0, tk.END)
        self.btn_apply.config(state=tk.DISABLED)
        self.btn_save.config(state=tk.DISABLED)
        self.title(f"参数编辑工具 {VERSION} - {os.path.basename(fp)}")
        self._highlight_current_tab()
        self.refresh_tables()

    def refresh_tables(self):
        # 清空表格和映射
        self.item_map.clear()
        for tree in [self.tree_prio, self.tree_norm]:
            for item in tree.get_children():
                tree.delete(item)

        # 当前文件的参数
        params = self.param_map.get(self.current_file, [])
        # 预调栏：所有未关闭文件中已置顶的参数（切换文件时保留显示）
        prio_params = [p for fp, plist in self.param_map.items() if fp not in self.closed_files
                       for p in plist if p["is_priority"]]

        if not params and not prio_params:
            self.btn_save_all.config(state=tk.DISABLED)
            return

        show_filtered = self.show_filtered_var.get()
        show_hidden = self.show_hidden_var.get()

        def visible(p):
            if p["hidden"] and not show_hidden:
                return False
            if p.get("ai_filtered") and not show_filtered:
                return False
            return True

        # 预调栏（跨文件）
        for p in prio_params:
            if visible(p):
                self._insert_param_row(self.tree_prio, p)

        # 参数列表（当前文件的非置顶参数）
        for p in params:
            if p["is_priority"]:
                continue
            if visible(p):
                self._insert_param_row(self.tree_norm, p)

        # 更新保存全部按钮状态
        has_unsaved = any(p["is_modified"] for p in params)
        self.btn_save_all.config(state=tk.NORMAL if has_unsaved else tk.DISABLED)

    def _insert_param_row(self, tree, p):
        """向表格插入一行参数并记录映射/状态标记"""
        val = p["new_value"] if p["new_value"] is not None else p["value"]
        note = p.get("note_manual") or p.get("ai_note") or ""
        pos = f"{p['file_name']}:{p['line']}"
        arrow = "↓" if p["is_priority"] else "↑"
        values = (p["type"], p["name"], val, note, pos, arrow, "×")
        item = tree.insert("", "end", values=values)
        self.item_map[(str(tree), item)] = p
        # 标记状态：未保存修改 / AI 过滤 / AI 推荐
        tags = []
        if p["is_modified"]:
            tags.append(self.unsaved_tag)
        if p.get("ai_filtered"):
            tags.append(self.ai_filtered_tag)
        elif p.get("ai_recommend"):
            tags.append(self.ai_rec_tag)
        if tags:
            tree.item(item, tags=tuple(tags))

    def on_click(self, is_priority_tree, e, tree):
        region = tree.identify_region(e.x, e.y)
        if region != "cell":
            return
        col = tree.identify_column(e.x)
        item = tree.focus()
        if not item:
            return

        p = self.item_map.get((str(tree), item))
        if not p:
            return

        # 处理箭头：参数列表↑=加入预调栏，预调栏↓=退回参数列表
        if col == "#6":
            p["is_priority"] = not is_priority_tree
            self.refresh_tables()
            self.save_session()
            return

        # 处理×按钮（区分预调栏和参数列表）
        if col == "#7":
            if is_priority_tree:
                # 预调栏×：退回参数列表
                p["is_priority"] = False
            else:
                # 参数列表×：隐藏参数；已隐藏时再次点击=取消隐藏（配合"显示隐藏项"）
                p["hidden"] = not p["hidden"]
            self.refresh_tables()
            self.save_session()
            return

    def on_tree_select(self, event):
        tree = event.widget
        item = tree.focus()
        p = self.item_map.get((str(tree), item)) if item else None
        if not p:
            self.selected_param = None
            self.entry_val.delete(0, tk.END)
            self.entry_note.delete(0, tk.END)
            self.btn_apply.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED)
            return

        self.selected_param = p
        # 自动全选输入框
        self.entry_val.delete(0, tk.END)
        self.entry_val.insert(0, p["new_value"] or p["value"])
        self.entry_val.selection_range(0, tk.END)
        # 填充手动说明
        self.entry_note.delete(0, tk.END)
        self.entry_note.insert(0, p.get("note_manual", ""))
        # 启用按钮
        self.btn_apply.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.NORMAL)

    def save_note(self):
        """保存当前参数的手动说明（回车/失焦/关闭时触发）"""
        if not self.selected_param:
            return
        text = self.entry_note.get().strip()
        if text == self.selected_param.get("note_manual", ""):
            return
        self.selected_param["note_manual"] = text
        if self.last_folder and self.notes_path:
            key = notes_param_key(self.selected_param["file_path"], self.last_folder) + "::" + self.selected_param["name"]
            if text:
                self.notes_data[key] = text
            else:
                self.notes_data.pop(key, None)
            if not save_notes(self.notes_path, self.notes_data) and not self._notes_warned:
                self._notes_warned = True
                messagebox.showwarning("提示", f"说明文件保存失败（目录不可写？）：\n{self.notes_path}")
        self.refresh_tables()

    def apply_val(self):
        if not self.selected_param:
            messagebox.showwarning("提示", "未选中任何参数")
            return
        new_val = self.entry_val.get().strip()
        if not new_val:
            messagebox.showwarning("提示", "新值不能为空")
            return
        # 标记为修改状态
        self.selected_param["new_value"] = new_val
        self.selected_param["is_modified"] = True
        self.refresh_tables()

    def save_one(self):
        if not self.selected_param:
            messagebox.showwarning("提示", "未选中任何参数")
            return
        if not self.selected_param["is_modified"]:
            messagebox.showinfo("提示", "无未保存修改")
            return
        # 保存到文件
        if save_param(self.selected_param, self.selected_param["new_value"]):
            self.selected_param["saved_from"] = self.selected_param["value"]  # 记录原值供调参日志
            self.selected_param["value"] = self.selected_param["new_value"]
            self.selected_param["new_value"] = None
            self.selected_param["is_modified"] = False
            self.refresh_tables()
            messagebox.showinfo("成功", "保存成功")

    def save_all(self):
        params = self.param_map.get(self.current_file, [])
        modified_params = [p for p in params if p["is_modified"]]
        if not modified_params:
            messagebox.showinfo("提示", "无未保存修改")
            return
        # 批量保存
        success_count = 0
        for p in modified_params:
            if save_param(p, p["new_value"]):
                p["saved_from"] = p["value"]  # 记录原值供调参日志
                p["value"] = p["new_value"]
                p["new_value"] = None
                p["is_modified"] = False
                success_count += 1
        self.refresh_tables()
        messagebox.showinfo("成功", f"共保存 {success_count}/{len(modified_params)} 项")

    # ==================== AI 识别 ====================

    def ai_scan_all(self):
        """打开选择窗口，选择要 AI 识别的文件"""
        api_key, _ = get_ai_settings()
        if not api_key:
            # 没配置 Key：直接打开设置窗口，填完保存后再点一次 AI 识别即可
            if messagebox.askyesno(
                    "未配置 API Key",
                    "还没有配置 DeepSeek API Key。\n\n"
                    "现在打开设置窗口填写吗？\n"
                    "（保存时会自动加密，绑定本机 Windows 账户）"):
                self.open_ai_settings()
            return

        files = [fp for fp in self.param_map if self.param_map[fp] and fp not in self.closed_files]
        if not files:
            messagebox.showinfo("提示", "请先选择文件夹（没有扫描到含参数的文件）")
            return
        self._open_ai_select_dialog(files)

    def open_ai_settings(self):
        """打开「AI 识别设置」窗口：输入并保存 API Key / 模型名。

        非模态：用 grab_set 抢焦点，但不阻塞调用方（避免界面卡住）。
        保存结果以窗口内状态提示为准。
        """
        c = ui_theme.COLORS
        dlg = tk.Toplevel(self)
        dlg.title("AI 识别设置")
        dlg.configure(bg=c["bg"])
        dlg.transient(self)
        dlg.resizable(False, False)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

        cur_key, cur_model = get_ai_settings()
        src = key_source()

        src_text = {
            "env": "当前来源：环境变量 DEEPSEEK_API_KEY（优先级最高，界面保存的 Key 会被它覆盖）",
            "encrypted": "当前来源：config.json 的加密字段（绑定本机 Windows 账户）",
            "plain": "当前来源：config.json 明文（保存后会转为加密）",
            "none": "当前尚未配置 Key",
        }.get(src, "当前尚未配置 Key")

        # 说明区
        head = tk.Frame(dlg, bg=c["bg"])
        head.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(head, text="🔑 DeepSeek API Key", anchor="w", bg=c["bg"], fg=c["text"],
                 font=ui_theme.ui_font(11, True)).pack(anchor="w")
        tk.Label(head, text=src_text, anchor="w", bg=c["bg"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9), wraplength=520, justify="left").pack(anchor="w", pady=(3, 0))

        body = tk.Frame(dlg, bg=c["bg"])
        body.pack(fill=tk.X, padx=16, pady=6)
        body.grid_columnconfigure(1, weight=1)

        # Key 输入
        tk.Label(body, text="API Key：", bg=c["bg"], fg=c["text"],
                 font=ui_theme.ui_font(10)).grid(row=0, column=0, sticky="w", pady=4)
        # 变量显式绑定到本对话框：不指定 master 时会绑到默认根窗口，
        # 多窗口/多解释器场景下会读到空值
        key_var = tk.StringVar(master=dlg, value="")
        key_entry = ttk.Entry(body, textvariable=key_var, width=46, show="•")
        key_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(0, 6))
        key_entry.focus_set()

        show_var = tk.BooleanVar(master=dlg, value=False)

        def toggle_show():
            key_entry.configure(show="" if show_var.get() else "•")

        ttk.Checkbutton(body, text="显示", variable=show_var,
                        command=toggle_show).grid(row=0, column=2, sticky="w")

        if cur_key:
            tk.Label(body, text=f"已保存：{mask_key(cur_key)}（留空则保持不变）",
                     bg=c["bg"], fg=c["text_muted"], font=ui_theme.ui_font(9),
                     anchor="w").grid(row=1, column=1, columnspan=2, sticky="w")

        # 模型输入（可编辑下拉）
        tk.Label(body, text="模型名：", bg=c["bg"], fg=c["text"],
                 font=ui_theme.ui_font(10)).grid(row=2, column=0, sticky="w", pady=(8, 4))
        model_var = tk.StringVar(master=dlg, value=cur_model or "deepseek-flash")
        model_box = ttk.Combobox(body, textvariable=model_var, values=KNOWN_MODELS, width=28)
        model_box.grid(row=2, column=1, sticky="w", pady=(8, 4))
        tk.Label(body, text="可直接输入其它模型名", bg=c["bg"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9)).grid(row=2, column=2, sticky="w")

        # 状态提示
        status_var = tk.StringVar(master=dlg, value="")
        status_lbl = tk.Label(dlg, textvariable=status_var, anchor="w", bg=c["bg"],
                              fg=c["text_secondary"], font=ui_theme.ui_font(9),
                              wraplength=520, justify="left")
        status_lbl.pack(fill=tk.X, padx=16, pady=(2, 0))

        def set_status(text, ok=None):
            status_var.set(text)
            color = c["text_secondary"]
            if ok is True:
                color = c["success"]
            elif ok is False:
                color = c["danger"]
            status_lbl.configure(fg=color)

        # 按钮区
        btns = tk.Frame(dlg, bg=c["bg"])
        btns.pack(fill=tk.X, padx=16, pady=(10, 14))

        def on_test():
            key = key_var.get().strip() or cur_key
            if not key:
                set_status("请先填写 API Key", False)
                return
            set_status("正在测试连接…")
            dlg.update_idletasks()
            ok, msg = test_api_connection(key, model_var.get().strip())
            set_status(("✅ " if ok else "❌ ") + msg, ok)

        def on_save():
            key = key_var.get().strip()
            if not key and not cur_key:
                set_status("请填写 API Key", False)
                return
            ok, msg = save_ai_settings(key if key else cur_key, model_var.get().strip())
            if not ok:
                set_status("❌ " + msg, False)
                return
            new_key, new_model = get_ai_settings()
            set_status(
                f"✅ 已保存（模型：{new_model}，Key：{mask_key(new_key)}）"
                f"\nKey 已加密保存在 config.json，绑定本机 Windows 账户。", True)
            key_var.set("")

        ttk.Button(btns, text="测试连接", command=on_test).pack(side=tk.LEFT)
        ttk.Button(btns, text="保存", style="Primary.TButton",
                   command=on_save).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT)

        key_entry.bind("<Return>", lambda e: on_save())
        model_box.bind("<Return>", lambda e: on_save())

        dlg.update_idletasks()
        try:
            x = self.winfo_rootx() + max(0, (self.winfo_width() - dlg.winfo_width()) // 2)
            y = self.winfo_rooty() + 90
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass

        return dlg

    def _open_ai_select_dialog(self, files):
        """弹出文件选择窗口：勾选要 AI 识别的文件（默认勾选当前文件）"""
        c = ui_theme.COLORS
        dlg = tk.Toplevel(self)
        dlg.title("AI 识别 - 选择文件")
        dlg.configure(bg=c["bg"])
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.update_idletasks()
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

        groups = group_files(files)
        hint = f"共 {len(files)} 个含参数的文件（点击行切换勾选"
        if groups:
            hint += "，点击 📁 分组名整组勾选"
        hint += "）："
        tk.Label(dlg, text=hint, anchor="w", bg=c["bg"], fg=c["text_secondary"],
                 font=ui_theme.ui_font(9)).pack(fill=tk.X, padx=12, pady=(10, 4))

        body = tk.Frame(dlg, bg=c["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=12)
        self._ai_tree = ttk.Treeview(body, columns=("chk", "name", "cnt"), show="headings",
                                     height=18, selectmode="browse")
        self._ai_tree.heading("chk", text="✓")
        self._ai_tree.heading("name", text="文件")
        self._ai_tree.heading("cnt", text="候选")
        self._ai_tree.column("chk", width=36, anchor="center", stretch=False)
        self._ai_tree.column("name", width=340, anchor="w")
        self._ai_tree.column("cnt", width=56, anchor="center", stretch=False)
        self._ai_tree.tag_configure("grouprow", background=c["primary_soft"])
        sb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._ai_tree.yview)
        self._ai_tree.configure(yscrollcommand=sb.set)
        self._ai_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._ai_dlg_files = list(files)
        self._ai_checked = {}
        self._ai_items = {}
        self._ai_groups = {}      # 组名 -> {"header": 标题行, "children": [行], "files": [文件]}
        self._ai_fp_group = {}    # 文件 -> 所属组名

        def add_file(fp, indent=""):
            checked = (fp == self.current_file)
            self._ai_checked[fp] = checked
            item = self._ai_tree.insert("", "end",
                                        values=("☑" if checked else "☐", indent + os.path.basename(fp),
                                                f"{len(self.param_map[fp])} 个"))
            self._ai_items[fp] = item
            return item

        if groups:
            for gname, gfiles in groups:
                header = self._ai_tree.insert("", "end",
                                              values=("☐", f"📁 {gname}（{len(gfiles)} 个）", ""),
                                              tags=("grouprow",))
                children = []
                for fp in gfiles:
                    children.append(add_file(fp, "    "))
                    self._ai_fp_group[fp] = gname
                self._ai_groups[gname] = {"header": header, "children": children, "files": list(gfiles)}
                self._ai_update_group_header(gname)
        else:
            for fp in files:
                add_file(fp)

        if self.current_file in self._ai_items:
            self._ai_tree.see(self._ai_items[self.current_file])

        btns = tk.Frame(dlg, bg=c["bg"])
        btns.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(btns, text="全选", width=8, command=self._ai_dialog_check_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="全不选", width=8, command=self._ai_dialog_uncheck_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="▶ 开始识别", width=12, style="Primary.TButton",
                   command=self._ai_dialog_start).pack(side=tk.LEFT, padx=12)
        ttk.Button(btns, text="取消", width=8, command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

        self._ai_dlg = dlg
        self._ai_tree.bind("<Button-1>", self._ai_dialog_toggle)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.update_idletasks()
        dlg.geometry(f"+{self.winfo_rootx() + 60}+{self.winfo_rooty() + 60}")
        dlg.focus_set()

    def _ai_update_group_header(self, gname):
        """刷新分组标题的勾选显示：☑全选 / ◐部分 / ☐全不选"""
        g = self._ai_groups.get(gname)
        if not g:
            return
        checked = [self._ai_checked.get(fp, False) for fp in g["files"]]
        if checked and all(checked):
            mark = "☑"
        elif any(checked):
            mark = "◐"
        else:
            mark = "☐"
        vals = list(self._ai_tree.item(g["header"], "values"))
        vals[0] = mark
        self._ai_tree.item(g["header"], values=tuple(vals))

    def _ai_set_checked(self, fp, checked):
        """更新某个文件的勾选状态与显示（同步所属分组标题）"""
        self._ai_checked[fp] = checked
        item = self._ai_items[fp]
        vals = list(self._ai_tree.item(item, "values"))
        vals[0] = "☑" if checked else "☐"
        self._ai_tree.item(item, values=tuple(vals))
        gname = self._ai_fp_group.get(fp)
        if gname:
            self._ai_update_group_header(gname)

    def _ai_dialog_toggle(self, event):
        """点击行切换勾选；点击 📁 分组名整组勾选/取消"""
        item = self._ai_tree.identify_row(event.y)
        if not item:
            return
        for gname, g in self._ai_groups.items():
            if g["header"] == item:
                all_on = all(self._ai_checked.get(fp, False) for fp in g["files"])
                for fp in g["files"]:
                    self._ai_set_checked(fp, not all_on)
                return
        for fp, it in self._ai_items.items():
            if it == item:
                self._ai_set_checked(fp, not self._ai_checked[fp])
                return

    def _ai_dialog_check_all(self):
        for fp in self._ai_dlg_files:
            self._ai_set_checked(fp, True)

    def _ai_dialog_uncheck_all(self):
        for fp in self._ai_dlg_files:
            self._ai_set_checked(fp, False)

    def _ai_dialog_start(self):
        files = [fp for fp in self._ai_dlg_files if self._ai_checked.get(fp)]
        if not files:
            messagebox.showinfo("提示", "请至少勾选一个文件", parent=self._ai_dlg)
            return
        self._ai_dlg.destroy()
        self._start_ai(files)

    def _start_ai(self, files):
        """开始 AI 识别指定文件（后台线程 + 队列回传进度）"""
        api_key, model = get_ai_settings()
        self.btn_ai.config(state=tk.DISABLED)
        # 归零统计量：所有合并/计数都发生在主线程的 _ai_poll 里
        self._ai_total = len(files)
        self.ai_done_count = 0
        self._ai_total_f = self._ai_total_a = self._ai_total_r = 0
        self._ai_errors = []
        self.ai_progress.config(maximum=len(files), value=0)
        self.ai_status_var.set(f"AI 识别准备中（共 {len(files)} 个文件）...")
        self.after(150, self._ai_poll)
        threading.Thread(target=self._ai_worker, args=(files, api_key, model), daemon=True).start()

    def _ai_worker(self, files, api_key, model):
        """后台线程：只做网络与文件读取，结果交主线程合并（不直接改共享参数/界面）"""
        total = len(files)
        try:
            for i, fp in enumerate(files, 1):
                self.ai_queue.put(("start", i, total, os.path.basename(fp)))
                try:
                    lines = read_file_lines(fp)
                    params = self.param_map.get(fp)
                    if params is None:
                        continue      # 工作区已切换，该文件不再存在
                    file_text = build_numbered_text(lines, params)
                    cand_text = "\n".join(f"{p['line']}: {p['name']}" for p in params)
                    ai_data = call_deepseek(file_text, cand_text, api_key, model)
                    # 只把原始结果回传，由主线程合并进参数列表
                    self.ai_queue.put(("apply", fp, ai_data, lines))
                except Exception as e:
                    self.ai_queue.put(("error", os.path.basename(fp), str(e)))
        finally:
            self.ai_queue.put(("done",))

    def _ai_poll(self):
        """主线程轮询：合并 AI 结果并刷新界面（所有共享数据的修改都发生在这里）"""
        try:
            while True:
                msg = self.ai_queue.get_nowait()
                kind = msg[0]
                if kind == "start":
                    _, i, total, name = msg
                    self.ai_done_count = i - 1
                    self.ai_status_var.set(f"AI 识别中 {i}/{total}：{name}")
                    self.ai_progress.config(value=i - 1)
                elif kind == "apply":
                    _, fp, ai_data, lines = msg
                    params = self.param_map.get(fp)
                    if params is not None:
                        f, a, r = apply_ai_result(params, ai_data, lines, fp)
                        self._ai_total_f += f
                        self._ai_total_a += a
                        self._ai_total_r += r
                    self.ai_done_count += 1
                    self.ai_progress.config(value=self.ai_done_count)
                    self.ai_status_var.set(
                        f"AI 识别 {self.ai_done_count}/{self._ai_total}"
                        f"（过滤 {self._ai_total_f}，补充 {self._ai_total_a}，推荐 {self._ai_total_r}）")
                elif kind == "error":
                    _, name, err = msg
                    self._ai_errors.append(f"{name}: {err}")
                elif kind == "done":
                    self._ai_done(self._ai_total_f, self._ai_total_a, self._ai_total_r, self._ai_errors)
                    return
        except queue.Empty:
            pass
        self.after(150, self._ai_poll)

    def _ai_done(self, total_f, total_a, total_r, errors):
        self.btn_ai.config(state=tk.NORMAL)
        self.ai_progress.config(value=self.ai_progress["maximum"])
        self.ai_status_var.set(f"AI 识别完成：过滤 {total_f}，补充 {total_a}，推荐 {total_r}")
        self.refresh_tables()
        msg = f"AI 识别完成\n\n过滤误报：{total_f} 项\n补充发现：{total_a} 项\n推荐置顶：{total_r} 项"
        if errors:
            msg += "\n\n以下文件识别失败：\n" + "\n".join(errors[:8])
        messagebox.showinfo("AI 识别", msg)

    def apply_ai_recommend(self):
        count = 0
        for params in self.param_map.values():
            for p in params:
                if p.get("ai_recommend") and not p["is_priority"]:
                    p["is_priority"] = True
                    count += 1
        self.refresh_tables()
        self.save_session()
        if count:
            messagebox.showinfo("提示", f"已把 {count} 个 AI 推荐参数加入预调栏")
        else:
            messagebox.showinfo("提示", "没有可采用的 AI 推荐（请先执行 AI 识别）")


if __name__ == "__main__":
    app = App()
    app.mainloop()