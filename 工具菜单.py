import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os


class ToolMenuApp:
    def __init__(self, root):
        self.root = root
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

        tools = [
            {"name": "参数扫描工具", "description": "批量查看、编辑、管理代码参数", "file": "tools/param_scanner_gui.py", "icon": "⚙️", "env": None},
            {"name": "文件批量重命名", "description": "批量重命名文件，支持多种命名规则", "file": "tools/change_name.py", "icon": "🔄", "env": None},
            {"name": "视频抽帧工具", "description": "从视频中提取帧图片", "file": "tools/frame_extract.py", "icon": "🎬", "env": None},
            {"name": "图片转RGB565", "description": "将图片转换为RGB565的C数组（STM32屏幕显示）", "file": "tools/img2rgb565_gui.py", "icon": "🖼️", "env": None},
            {"name": "进度条标定尺", "description": "透明进度条标定工具", "file": "tools/ruler.py", "icon": "📏", "env": None},
            {"name": "模型训练工具", "description": "训练机器学习模型（自动激活YOLO环境）", "file": "tools/model_train.py", "icon": "🤖", "env": "yolov5"}
        ]

        for tool in tools:
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

    def launch_tool(self, tool):
        try:
            filename = tool['file']
            env = tool.get('env')
            script_path = os.path.join(os.getcwd(), filename)
            
            if not os.path.exists(script_path):
                messagebox.showerror("错误", f"找不到文件: {filename}")
                return

            if env == "yolo":
                bat_content = f'''@echo off
chcp 65001 >nul
cd /d "{os.getcwd()}"
call conda activate yolo
python "{script_path}"
pause
'''
                bat_path = os.path.join(os.getcwd(), "run_yolo_temp.bat")
                with open(bat_path, 'w', encoding='utf-8') as f:
                    f.write(bat_content)
                subprocess.Popen([bat_path], shell=True)
                messagebox.showinfo("启动成功", f"正在启动 {filename}（YOLO环境）")
            else:
                subprocess.Popen([sys.executable, script_path])
                messagebox.showinfo("启动成功", f"正在启动 {filename}")
        
        except Exception as e:
            messagebox.showerror("启动失败", f"启动 {filename} 时出错:\n{str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ToolMenuApp(root)
    root.mainloop()