import cv2
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
import ui_theme

class ImageCropApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片批量裁剪工具")
        self.root.geometry("900x840")
        self.root.resizable(True, True)

        # 应用统一主题
        ui_theme.apply(self.root)

        # 初始化变量
        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.crop_x1 = tk.IntVar(value=0)
        self.crop_y1 = tk.IntVar(value=0)
        self.crop_x2 = tk.IntVar(value=0)
        self.crop_y2 = tk.IntVar(value=0)
        self.crop_width = tk.StringVar(value="0")
        self.crop_height = tk.StringVar(value="0")
        self.total_images = tk.StringVar(value="0")
        self.processed_count = tk.StringVar(value="0")
        self.is_processing = False

        # 裁剪区域变量
        self.ix, self.iy = -1, -1
        self.drawing = False
        self.current_image = None
        self.image_tk = None
        self.crop_rect_id = None
        self.image_files = []
        # 处理过程中收集的失败文件说明（GUI 无控制台，出错信息累计到这里，结束时汇总提示）
        self.failed_files = []

        # 创建主布局
        self.create_widgets()
        ui_theme.center(self.root, 900, 840, min_w=800, min_h=620)

    def create_widgets(self):
        # 顶部配置区域
        top_frame = ttk.LabelFrame(self.root, text="配置", padding="10")
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        # 输入目录
        input_row = ttk.Frame(top_frame)
        input_row.pack(fill=tk.X, pady=2)
        ttk.Label(input_row, text="输入目录:", width=10).pack(side=tk.LEFT)
        ttk.Entry(input_row, textvariable=self.input_folder, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_row, text="浏览", command=self.browse_input).pack(side=tk.LEFT)

        # 输出目录
        output_row = ttk.Frame(top_frame)
        output_row.pack(fill=tk.X, pady=2)
        ttk.Label(output_row, text="输出目录:", width=10).pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.output_folder, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(output_row, text="浏览", command=self.browse_output).pack(side=tk.LEFT)

        # 底部控制面板（先于预览区打包，保证窗口较小时不被挤压隐藏）
        bottom_frame = ttk.LabelFrame(self.root, text="控制", padding="10")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        # 裁剪区域信息
        info_frame = ttk.Frame(bottom_frame)
        info_frame.pack(fill=tk.X, pady=5)

        ttk.Label(info_frame, text="裁剪区域:").pack(side=tk.LEFT, padx=5)
        ttk.Label(info_frame, text="X1:").pack(side=tk.LEFT)
        ttk.Entry(info_frame, textvariable=self.crop_x1, width=6).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="Y1:").pack(side=tk.LEFT)
        ttk.Entry(info_frame, textvariable=self.crop_y1, width=6).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="X2:").pack(side=tk.LEFT)
        ttk.Entry(info_frame, textvariable=self.crop_x2, width=6).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="Y2:").pack(side=tk.LEFT)
        ttk.Entry(info_frame, textvariable=self.crop_y2, width=6).pack(side=tk.LEFT)

        ttk.Label(info_frame, text="尺寸:").pack(side=tk.LEFT, padx=10)
        ttk.Label(info_frame, textvariable=self.crop_width).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="x").pack(side=tk.LEFT)
        ttk.Label(info_frame, textvariable=self.crop_height).pack(side=tk.LEFT)

        # 按钮区域
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="🔍 加载图片", command=self.load_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ 清除选区", command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="⚡ 开始裁剪", command=self.start_cropping, style="Primary.TButton").pack(side=tk.LEFT, padx=5)

        # 进度显示
        progress_frame = ttk.Frame(bottom_frame)
        progress_frame.pack(fill=tk.X, pady=5)

        ttk.Label(progress_frame, text="图片总数:").pack(side=tk.LEFT)
        ttk.Label(progress_frame, textvariable=self.total_images).pack(side=tk.LEFT, padx=5)
        ttk.Label(progress_frame, text="已处理:").pack(side=tk.LEFT, padx=10)
        ttk.Label(progress_frame, textvariable=self.processed_count).pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=10)

        # 状态标签
        self.status_label = ttk.Label(bottom_frame, text="就绪", foreground=ui_theme.COLORS["primary"])
        self.status_label.pack(side=tk.RIGHT)

        # 中间预览区域
        preview_frame = ttk.LabelFrame(self.root, text="裁剪预览", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 画布容器
        canvas_container = ttk.Frame(preview_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_container, bg=ui_theme.COLORS["log_bg"], cursor="cross",
                                highlightthickness=1, highlightbackground=ui_theme.COLORS["border"])
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def browse_input(self):
        folder = filedialog.askdirectory(title="选择输入目录")
        if folder:
            self.input_folder.set(folder)
            # 自动设置输出目录
            if not self.output_folder.get():
                self.output_folder.set(folder + "_cropped")

    def browse_output(self):
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_folder.set(folder)

    def get_image_files(self, folder):
        exts = [".jpg", ".jpeg", ".png", ".bmp", ".JPG", ".PNG", ".JPEG"]
        files = []
        for f in os.listdir(folder):
            if os.path.splitext(f)[1].lower() in exts:
                files.append(os.path.join(folder, f))
        return sorted(files)

    def load_images(self):
        input_folder = self.input_folder.get()
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror("错误", "请选择有效的输入目录！")
            return

        self.image_files = self.get_image_files(input_folder)
        if not self.image_files:
            messagebox.showwarning("提示", "输入目录中没有找到图片！")
            return

        self.total_images.set(str(len(self.image_files)))
        self.processed_count.set("0")
        self.progress_bar["value"] = 0

        # 加载第一张图片
        self.load_image(self.image_files[0])
        self.status_label.config(text=f"已加载 {len(self.image_files)} 张图片，用鼠标框选裁剪区域")

    def load_image(self, filepath):
        # 读取图片（支持中文路径）
        try:
            import numpy as np
            self.current_image = cv2.imdecode(np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self.current_image = None
            self.status_label.config(text=f"读取图片失败: {os.path.basename(filepath)} - {e}")
            return

        if self.current_image is None:
            self.status_label.config(text=f"无法读取图片: {os.path.basename(filepath)}")
            return

        # 转换颜色空间
        image_rgb = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        height, width = image_rgb.shape[:2]

        # 缩放适应画布
        max_size = 600
        scale = min(max_size / width, max_size / height)
        new_width = int(width * scale)
        new_height = int(height * scale)

        image_resized = cv2.resize(image_rgb, (new_width, new_height))
        self.image_tk = ImageTk.PhotoImage(image=Image.fromarray(image_resized))

        # 更新画布
        self.canvas.delete("all")
        self.canvas.config(width=new_width, height=new_height)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.image_tk)

        # 保存缩放比例用于计算实际坐标
        self.scale = scale

    def on_canvas_click(self, event):
        if not self.current_image is None:
            self.drawing = True
            self.ix, self.iy = event.x, event.y
            # 清除之前的选区
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)

    def on_canvas_drag(self, event):
        if self.drawing and self.ix != -1 and self.iy != -1:
            # 清除之前的矩形
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
            # 绘制新矩形
            self.crop_rect_id = self.canvas.create_rectangle(
                self.ix, self.iy, event.x, event.y,
                outline="#4CAF50", width=2, dash=(5, 5)
            )

    def on_canvas_release(self, event):
        if self.drawing and self.ix != -1 and self.iy != -1:
            self.drawing = False

            # 计算裁剪区域（转换为原始图片坐标）
            x1 = int(min(self.ix, event.x) / self.scale)
            y1 = int(min(self.iy, event.y) / self.scale)
            x2 = int(max(self.ix, event.x) / self.scale)
            y2 = int(max(self.iy, event.y) / self.scale)

            # 更新显示
            self.crop_x1.set(x1)
            self.crop_y1.set(y1)
            self.crop_x2.set(x2)
            self.crop_y2.set(y2)
            self.crop_width.set(str(x2 - x1))
            self.crop_height.set(str(y2 - y1))

            # 绘制实线选区
            if self.crop_rect_id:
                self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = self.canvas.create_rectangle(
                min(self.ix, event.x), min(self.iy, event.y),
                max(self.ix, event.x), max(self.iy, event.y),
                outline="#2196F3", width=2
            )

            self.status_label.config(text=f"选区: ({x1},{y1}) - ({x2},{y2})  [{x2-x1}x{y2-y1}]")

    def clear_selection(self):
        if self.crop_rect_id:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self.crop_x1.set(0)
        self.crop_y1.set(0)
        self.crop_x2.set(0)
        self.crop_y2.set(0)
        self.crop_width.set("0")
        self.crop_height.set("0")
        self.status_label.config(text="选区已清除")

    def start_cropping(self):
        # 验证输入
        if not self.image_files:
            messagebox.showerror("错误", "请先加载图片！")
            return

        if self.crop_x1.get() >= self.crop_x2.get() or self.crop_y1.get() >= self.crop_y2.get():
            messagebox.showerror("错误", "请先选择有效的裁剪区域！")
            return

        output_folder = self.output_folder.get()
        if not output_folder:
            messagebox.showerror("错误", "请选择输出目录！")
            return

        # 创建输出目录（确保所有父目录都存在）
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出目录: {e}")
            return

        # 输出目录与输入目录相同时，同名图片会被直接覆盖（open(...,'wb') 不报错），先确认
        if os.path.abspath(output_folder).lower() == os.path.abspath(self.input_folder.get()).lower():
            if not messagebox.askyesno(
                    "输出目录与输入目录相同",
                    "输出目录与输入目录相同，保存时会直接覆盖原有图片且无法恢复。\n\n是否继续？"):
                self.status_label.config(text="已取消：输出目录与输入目录相同")
                return

        # 获取裁剪参数
        x1 = self.crop_x1.get()
        y1 = self.crop_y1.get()
        x2 = self.crop_x2.get()
        y2 = self.crop_y2.get()

        # 开始处理（在后台线程中）
        self.is_processing = True
        self.processed_count.set("0")
        self.progress_bar["value"] = 0
        self.status_label.config(text="正在裁剪...")

        thread = threading.Thread(
            target=self.process_images,
            args=(x1, y1, x2, y2, output_folder),
            daemon=True
        )
        thread.start()

    def process_images(self, x1, y1, x2, y2, output_folder):
        import numpy as np
        success_count = 0
        fail_count = 0
        self.failed_files = []

        for idx, filepath in enumerate(self.image_files):
            try:
                # 读取图片（支持中文路径）
                img = cv2.imdecode(np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    fail_count += 1
                    self.failed_files.append(f"{os.path.basename(filepath)}（无法读取图片）")
                    continue

                # 检查坐标是否在图片范围内
                height, width = img.shape[:2]
                crop_x1 = max(0, min(x1, width - 1))
                crop_y1 = max(0, min(y1, height - 1))
                crop_x2 = max(0, min(x2, width))
                crop_y2 = max(0, min(y2, height))
                if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
                    fail_count += 1
                    self.failed_files.append(f"{os.path.basename(filepath)}（裁剪区域超出图片范围）")
                    continue

                # 裁剪
                cropped = img[crop_y1:crop_y2, crop_x1:crop_x2]

                # 保存（支持中文路径）
                filename = os.path.basename(filepath)
                save_path = os.path.join(output_folder, filename)
                ext = os.path.splitext(filename)[1].lower()
                try:
                    success, buf = cv2.imencode(ext, cropped)
                except Exception as e:
                    fail_count += 1
                    self.failed_files.append(f"{filename}（扩展名 {ext} 不支持编码: {str(e).strip()}）")
                    continue
                if success:
                    with open(save_path, 'wb') as f:
                        f.write(buf.tobytes())
                else:
                    fail_count += 1
                    self.failed_files.append(f"{filename}（编码失败，扩展名 {ext} 可能不受支持）")
                    continue

                success_count += 1

            except Exception as e:
                fail_count += 1
                self.failed_files.append(f"{os.path.basename(filepath)}（{e}）")

            # 更新进度（经 after 回到主线程：Tk 不是线程安全的，
            # 直接在后台线程里操作控件可能卡死或崩溃）
            self.root.after(0, self._update_progress_ui, success_count + fail_count,
                            (idx + 1) / len(self.image_files) * 100)

        # 完成
        self.root.after(0, self._finish_cropping, success_count, fail_count, output_folder)

    def _update_progress_ui(self, done, percent):
        self.processed_count.set(str(done))
        self.progress_bar["value"] = percent

    def _finish_cropping(self, success_count, fail_count, output_folder):
        self.is_processing = False
        self.status_label.config(text=f"完成！成功: {success_count} | 失败: {fail_count}")

        result_msg = f"批量裁剪完成！\n成功: {success_count} 张\n失败: {fail_count} 张\n输出目录: {output_folder}"
        if self.failed_files:
            preview = "\n".join(f"· {item}" for item in self.failed_files[:5])
            more = f"\n... 等共 {len(self.failed_files)} 个" if len(self.failed_files) > 5 else ""
            result_msg += f"\n\n失败文件:\n{preview}{more}"
        messagebox.showinfo("完成", result_msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageCropApp(root)
    root.mainloop()
