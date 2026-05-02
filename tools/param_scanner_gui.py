import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

VERSION = "极简稳定版 - 单冒号参数必显示"

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

def scan_file(path):
    results = []
    try:
        # 优先utf-8，兼容大部分文件
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 失败则用gbk，兼容Windows中文文件
        with open(path, 'r', encoding='gbk') as f:
            lines = f.readlines()
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

        # ===================== 新增：跳过双冒号 :: =====================
        if "::" in line:
            line_num += 1
            continue
        # ==============================================================

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
                results.append({
                    "file_path": path, "file_name": os.path.basename(path),
                    "line": line_num, "type": "变量",
                    "name": name, "value": value, "original_line": line,
                    "new_value": None, "is_modified": False, "is_priority": False,
                    "hidden": False
                })
            line_num += 1
            continue

        # ===================== 新增：匹配单冒号参数 =====================
        match = PATTERNS['colon_param'].search(line)
        if match:
            name = match.group(1).strip()
            value = match.group(2).strip()
            if name and value and name != value:
                results.append({
                    "file_path": path, "file_name": os.path.basename(path),
                    "line": line_num, "type": "参数",
                    "name": name, "value": value, "original_line": line,
                    "new_value": None, "is_modified": False, "is_priority": False,
                    "hidden": False
                })
            line_num += 1
            continue
        # ==============================================================

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
            else:
                name = match.group(2).strip()
                value = match.group(3).strip() if len(match.groups())>=3 else match.group(2).strip()
                type_name = "常量" if typ == "global_const" else "全局变量"
            
            value = value.rstrip(';').strip()
            if name and value and name != value:
                results.append({
                    "file_path": path, "file_name": os.path.basename(path),
                    "line": line_num, "type": type_name,
                    "name": name, "value": value, "original_line": line,
                    "new_value": None, "is_modified": False, "is_priority": False,
                    "hidden": False
                })
            break

        line_num += 1

    # 打印扫描结果，方便调试（可删除）
    print(f"文件 {os.path.basename(path)} 扫描到 {len(results)} 个参数")
    return results

