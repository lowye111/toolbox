import tkinter as tk
from tkinter import messagebox
import time

class TransparentRuler:
    def __init__(self, root):
        self.root = root
        self.root.title("进度条标定尺")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        # 透明背景色
        self.transparent_bg = '#abcdef'
        self.root.configure(bg=self.transparent_bg)
        self.root.attributes('-transparentcolor', self.transparent_bg)

        # 窗口尺寸
        self.window_width = 700
        self.window_height = 350
        self.root.geometry(f"{self.window_width}x{self.window_height}+200+200")

        # 标题栏
        self.title_height = 30
        self.title_bar = tk.Frame(self.root, bg='#2c3e50', height=self.title_height, bd=0)
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)

        title_label = tk.Label(self.title_bar, text="进度条标定尺", bg='#2c3e50', fg='white',
                               font=('Arial', 10, 'bold'))
        title_label.pack(side=tk.LEFT, padx=10)

        close_btn = tk.Button(self.title_bar, text='✕', command=self.root.destroy,
                              bg='#e74c3c', fg='white', bd=0, padx=8, font=('Arial', 10, 'bold'))
        close_btn.pack(side=tk.RIGHT, padx=5)

        self.title_bar.bind("<Button-1>", self.start_move)
        self.title_bar.bind("<B1-Motion>", self.on_move)
        title_label.bind("<Button-1>", self.start_move)
        title_label.bind("<B1-Motion>", self.on_move)

        # 透明画布
        self.canvas = tk.Canvas(self.root, bg=self.transparent_bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 游标初始X坐标
        self.cursor1_x = 150
        self.cursor2_x = 300
        self.slider_width = 12
        self.slider_height = 40

        self.draw_cursors()

        # 绑定滑块拖动
        self.canvas.tag_bind("cursor1", "<Button-1>", self.on_cursor1_press)
        self.canvas.tag_bind("cursor1", "<B1-Motion>", self.on_cursor1_drag)
        self.canvas.tag_bind("cursor2", "<Button-1>", self.on_cursor2_press)
        self.canvas.tag_bind("cursor2", "<B1-Motion>", self.on_cursor2_drag)

        # 控制面板（水平排列按钮和时间标签）
        self.control_frame = tk.Frame(self.root, bg='lightgray', bd=1, relief=tk.RAISED)
        self.control_frame.place(x=10, y=self.window_height - 80, width=680, height=75)

        # 游标1区域
        self.btn_cursor1 = tk.Button(self.control_frame, text="记录游标1位置", command=self.record_cursor1, width=16)
        self.btn_cursor1.grid(row=0, column=0, padx=5, pady=5)
        self.time_label1 = tk.Label(self.control_frame, text="未记录", bg='lightgray', font=('Arial', 9))
        self.time_label1.grid(row=0, column=1, padx=5)

        # 游标2区域
        self.btn_cursor2 = tk.Button(self.control_frame, text="记录游标2位置", command=self.record_cursor2, width=16)
        self.btn_cursor2.grid(row=1, column=0, padx=5, pady=5)
        self.time_label2 = tk.Label(self.control_frame, text="未记录", bg='lightgray', font=('Arial', 9))
        self.time_label2.grid(row=1, column=1, padx=5)

        # 比较按钮
        self.btn_compare = tk.Button(self.control_frame, text="判断是否进行", command=self.compare, width=16)
        self.btn_compare.grid(row=0, column=2, rowspan=2, padx=20, pady=5)

        # 存储记录的时间戳和游标位置
        self.time1 = None
        self.time2 = None
        self.recorded_cursor1 = None
        self.recorded_cursor2 = None

    def draw_cursors(self):
        """绘制两个游标（垂直线+矩形滑块+数字）"""
        if hasattr(self, 'cursor1_line'):
            self.canvas.delete(self.cursor1_line, self.cursor1_slider, self.cursor1_text,
                               self.cursor2_line, self.cursor2_slider, self.cursor2_text)

        # 游标1 (红色)
        self.cursor1_line = self.canvas.create_line(
            self.cursor1_x, self.title_height, self.cursor1_x, self.window_height,
            fill='red', width=2, tags="cursor1"
        )
        self.cursor1_slider = self.canvas.create_rectangle(
            self.cursor1_x - self.slider_width//2,
            (self.title_height + self.window_height)//2 - self.slider_height//2,
            self.cursor1_x + self.slider_width//2,
            (self.title_height + self.window_height)//2 + self.slider_height//2,
            fill='red', outline='darkred', width=2, tags="cursor1"
        )
        self.cursor1_text = self.canvas.create_text(
            self.cursor1_x, (self.title_height + self.window_height)//2,
            text="1", fill='white', font=('Arial', 12, 'bold'), tags="cursor1"
        )

        # 游标2 (蓝色)
        self.cursor2_line = self.canvas.create_line(
            self.cursor2_x, self.title_height, self.cursor2_x, self.window_height,
            fill='blue', width=2, tags="cursor2"
        )
        self.cursor2_slider = self.canvas.create_rectangle(
            self.cursor2_x - self.slider_width//2,
            (self.title_height + self.window_height)//2 - self.slider_height//2,
            self.cursor2_x + self.slider_width//2,
            (self.title_height + self.window_height)//2 + self.slider_height//2,
            fill='blue', outline='darkblue', width=2, tags="cursor2"
        )
        self.cursor2_text = self.canvas.create_text(
            self.cursor2_x, (self.title_height + self.window_height)//2,
            text="2", fill='white', font=('Arial', 12, 'bold'), tags="cursor2"
        )

    def move_cursor(self, cursor_id, new_x):
        """移动指定游标的所有组件"""
        if cursor_id == 1:
            dx = new_x - self.cursor1_x
            self.cursor1_x = new_x
            self.canvas.move(self.cursor1_line, dx, 0)
            self.canvas.move(self.cursor1_slider, dx, 0)
            self.canvas.move(self.cursor1_text, dx, 0)
        else:
            dx = new_x - self.cursor2_x
            self.cursor2_x = new_x
            self.canvas.move(self.cursor2_line, dx, 0)
            self.canvas.move(self.cursor2_slider, dx, 0)
            self.canvas.move(self.cursor2_text, dx, 0)

    def on_cursor1_press(self, event):
        self.drag_start_x = event.x
        self.drag_start_cursor_x = self.cursor1_x

    def on_cursor1_drag(self, event):
        dx = event.x - self.drag_start_x
        new_x = self.drag_start_cursor_x + dx
        new_x = max(0, min(new_x, self.window_width))
        if new_x != self.cursor1_x:
            self.move_cursor(1, new_x)

    def on_cursor2_press(self, event):
        self.drag_start_x = event.x
        self.drag_start_cursor_x = self.cursor2_x

    def on_cursor2_drag(self, event):
        dx = event.x - self.drag_start_x
        new_x = self.drag_start_cursor_x + dx
        new_x = max(0, min(new_x, self.window_width))
        if new_x != self.cursor2_x:
            self.move_cursor(2, new_x)

    def get_time_str(self):
        """返回当前时间的字符串（时:分:秒.毫秒）"""
        t = time.time()
        local = time.localtime(t)
        ms = int((t - int(t)) * 1000)
        return f"{local.tm_hour:02d}:{local.tm_min:02d}:{local.tm_sec:02d}.{ms:03d}"

    def record_cursor1(self):
        self.time1 = time.time()
        self.recorded_cursor1 = self.cursor1_x
        self.time_label1.config(text=self.get_time_str())
        # 闪烁提示
        self.canvas.itemconfig(self.cursor1_line, fill='orange')
        self.root.after(500, lambda: self.canvas.itemconfig(self.cursor1_line, fill='red'))

    def record_cursor2(self):
        self.time2 = time.time()
        self.recorded_cursor2 = self.cursor2_x
        self.time_label2.config(text=self.get_time_str())
        self.canvas.itemconfig(self.cursor2_line, fill='lightblue')
        self.root.after(500, lambda: self.canvas.itemconfig(self.cursor2_line, fill='blue'))

    def compare(self):
        if self.time1 is None or self.time2 is None:
            messagebox.showwarning("提示", "请先记录两个游标的位置！")
            return

        # 获取当前游标2位置
        current_cursor2 = self.cursor2_x
        delta = current_cursor2 - self.recorded_cursor2

        # 计算时间差
        elapsed = self.time2 - self.time1
        elapsed_ms = int(elapsed * 1000)

        # 格式化输出
        time1_str = self.time_label1.cget("text")
        time2_str = self.time_label2.cget("text")

        msg = f"游标1记录时间: {time1_str}\n"
        msg += f"游标2记录时间: {time2_str}\n"
        msg += f"两个记录点的时间差: {elapsed_ms} 毫秒 ({elapsed:.3f} 秒)\n\n"
        if delta != 0:
            msg += f"✅ 结论：进度条正在进行（游标2从记录到当前移动了 {delta:+d} 像素）"
        else:
            msg += f"⚠️ 结论：进度条似乎没有移动（游标2位置未变）"
        messagebox.showinfo("标定结果", msg)

    # ----- 窗口拖动 -----
    def start_move(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_move(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_start_x)
        y = self.root.winfo_y() + (event.y - self.drag_start_y)
        self.root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TransparentRuler(root)
    root.mainloop()