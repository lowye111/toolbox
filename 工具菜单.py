import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os

import env_check


class ToolMenuApp:
    def __init__(self, root):
        self.root = root
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.root.title("工具菜单")
        self.root.geometry("600x450")
        self.root.minsize(400, 300)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 600) // 2
        y = (screen_height - 450) // 2
        self.root.geometry(f"600x450+{x}+{y}")

        self.setup_styles()
        self.create_widgets()
        self.check_environment()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('Title.TLabel', 
                       font=('微软雅黑', 18, 'bold'),
                       foreground='#1a73e8')

        style.configure('Tool.TButton',
                       font=('微软雅黑', 12),
                       padding=15,
                       borderwidth=0)

        style.map('Tool.TButton',
                  background=[('active', '#4285f4'), ('!active', '#1a73e8')],
                  foreground=[('active', 'white'), ('!active', 'white')])

        style.configure('Description.TLabel',
                       font=('微软雅黑', 10),
                       foreground='#666666')

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="🛠️ 工具箱", style='Title.TLabel')
        title_label.pack(pady=(0, 20))

        self.canvas = tk.Canvas(main_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<MouseWheel>", self.on_mousewheel)

        self.tools = [
            {"name": "参数扫描工具", "description": "批量查看、编辑、管理代码参数", "file": "tools/param_scanner_gui.py", "icon": "⚙️"},
            {"name": "文件批量重命名", "description": "批量重命名文件，支持多种命名规则", "file": "tools/change_name.py", "icon": "🔄"},
            {"name": "视频抽帧工具", "description": "从视频中提取帧图片", "file": "tools/frame_extract.py", "icon": "🎬", "deps": ["cv2"]},
            {"name": "图片转RGB565", "description": "将图片转换为RGB565的C数组（STM32屏幕显示）", "file": "tools/img2rgb565_gui.py", "icon": "🖼️", "deps": ["PIL"]},
            {"name": "进度条标定尺", "description": "透明进度条标定工具", "file": "tools/ruler.py", "icon": "📏"},
            {"name": "模型训练工具", "description": "训练机器学习模型（自动检测YOLO训练环境）", "file": "tools/model_train.py", "icon": "🤖", "deps": ["cv2", "numpy", "PIL"], "env": True},
        ]

        for tool in self.tools:
            tool_frame = ttk.Frame(self.scrollable_frame)
            tool_frame.pack(fill=tk.X, pady=8)

            btn = ttk.Button(tool_frame,
                           text=f"{tool['icon']} {tool['name']}",
                           style='Tool.TButton',
                           command=lambda t=tool: self.launch_tool(t))
            btn.pack(fill=tk.X, pady=(0, 5))

            desc_label = ttk.Label(tool_frame,
                                  text=tool['description'],
                                  style='Description.TLabel')
            desc_label.pack(anchor=tk.W)

        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, pady=(20, 0))

        footer_label = ttk.Label(footer_frame,
                                text="点击工具按钮启动相应程序",
                                style='Description.TLabel')
        footer_label.pack()

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