def scan_folder(folder):
    exts = ('.h', '.hpp', '.c', '.cpp', '.cc', '.cxx')
    param_map = {}
    all_files = []

    for root, _, files in os.walk(folder):
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
    old_val = item["value"]

    try:
        with open(fp, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(fp, 'r', encoding='gbk') as f:
            lines = f.readlines()
    except Exception as e:
        messagebox.showerror("错误", f"读取文件失败：{e}")
        return False

    if line_idx < 0 or line_idx >= len(lines):
        messagebox.showerror("错误", "行号超出范围")
        return False

    line = lines[line_idx]

    # ===================== 新增：支持保存单冒号 =====================
    if ":" in line:
        pattern = re.compile(r'(\s*' + re.escape(name) + r'\s*:\s*)(.*?)(\s*;?\s*)$', re.DOTALL)
    else:
        pattern = re.compile(r'(\s*' + re.escape(name) + r'\s*=\s*)(.*?)(\s*;?\s*)$', re.DOTALL)
    # ==============================================================

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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"参数编辑工具 {VERSION}")
        self.geometry("1050x700")
        self.param_map = {}
        self.all_files = []
        self.current_file = ""
        self.last_folder = ""
        self.unsaved_tag = "unsaved"
        self.selected_param = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 顶部控件
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        self.btn_select_folder = tk.Button(top_frame, text="选择文件夹", command=self.select_folder)
        self.btn_select_folder.pack(side=tk.LEFT, padx=5)
        self.info_label = tk.Label(top_frame, text="未选择文件夹 | 支持 .h/.cpp/.c 等文件 | 单冒号=参数，双冒号=跳过")
        self.info_label.pack(side=tk.LEFT, padx=10)

        # 文件标签栏
        tab_frame = tk.Frame(self, height=30, bg="#eee")
        tab_frame.pack(fill=tk.X, padx=5)
        self.tab_canvas = tk.Canvas(tab_frame, height=25, bg="#eee")
        self.tab_scroll = ttk.Scrollbar(tab_frame, orient=tk.HORIZONTAL, command=self.tab_canvas.xview)
        self.tab_inner = tk.Frame(self.tab_canvas, bg="#eee")
        self.tab_canvas.create_window((0, 0), window=self.tab_inner, anchor="nw")
        self.tab_canvas.configure(xscrollcommand=self.tab_scroll.set)
        self.tab_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 双栏面板
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 预调栏
        prio_frame = tk.Frame(paned)
        paned.add(prio_frame, minsize=160)
        tk.Label(prio_frame, text="📌 预调整栏", font=("", 10, "bold")).pack(anchor="w")
        cols = ("type", "name", "value", "pos", "up", "del")
        self.tree_prio = ttk.Treeview(prio_frame, columns=cols, show="headings", height=6, selectmode="browse")
        for c, w, t in [("type", 80, "类型"), ("name", 240, "参数名"), ("value", 180, "值"),
                        ("pos", 100, "位置"), ("up", 40, "↑"), ("del", 40, "×")]:
            self.tree_prio.heading(c, text=t)
            self.tree_prio.column(c, width=w, anchor="center")
        self.tree_prio.tag_configure(self.unsaved_tag, background="#fff3cd")
        self.tree_prio.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree_prio.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree_prio.bind("<ButtonRelease-1>", lambda e: self.on_click(True, e, self.tree_prio))

        # 参数列表
        norm_frame = tk.Frame(paned)
        paned.add(norm_frame, minsize=200)
        tk.Label(norm_frame, text="📋 参数列表", font=("", 10, "bold")).pack(anchor="w")
        self.tree_norm = ttk.Treeview(norm_frame, columns=cols, show="headings", height=12, selectmode="browse")
        for c, w, t in [("type", 80, "类型"), ("name", 240, "参数名"), ("value", 180, "值"),
                        ("pos", 100, "位置"), ("up", 40, "↑"), ("del", 40, "×")]:
            self.tree_norm.heading(c, text=t)
            self.tree_norm.column(c, width=w, anchor="center")
        self.tree_norm.tag_configure(self.unsaved_tag, background="#fff3cd")
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

    def on_close(self):
        generate_tune_log(self.param_map)
        self.destroy()

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.last_folder = folder
        self.param_map, self.all_files = scan_folder(folder)
        # 显示含参数的文件数，方便确认
        param_file_count = len([f for f in self.param_map if self.param_map[f]])
        self.info_label.config(text=f"{os.path.basename(folder)} | 总文件：{len(self.all_files)} | 含参数文件：{param_file_count}")
        self.rebuild_tabs()
        if self.all_files:
            self.switch_file(self.all_files[0])

    def rebuild_tabs(self):
        # 清空现有标签
        for w in self.tab_inner.winfo_children():
            w.destroy()
        # 添加文件标签
        for fp in self.all_files:
            fn = os.path.basename(fp)
            btn = tk.Button(self.tab_inner, text=fn, padx=4, pady=1,
                            command=lambda p=fp: self.switch_file(p))
            btn.pack(side=tk.LEFT, padx=2)
        # 更新滚动范围
        self.tab_canvas.configure(scrollregion=self.tab_canvas.bbox("all"))

    def switch_file(self, fp):
        self.current_file = fp
        self.selected_param = None
        self.entry_val.delete(0, tk.END)
        self.btn_apply.config(state=tk.DISABLED)
        self.btn_save.config(state=tk.DISABLED)
        self.refresh_tables()

    def refresh_tables(self):
        # 清空表格
        for tree in [self.tree_prio, self.tree_norm]:
            for item in tree.get_children():
                tree.delete(item)

        # 获取当前文件参数
        params = self.param_map.get(self.current_file, [])
        if not params:
            self.btn_save_all.config(state=tk.DISABLED)
            return

        # 填充表格（确保所有参数都显示）
        for p in params:
            if p["hidden"]:
                continue
            val = p["new_value"] if p["new_value"] is not None else p["value"]
            pos = f"{p['file_name']}:{p['line']}"
            values = (p["type"], p["name"], val, pos, "↑", "×")
            # 按优先级分配表格
            if p["is_priority"]:
                item = self.tree_prio.insert("", "end", values=values)
            else:
                item = self.tree_norm.insert("", "end", values=values)
            # 标记未保存修改
            if p["is_modified"]:
                tree = self.tree_prio if p["is_priority"] else self.tree_norm
                tree.item(item, tags=(self.unsaved_tag,))

        # 更新保存全部按钮状态
        has_unsaved = any(p["is_modified"] for p in params)
        self.btn_save_all.config(state=tk.NORMAL if has_unsaved else tk.DISABLED)

    def on_click(self, is_priority_tree, e, tree):
        region = tree.identify_region(e.x, e.y)
        if region != "cell":
            return
        col = tree.identify_column(e.x)
        item = tree.focus()
        if not item:
            return

        # 获取当前参数
        item_idx = tree.index(item)
        params = self.param_map.get(self.current_file, [])
        if item_idx >= len(params):
            return
        p = params[item_idx]

        # 处理↑按钮（加入预调栏）
        if col == "#5":
            p["is_priority"] = True
            self.refresh_tables()
            return

        # 处理×按钮（区分预调栏和参数列表）
        if col == "#6":
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
        if not item:
            self.selected_param = None
            self.entry_val.delete(0, tk.END)
            self.btn_apply.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED)
            return

        # 获取选中参数
        item_idx = tree.index(item)
        params = self.param_map.get(self.current_file, [])
        if item_idx >= len(params):
            return
        p = params[item_idx]

        self.selected_param = p
        # 自动全选输入框
        self.entry_val.delete(0, tk.END)
        self.entry_val.insert(0, p["new_value"] or p["value"])
        self.entry_val.selection_range(0, tk.END)
        # 启用按钮
        self.btn_apply.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.NORMAL)

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

if __name__ == "__main__":
    app = App()
    app.mainloop()