import os
import re
import sys
import json
import hashlib
import queue
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# 引入根目录的环境检测模块（复用 config.json）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import env_check
except Exception:
    env_check = None

VERSION = "AI 识别版"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

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


def read_file_lines(path):
    """读取文件行：utf-8 优先，兼容 gbk（Windows 中文文件）"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='gbk') as f:
            return f.readlines()


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
    }


def scan_file(path):
    results = []
    try:
        lines = read_file_lines(path)
    except Exception as e:
        print(f"读取文件失败：{path} - {e}")
        return results

    in_enum = False
    brace_count = 0
    line_num = 1

    for line in lines:
        stripped = line.strip()
        # 跳过注释和空行
        if not stripped or stripped.startswith(('//', '/*')):
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
    print(f"文件 {os.path.basename(path)} 扫描到 {len(results)} 个参数")
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


# 扫描时跳过的构建产物目录（ROS 的 devel/build/install 等，避免扫到自动生成的样板文件）
SKIP_DIRS = {"devel", "build", "install"}


def scan_folder(folder):
    exts = ('.h', '.hpp', '.c', '.cpp', '.cc', '.cxx')
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


def save_param(item, new_value):
    fp = item["file_path"]
    line_idx = item["line"] - 1
    name = item["name"]

    try:
        lines = read_file_lines(fp)
    except Exception as e:
        messagebox.showerror("错误", f"读取文件失败：{e}")
        return False

    if line_idx < 0 or line_idx >= len(lines):
        messagebox.showerror("错误", "行号超出范围")
        return False

    line = lines[line_idx]

    # 支持保存单冒号
    if ":" in line:
        pattern = re.compile(r'(\s*' + re.escape(name) + r'\s*:\s*)(.*?)(\s*;?\s*)$', re.DOTALL)
    else:
        pattern = re.compile(r'(\s*' + re.escape(name) + r'\s*=\s*)(.*?)(\s*;?\s*)$', re.DOTALL)

    match = pattern.search(line)
    if not match:
        messagebox.showerror("错误", "未找到参数格式")
        return False

    prefix = match.group(1)
    suffix = match.group(3)
    new_line = prefix + new_value + suffix
    lines[line_idx] = new_line

    try:
        with open(fp, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception as e:
        messagebox.showerror("错误", f"保存文件失败：{e}")
        return False

    return True


def generate_tune_log(param_map):
    modified = []
    for params in param_map.values():
        for p in params:
            if p["new_value"] is not None and p["new_value"] != p["value"]:
                modified.append(p)

    if not modified:
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
                f.write(f"【{i}】\n文件：{p['file_name']}\n参数：{p['name']}\n原值：{p['value']}\n新值：{p['new_value']}\n\n")
        messagebox.showinfo("成功", f"日志已生成：{fname}")
    except Exception as e:
        messagebox.showerror("错误", f"日志生成失败：{e}")


# ==================== AI 识别（DeepSeek） ====================

def get_ai_settings():
    """从 config.json 读取 API Key 和模型名"""
    key, model = "", "deepseek-flash"
    if env_check:
        cfg = env_check.load_config()
        key = (cfg.get("deepseek_api_key") or "").strip()
        model = (cfg.get("deepseek_model") or "deepseek-flash").strip()
    return key, model


def ensure_key_field():
    """确保 config.json 磁盘文件里存在 deepseek 配置项，方便用户填写"""
    if not env_check:
        return
    cfg = env_check.load_config()
    try:
        raw = json.loads(env_check.CONFIG_PATH.read_text(encoding="utf-8")) if env_check.CONFIG_PATH.exists() else {}
    except Exception:
        raw = {}
    if not all(k in raw for k in ("deepseek_api_key", "deepseek_model")):
        env_check.save_config(cfg)


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


def save_notes(notes_path, notes):
    """保存说明文件（自动创建目录），成功返回 True"""
    try:
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        with open(notes_path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "notes": notes}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


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
            raise RuntimeError("API Key 无效（401），请检查 config.json 里的 deepseek_api_key")
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
        self.geometry("1100x700")
        self.param_map = {}
        self.all_files = []
        self.current_file = ""
        self.last_folder = ""
        self.notes_path = ""       # 当前工作区的说明文件路径
        self.notes_data = {}       # 说明数据：键 -> 说明内容
        self._notes_warned = False
        self.unsaved_tag = "unsaved"
        self.ai_rec_tag = "ai_rec"
        self.ai_filtered_tag = "ai_filtered"
        self.item_map = {}  # (tree, item_id) -> 参数项
        self.ai_queue = queue.Queue()  # AI 识别线程 -> 主线程消息队列
        self.selected_param = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 顶部控件
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        row1 = tk.Frame(top_frame)
        row1.pack(fill=tk.X)
        self.btn_select_folder = tk.Button(row1, text="选择文件夹", command=self.select_folder)
        self.btn_select_folder.pack(side=tk.LEFT, padx=5)
        self.btn_ai = tk.Button(row1, text="🤖 AI 识别", command=self.ai_scan_all)
        self.btn_ai.pack(side=tk.LEFT, padx=5)
        self.btn_apply_rec = tk.Button(row1, text="📌 采用AI推荐", command=self.apply_ai_recommend)
        self.btn_apply_rec.pack(side=tk.LEFT, padx=5)
        self.show_filtered_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row1, text="显示AI过滤项", variable=self.show_filtered_var,
                       command=self.refresh_tables).pack(side=tk.LEFT, padx=5)
        self.ai_status_var = tk.StringVar(value="")
        tk.Label(row1, textvariable=self.ai_status_var, fg="#1a73e8").pack(side=tk.LEFT, padx=10)
        self.ai_progress = ttk.Progressbar(row1, orient="horizontal", length=170, mode="determinate")
        self.ai_progress.pack(side=tk.LEFT, padx=(0, 10))

        # 右上角：文件名搜索（实时过滤标签栏）
        self.search_var = tk.StringVar(value="")
        search_entry = ttk.Entry(row1, textvariable=self.search_var, width=18)
        search_entry.pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(row1, text="🔍 文件名：").pack(side=tk.RIGHT)
        self.search_var.trace("w", lambda *a: self.apply_tab_filter())

        self.info_label = tk.Label(
            top_frame,
            text="未选择文件夹 | 支持 .h/.cpp/.c 等文件 | 单冒号=参数，双冒号=跳过 | AI 识别需在 config.json 填写 deepseek_api_key",
            anchor="w")
        self.info_label.pack(fill=tk.X, padx=5, pady=(4, 0))

        # 文件标签栏（多行自动换行 + 垂直滚动 + 每个文件可关闭）
        # 不用单行横向滚动：文件很多时单行总宽度会超过 Tk 坐标上限（约32767像素），后端会截断显示
        tab_frame = tk.Frame(self, bg="#eee")
        tab_frame.pack(fill=tk.X, padx=5)
        self.tab_canvas = tk.Canvas(tab_frame, bg="#eee", height=34, highlightthickness=0)
        self.tab_scroll = ttk.Scrollbar(tab_frame, orient=tk.VERTICAL, command=self.tab_canvas.yview)
        self.tab_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tab_canvas.configure(yscrollcommand=self.tab_scroll.set)
        self.tab_inner = tk.Frame(self.tab_canvas, bg="#eee")
        self._tab_win = self.tab_canvas.create_window((0, 0), window=self.tab_inner, anchor="nw")
        self.tab_canvas.bind("<MouseWheel>", self._tab_wheel)
        self.tab_canvas.bind("<Configure>", self._on_tab_resize)
        self.tab_widgets = {}  # 文件路径 -> 标签控件
        self.tab_buttons = {}  # 文件路径 -> 标签按钮（用于高亮当前文件）

        # 双栏面板
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 预调栏
        prio_frame = tk.Frame(paned)
        paned.add(prio_frame, minsize=160)
        tk.Label(prio_frame, text="📌 预调整栏", font=("", 10, "bold")).pack(anchor="w")
        cols = ("type", "name", "value", "note", "pos", "up", "del")
        col_defs = [("type", 70, "类型"), ("name", 200, "参数名"), ("value", 150, "值"),
                    ("note", 250, "说明"), ("pos", 100, "位置"), ("up", 36, "↑"), ("del", 36, "×")]
        self.tree_prio = ttk.Treeview(prio_frame, columns=cols, show="headings", height=6, selectmode="browse")
        for c, w, t in col_defs:
            self.tree_prio.heading(c, text=t)
            self.tree_prio.column(c, width=w, anchor="center")
        self.tree_prio.heading("up", text="↓")  # 预调栏：下箭头=退回参数列表
        self._config_tree_tags(self.tree_prio)
        self.tree_prio.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree_prio.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree_prio.bind("<ButtonRelease-1>", lambda e: self.on_click(True, e, self.tree_prio))

        # 参数列表
        norm_frame = tk.Frame(paned)
        paned.add(norm_frame, minsize=200)
        tk.Label(norm_frame, text="📋 参数列表", font=("", 10, "bold")).pack(anchor="w")
        self.tree_norm = ttk.Treeview(norm_frame, columns=cols, show="headings", height=12, selectmode="browse")
        for c, w, t in col_defs:
            self.tree_norm.heading(c, text=t)
            self.tree_norm.column(c, width=w, anchor="center")
        self._config_tree_tags(self.tree_norm)
        self.tree_norm.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree_norm.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree_norm.bind("<ButtonRelease-1>", lambda e: self.on_click(False, e, self.tree_norm))

        # 底部编辑区
        bot_frame = tk.Frame(self)
        bot_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(bot_frame, text="新值：").pack(side=tk.LEFT)
        self.entry_val = tk.Entry(bot_frame)
        self.entry_val.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry_val.bind("<Return>", lambda e: self.apply_val())
        self.btn_apply = tk.Button(bot_frame, text="应用", state=tk.DISABLED, command=self.apply_val)
        self.btn_apply.pack(side=tk.LEFT, padx=3)
        self.btn_save = tk.Button(bot_frame, text="保存选中", state=tk.DISABLED, command=self.save_one)
        self.btn_save.pack(side=tk.LEFT, padx=3)
        self.btn_save_all = tk.Button(bot_frame, text="💾 保存全部", state=tk.DISABLED, command=self.save_all)
        self.btn_save_all.pack(side=tk.LEFT, padx=3)

        # 手动说明（选中参数后填写，回车/失焦自动保存）
        self.entry_note = tk.Entry(bot_frame, width=36)
        self.entry_note.pack(side=tk.RIGHT, padx=(0, 4))
        tk.Label(bot_frame, text="📝 说明：").pack(side=tk.RIGHT)
        self.entry_note.bind("<Return>", lambda e: self.save_note())
        self.entry_note.bind("<FocusOut>", lambda e: self.save_note())

    def _config_tree_tags(self, tree):
        tree.tag_configure(self.unsaved_tag, background="#fff3cd")
        tree.tag_configure(self.ai_rec_tag, background="#e8f5e9")
        tree.tag_configure(self.ai_filtered_tag, background="#f0f0f0", foreground="#999999")

    def on_close(self):
        self.save_note()  # 保存尚在输入框中的说明
        generate_tune_log(self.param_map)
        self.destroy()

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.last_folder = folder
        self.param_map, scanned_files = scan_folder(folder)
        # 标签栏只显示"扫出参数"的文件；无参数的文件不显示（AI 识别本来也会跳过它们）
        self.all_files = [fp for fp in scanned_files if self.param_map.get(fp)]
        # 加载该工作区保存过的参数说明（集中存放在说明目录，按工作区路径区分）
        self.notes_path = workspace_notes_path(folder)
        self.notes_data = load_notes(self.notes_path)
        loaded = 0
        for fp, params in self.param_map.items():
            for p in params:
                key = notes_param_key(fp, folder) + "::" + p["name"]
                if key in self.notes_data:
                    p["note_manual"] = self.notes_data[key]
                    loaded += 1
        info = f"{os.path.basename(folder)} | 已扫描：{len(scanned_files)} | 含参数文件：{len(self.all_files)}"
        if loaded:
            info += f" | 已载说明：{loaded} 条"
        self.info_label.config(text=info)
        self.rebuild_tabs()
        if self.all_files:
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
        for fp, btn in self.tab_buttons.items():
            if fp == self.current_file:
                btn.config(bg="#1a73e8", fg="#ffffff",
                           activebackground="#1667c8", activeforeground="#ffffff")
            else:
                btn.config(bg="#f0f0f0", fg="#000000",
                           activebackground="#e6e6e6", activeforeground="#000000")

    def rebuild_tabs(self):
        """重新创建文件标签（选文件夹/搜索过滤时调用）"""
        # 清空现有标签
        for w in self.tab_inner.winfo_children():
            w.destroy()
        self.tab_widgets = {}
        self.tab_buttons = {}
        # 创建文件标签（右上角 × 可关闭）
        for fp in self._filtered_files():
            fn = os.path.basename(fp)
            holder = tk.Frame(self.tab_inner, bg="#eee")
            btn = tk.Button(holder, text=fn + "   ", padx=4, pady=1,
                            command=lambda p=fp: self.switch_file(p))
            btn.pack()
            close = tk.Label(holder, text="×", fg="#999999", bg="#e2e2e2",
                             cursor="hand2", font=("", 8, "bold"))
            close.place(relx=1.0, rely=0.0, anchor="ne")
            close.bind("<Button-1>", lambda e, p=fp: self.close_file_tab(p))
            close.bind("<Enter>", lambda e, w=close: w.config(fg="#d32f2f"))
            close.bind("<Leave>", lambda e, w=close: w.config(fg="#999999"))
            for w in (holder, btn, close):
                w.bind("<MouseWheel>", self._tab_wheel)
            self.tab_widgets[fp] = holder
            self.tab_buttons[fp] = btn
        self._shown_files = list(self.tab_widgets.keys())
        self._layout_tabs(reset_scroll=True)
        self._highlight_current_tab()

    def _layout_tabs(self, reset_scroll=False):
        """把文件标签按容器宽度排成多行，高度超出部分垂直滚动（不重建控件，速度快）"""
        canvas_w = self.tab_canvas.winfo_width()
        if canvas_w < 50:
            canvas_w = 900  # 窗口尚未显示时的兜底宽度
        self.tab_inner.update_idletasks()

        cur_x = row_y = row_h = 0
        total_h = 0
        for fp in self.all_files:
            holder = self.tab_widgets.get(fp)
            if holder is None:
                continue
            w = holder.winfo_reqwidth()
            h = holder.winfo_reqheight()
            if cur_x > 0 and cur_x + w > canvas_w - 4:
                row_y += row_h + 4
                cur_x = row_h = 0
            holder.place(x=cur_x, y=row_y)
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
        """关闭文件标签：仅从当前列表移除，不改动磁盘文件"""
        self.param_map.pop(fp, None)
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
        # 只销毁被关闭的标签控件，不重建全部（避免文件多时卡顿）
        holder = self.tab_widgets.pop(fp, None)
        self.tab_buttons.pop(fp, None)
        if holder:
            holder.destroy()
        self._shown_files = list(self.tab_widgets.keys())
        self._layout_tabs()

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
        # 预调栏：所有文件中已置顶的参数（切换文件时保留显示）
        prio_params = [p for plist in self.param_map.values() for p in plist if p["is_priority"]]

        if not params and not prio_params:
            self.btn_save_all.config(state=tk.DISABLED)
            return

        show_filtered = self.show_filtered_var.get()

        def visible(p):
            if p["hidden"]:
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
            return

        # 处理×按钮（区分预调栏和参数列表）
        if col == "#7":
            if is_priority_tree:
                # 预调栏×：退回参数列表
                p["is_priority"] = False
            else:
                # 参数列表×：隐藏参数
                p["hidden"] = True
            self.refresh_tables()
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
                p["value"] = p["new_value"]
                p["new_value"] = None
                p["is_modified"] = False
                success_count += 1
        self.refresh_tables()
        messagebox.showinfo("成功", f"共保存 {success_count}/{len(modified_params)} 项")

    # ==================== AI 识别 ====================

    def ai_scan_all(self):
        api_key, model = get_ai_settings()
        if not api_key:
            ensure_key_field()
            messagebox.showinfo(
                "需要 API Key",
                "未配置 DeepSeek API Key。\n\n"
                "已把配置项写入根目录 config.json，请填写后重试：\n"
                "  \"deepseek_api_key\": \"\"   ← 在这里填 Key")
            return

        files = [fp for fp in self.param_map if self.param_map[fp]]
        if not files:
            messagebox.showinfo("提示", "请先选择文件夹（没有扫描到含参数的文件）")
            return

        self.btn_ai.config(state=tk.DISABLED)
        self.ai_progress.config(maximum=len(files), value=0)
        self.ai_status_var.set(f"AI 识别准备中（共 {len(files)} 个文件）...")
        self.after(150, self._ai_poll)
        threading.Thread(target=self._ai_worker, args=(files, api_key, model), daemon=True).start()

    def _ai_worker(self, files, api_key, model):
        """后台线程：只做网络与数据处理，所有进度通过队列交给主线程（不直接操作界面）"""
        total = len(files)
        total_f = total_a = total_r = 0
        errors = []
        try:
            for i, fp in enumerate(files, 1):
                self.ai_queue.put(("start", i, total, os.path.basename(fp)))
                try:
                    lines = read_file_lines(fp)
                    params = self.param_map[fp]
                    file_text = build_numbered_text(lines, params)
                    cand_text = "\n".join(f"{p['line']}: {p['name']}" for p in params)
                    ai_data = call_deepseek(file_text, cand_text, api_key, model)
                    f, a, r = apply_ai_result(params, ai_data, lines, fp)
                    total_f += f
                    total_a += a
                    total_r += r
                except Exception as e:
                    errors.append(f"{os.path.basename(fp)}: {e}")
                self.ai_queue.put(("file_done", i, total, total_f, total_a, total_r))
        finally:
            self.ai_queue.put(("done", total_f, total_a, total_r, errors))

    def _ai_poll(self):
        """主线程轮询：处理 AI 识别线程发来的消息并更新界面"""
        try:
            while True:
                msg = self.ai_queue.get_nowait()
                kind = msg[0]
                if kind == "start":
                    _, i, total, name = msg
                    self.ai_status_var.set(f"AI 识别中 {i}/{total}：{name}")
                    self.ai_progress.config(value=i - 1)
                elif kind == "file_done":
                    _, i, total, tf, ta, tr = msg
                    self.ai_progress.config(value=i)
                    self.ai_status_var.set(f"AI 识别 {i}/{total}（过滤 {tf}，补充 {ta}，推荐 {tr}）")
                elif kind == "done":
                    _, tf, ta, tr, errors = msg
                    self._ai_done(tf, ta, tr, errors)
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
        if count:
            messagebox.showinfo("提示", f"已把 {count} 个 AI 推荐参数加入预调栏")
        else:
            messagebox.showinfo("提示", "没有可采用的 AI 推荐（请先执行 AI 识别）")


if __name__ == "__main__":
    app = App()
    app.mainloop()