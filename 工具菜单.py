import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_theme
import env_check

# 长按判定：按住超过这个毫秒数即进入拖动模式（短按仍是启动工具）
LONG_PRESS_MS = 350
# 判定为"开始拖动"前允许的鼠标移动量（像素）；超过则视为误触，取消长按
DRAG_TOLERANCE = 6


class ToolMenuApp:
    def __init__(self, root):
        self.root = root
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.root.title("工具箱")

        ui_theme.apply(self.root)
        ui_theme.center(self.root, 640, 620, min_w=480, min_h=420)

        self.tools = [
            {"name": "参数扫描工具", "description": "批量查看、编辑、管理代码参数", "file": "tools/param_scanner_gui.py", "icon": "⚙️"},
            {"name": "文件批量重命名", "description": "批量重命名文件，支持多种命名规则", "file": "tools/change_name.py", "icon": "🔄"},
            {"name": "视频抽帧工具", "description": "从视频中提取帧图片", "file": "tools/frame_extract.py", "icon": "🎬", "deps": ["cv2"]},
            {"name": "图片批量裁剪", "description": "框选一次区域，批量裁剪整个目录的图片", "file": "tools/cut_gui.py", "icon": "✂️", "deps": ["cv2", "PIL"]},
            {"name": "图片转RGB565", "description": "将图片转换为RGB565的C数组（STM32屏幕显示）", "file": "tools/img2rgb565_gui.py", "icon": "🖼️", "deps": ["PIL"]},
            {"name": "进度条标定尺", "description": "透明进度条标定工具", "file": "tools/ruler.py", "icon": "📏"},
            {"name": "模型训练工具", "description": "训练机器学习模型（自动检测YOLO训练环境）", "file": "tools/model_train.py", "icon": "🤖", "deps": ["cv2", "numpy", "PIL"], "env": True},
            {"name": "抓歌打包器", "description": "输入歌名 → 生成 zip（MP3/FLAC + 封面 + 歌词），拖进 QQ/微信即可发到手机", "file": "tools/music_grabber.py", "icon": "🎵"},
        ]

        # 卡片控件与拖动状态
        self.cards = {}          # file -> {"card":..., "widgets":[...]}
        self.drag = None         # 拖动中的临时状态
        self._order_dirty = False

        self._load_order()
        self._create_widgets()
        self.check_environment()

    # ==================== 顺序持久化 ====================

    def _load_order(self):
        """按 config.json 里保存的顺序重排 self.tools。

        未记录的新工具按定义顺序追加到末尾；
        已不存在的工具会被忽略。这样以后新增/删除工具都不会乱。
        """
        saved = env_check.load_config().get("tool_order") or []
        if not isinstance(saved, list) or not saved:
            return
        by_file = {t["file"]: t for t in self.tools}
        ordered = [by_file[f] for f in saved if f in by_file]
        known = {t["file"] for t in ordered}
        ordered.extend(t for t in self.tools if t["file"] not in known)
        if len(ordered) == len(self.tools):
            self.tools = ordered

    def _save_order(self):
        """把当前顺序写回 config.json"""
        try:
            cfg = env_check.load_config()
            cfg["tool_order"] = [t["file"] for t in self.tools]
            env_check.save_config(cfg)
            self._order_dirty = False
        except Exception as e:
            messagebox.showwarning("提示", f"顺序保存失败：{e}")

    # ==================== 界面 ====================

    def _create_widgets(self):
        c = ui_theme.COLORS

        # 顶部标题区
        header = tk.Frame(self.root, bg=c["surface"])
        header.pack(fill=tk.X)
        header_inner = tk.Frame(header, bg=c["surface"])
        header_inner.pack(fill=tk.X, padx=22, pady=(18, 16))
        tk.Label(header_inner, text="🛠️ 工具箱", bg=c["surface"], fg=c["primary"],
                 font=ui_theme.ui_font(17, True)).pack(anchor="w")
        tk.Label(header_inner, text="点击卡片启动 · 长按卡片可拖动排序",
                 bg=c["surface"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9)).pack(anchor="w", pady=(4, 0))
        tk.Frame(self.root, bg=c["border"], height=1).pack(fill=tk.X)

        # 工具卡片滚动区
        body = tk.Frame(self.root, bg=c["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 4))

        self.canvas = tk.Canvas(body, highlightthickness=0, bg=c["bg"])
        self.scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=c["bg"])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self._canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        # 卡片区域宽度跟随滚动区，卡片随窗口拉伸
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._canvas_window, width=e.width))

        self._render_cards()

        # 底部提示
        footer = tk.Frame(self.root, bg=c["bg"])
        footer.pack(fill=tk.X, padx=22, pady=(0, 12))
        tk.Label(footer, text="点击卡片启动 · 长按拖动排序（顺序会自动记住）",
                 bg=c["bg"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9)).pack(anchor="w")

    def _render_cards(self):
        """按 self.tools 的顺序重建卡片"""
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        self.cards.clear()
        for tool in self.tools:
            self._create_card(self.scrollable_frame, tool)

    def _create_card(self, parent, tool):
        """创建单个工具卡片（悬停高亮、短按启动、长按拖动排序）"""
        c = ui_theme.COLORS

        card = tk.Frame(parent, bg=c["surface"], highlightbackground=c["border"],
                        highlightthickness=1, cursor="hand2")
        card.pack(fill=tk.X, pady=(0, 10))

        row = tk.Frame(card, bg=c["surface"])
        row.pack(fill=tk.X, padx=16, pady=13)

        icon = tk.Label(row, text=tool["icon"], bg=c["surface"], font=ui_theme.ui_font(20))
        icon.pack(side=tk.LEFT, padx=(0, 14))

        text_box = tk.Frame(row, bg=c["surface"])
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        name = tk.Label(text_box, text=tool["name"], bg=c["surface"], fg=c["text"],
                        font=ui_theme.ui_font(11, True), anchor="w")
        name.pack(anchor="w")

        desc = tk.Label(text_box, text=tool["description"], bg=c["surface"],
                        fg=c["text_muted"], font=ui_theme.ui_font(9), anchor="w")
        desc.pack(anchor="w", pady=(3, 0))

        arrow = tk.Label(row, text="›", bg=c["surface"], fg=c["text_muted"],
                         font=ui_theme.ui_font(16, True))
        arrow.pack(side=tk.RIGHT, padx=(10, 2))

        widgets = [card, row, icon, text_box, name, desc, arrow]
        self.cards[tool["file"]] = {"card": card, "widgets": widgets, "tool": tool}

        def set_hover(hover):
            bg = c["hover"] if hover else c["surface"]
            for w in widgets:
                w.configure(bg=bg)
            card.configure(highlightbackground=c["primary"] if hover else c["border"])

        def on_enter(_event):
            if self.drag is None:
                set_hover(True)

        def on_leave(_event):
            if self.drag is None and not self._pointer_in(card):
                set_hover(False)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, t=tool, c_=card: self._on_press(e, t, c_))
            w.bind("<B1-Motion>", self._on_motion)
            w.bind("<ButtonRelease-1>", lambda e, t=tool: self._on_release(e, t))
            w.bind("<MouseWheel>", self.on_mousewheel)

    # ==================== 长按拖动 ====================

    def _on_press(self, event, tool, card):
        """按下：起一个定时器，按住够久就进入拖动模式"""
        self.drag = {
            "tool": tool,
            "card": card,
            "press_xy": (event.x_root, event.y_root),
            "active": False,       # 是否已进入拖动模式
            "cancelled": False,    # 是否因移动过多而取消
            "timer": None,
            "insert_index": None,
        }
        self.drag["timer"] = self.root.after(LONG_PRESS_MS, self._enter_drag_mode)

    def _enter_drag_mode(self):
        """长按到时：进入拖动模式（此时才会显示拖动反馈）"""
        d = self.drag
        if not d or d["cancelled"]:
            return
        d["active"] = True
        c = ui_theme.COLORS
        card = d["card"]
        card.configure(highlightbackground=c["primary"], highlightthickness=2)
        # 拖动时改用手型抓取光标；并把卡片稍微"抬起来"一点提示可拖
        for w in self.cards[d["tool"]["file"]]["widgets"]:
            w.configure(cursor="fleur")
        self.root.configure(cursor="fleur")

    def _on_motion(self, event):
        d = self.drag
        if not d:
            return
        # 还没进入拖动模式时，若移动过多就取消长按（避免"想点却轻微滑动"被当成拖动）
        if not d["active"]:
            x0, y0 = d["press_xy"]
            if abs(event.x_root - x0) > DRAG_TOLERANCE or abs(event.y_root - y0) > DRAG_TOLERANCE:
                d["cancelled"] = True
                if d["timer"]:
                    self.root.after_cancel(d["timer"])
                    d["timer"] = None
            return

        self._reorder_to(event.y_root)
        self._autoscroll(event.y_root)

    def _reorder_to(self, y_root):
        """根据鼠标位置，把正在拖的卡片移到对应下标。

        这里刻意用"重新 pack"而不是销毁重建卡片：拖动中若销毁了正被按住的
        控件，Tk 的隐式抓取会中断，后续 B1-Motion 就收不到了。
        """
        d = self.drag
        index = self._index_at(y_root)
        if index is None or index == d.get("insert_index"):
            return
        d["insert_index"] = index

        tool = d["tool"]
        cur = self.tools.index(tool)
        if index == cur:
            return

        self.tools.pop(cur)
        self.tools.insert(index, tool)

        # 按新顺序重新 pack（控件复用，不销毁）
        for t in self.tools:
            info = self.cards.get(t["file"])
            if info:
                info["card"].pack_forget()
        for t in self.tools:
            info = self.cards.get(t["file"])
            if info:
                info["card"].pack(fill=tk.X, pady=(0, 10))
        self.scrollable_frame.update_idletasks()

    def _index_at(self, y_root):
        """算出鼠标纵向位置对应的插入下标"""
        n = len(self.tools)
        for i, tool in enumerate(self.tools):
            info = self.cards.get(tool["file"])
            if not info:
                continue
            card = info["card"]
            try:
                top = card.winfo_rooty()
                mid = top + card.winfo_height() / 2
            except Exception:
                continue
            if y_root < mid:
                return i
        return n - 1

    def _autoscroll(self, y_root):
        """拖到可视区域上下边缘时自动滚动"""
        try:
            top = self.canvas.winfo_rooty()
            height = self.canvas.winfo_height()
        except Exception:
            return
        margin = 28
        if y_root < top + margin:
            self.canvas.yview_scroll(-1, "units")
        elif y_root > top + height - margin:
            self.canvas.yview_scroll(1, "units")

    def _on_release(self, event, tool):
        """松手：短按则启动工具；长按拖动过则保存顺序（不启动）"""
        d = self.drag
        self.drag = None
        self.root.configure(cursor="")

        if d and d["timer"]:
            self.root.after_cancel(d["timer"])
            d["timer"] = None

        was_drag = bool(d and d["active"])
        info = self.cards.get(tool["file"])
        if info:
            info["card"].configure(highlightbackground=ui_theme.COLORS["border"],
                                   highlightthickness=1)
            for w in info["widgets"]:
                w.configure(cursor="hand2")
        if was_drag:
            # 拖动结束：保存顺序，并且不启动工具
            self._save_order()
            if info:
                self._flash(info["card"], "✅ 顺序已保存")
            return

        # 短按：照旧启动
        self.launch_tool(tool)

    def _flash(self, widget, text):
        """在卡片上短暂显示一条提示（拖动结束后反馈）"""
        try:
            tip = tk.Label(widget, text=text, bg=ui_theme.COLORS["primary"], fg="#ffffff",
                           font=ui_theme.ui_font(9, True), padx=10, pady=3)
            tip.place(relx=1.0, rely=0.5, anchor="e", x=-12)
            self.root.after(1200, tip.destroy)
        except Exception:
            pass

    def _pointer_in(self, widget):
        """判断鼠标指针当前是否在指定控件（含子控件）范围内"""
        try:
            x, y = widget.winfo_pointerxy()
            under = widget.winfo_containing(x, y)
        except Exception:
            return False
        while under is not None:
            if under == widget:
                return True
            under = getattr(under, "master", None)
        return False

    def on_mousewheel(self, event):
        # 拖动过程中不要滚动（交给 _autoscroll 处理）
        if self.drag and self.drag.get("active"):
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ==================== 启动 ====================

    def check_environment(self):
        """启动时自检所有工具的基础依赖"""
        deps = sorted({d for tool in self.tools for d in tool.get('deps', [])})
        if deps:
            env_check.ensure_modules(deps, title="环境自检", parent=self.root)

    def launch_tool(self, tool):
        try:
            filename = tool['file']
            deps = tool.get('deps', [])
            script_path = os.path.join(self.root_dir, filename)

            if not os.path.exists(script_path):
                messagebox.showerror("错误", f"找不到文件: {filename}")
                return

            if tool.get('env'):
                self.launch_with_env(tool, script_path, deps)
                return

            if deps and not env_check.ensure_modules(deps, parent=self.root):
                return

            subprocess.Popen([sys.executable, script_path])
            messagebox.showinfo("启动成功", f"正在启动 {filename}")

        except Exception as e:
            messagebox.showerror("启动失败", f"启动 {tool.get('file')} 时出错:\n{str(e)}")

    def launch_with_env(self, tool, script_path, deps):
        """启动需要 conda 训练环境的工具：自动检测环境、补齐依赖后启动"""
        env_python = env_check.find_env_python()
        if not env_python:
            if env_check.module_available("ultralytics") or env_check.module_available("torch"):
                # 当前 Python 本身具备训练能力（如 miniconda base 环境），直接使用
                env_python = sys.executable
            else:
                if not messagebox.askyesno(
                        "未检测到训练环境",
                        "未检测到 conda 训练环境，当前 Python 也没有训练依赖（ultralytics/torch）。\n\n"
                        "可先安装/创建环境，或在根目录 config.json 中填写：\n"
                        "  conda_env  —— 环境名（默认 yolov5）\n"
                        "  env_python —— 环境的 python.exe 路径\n\n"
                        "是否仍用当前 Python 启动？"):
                    return
                env_python = sys.executable

        if env_python == sys.executable:
            # 未检测到专用环境，退回当前 Python（需补齐基础依赖）
            if deps and not env_check.ensure_modules(deps, parent=self.root):
                return
            env_name = "当前 Python"
        else:
            env_name = os.path.basename(os.path.dirname(env_python))
            missing = env_check.env_missing_modules(env_python, deps) if deps else None
            if missing:
                pkgs = env_check.pip_names(missing)
                if messagebox.askyesno(
                        "训练环境缺少依赖",
                        f"环境「{env_name}」中缺少：\n\n" + "\n".join(pkgs) +
                        "\n\n是否安装到该环境？（安装完成后重新启动工具）",
                        parent=self.root):
                    env_check.install_in_console(pkgs, env_python)
                return

        # 等效于 conda activate：把环境目录加入 PATH，保证工具内调用的 python / yolo 来自该环境
        env = os.environ.copy()
        env_dir = os.path.dirname(env_python)
        env["PATH"] = os.pathsep.join([
            env_dir,
            os.path.join(env_dir, "Scripts"),
            os.path.join(env_dir, "Library", "bin"),
            env.get("PATH", ""),
        ])
        subprocess.Popen([env_python, script_path], env=env)
        messagebox.showinfo("启动成功", f"正在启动 {tool['file']}（环境：{env_name}）")


if __name__ == "__main__":
    root = tk.Tk()
    app = ToolMenuApp(root)
    root.mainloop()