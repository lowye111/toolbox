import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_theme
import env_check


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
        ]

        self._create_widgets()
        self.check_environment()

    def _create_widgets(self):
        c = ui_theme.COLORS

        # 顶部标题区
        header = tk.Frame(self.root, bg=c["surface"])
        header.pack(fill=tk.X)
        header_inner = tk.Frame(header, bg=c["surface"])
        header_inner.pack(fill=tk.X, padx=22, pady=(18, 16))
        tk.Label(header_inner, text="🛠️ 工具箱", bg=c["surface"], fg=c["primary"],
                 font=ui_theme.ui_font(17, True)).pack(anchor="w")
        tk.Label(header_inner, text="常用开发辅助工具集合，点击卡片即可启动",
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

        for tool in self.tools:
            self._create_card(self.scrollable_frame, tool)

        # 底部提示
        footer = tk.Frame(self.root, bg=c["bg"])
        footer.pack(fill=tk.X, padx=22, pady=(0, 12))
        tk.Label(footer, text="点击卡片启动对应程序 · 启动时自动检查运行依赖",
                 bg=c["bg"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9)).pack(anchor="w")

    def _create_card(self, parent, tool):
        """创建单个工具卡片（悬停高亮，点击启动）"""
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

        def set_hover(hover):
            bg = c["hover"] if hover else c["surface"]
            for w in widgets:
                w.configure(bg=bg)
            card.configure(highlightbackground=c["primary"] if hover else c["border"])

        def on_enter(_event):
            set_hover(True)

        def on_leave(_event):
            # 移动到卡片内部子控件时也会触发 Leave，先确认指针是否仍在卡片范围内
            if not self._pointer_in(card):
                set_hover(False)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, t=tool: self.launch_tool(t))
            w.bind("<MouseWheel>", self.on_mousewheel)

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
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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