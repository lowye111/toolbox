import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk


class ImageToRGB565GUI:
    """将图片转换为 RGB565 的 C 数组头文件，用于 ST7735/ST7789 等屏幕显示。"""

    def __init__(self, root):
        self.root = root
        self.root.title("图片转 RGB565 工具")
        self.root.geometry("900x780")
        self.root.minsize(820, 680)
        self.root.resizable(True, True)

        # 参数变量
        self.image_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.target_w = tk.StringVar(value="128")
        self.target_h = tk.StringVar(value="128")
        self.fit_mode = tk.StringVar(value="fit")
        self.array_name = tk.StringVar(value="image_data")
        self.bytes_per_row = tk.StringVar(value="20")

        self.preview_photo = None
        self.is_converting = False

        self._setup_style()
        self._create_widgets()

    # ==================== 界面 ====================
    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("微软雅黑", 10))
        style.configure("TLabelframe.Label", font=("微软雅黑", 10, "bold"))
        style.configure("Accent.TButton", font=("微软雅黑", 11, "bold"))
        style.configure("Tip.TLabel", font=("微软雅黑", 9), foreground="gray")

    def _create_widgets(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(4, weight=1)

        # 标题
        title_frame = ttk.Frame(self.root, padding=(20, 15, 20, 5))
        title_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(title_frame, text="图片转 RGB565 工具",
                  font=("微软雅黑", 18, "bold")).pack(anchor="w")
        ttk.Label(title_frame,
                  text="将图片转换为 RGB565 格式的 C 数组头文件，适配 ST7735/ST7789 屏幕（高字节在前）",
                  style="Tip.TLabel").pack(anchor="w", pady=(4, 0))

        # 文件选择
        frame_file = ttk.LabelFrame(self.root, text="文件选择", padding=(15, 12))
        frame_file.grid(row=1, column=0, sticky="ew", padx=20, pady=8)
        frame_file.grid_columnconfigure(1, weight=1)

        ttk.Label(frame_file, text="源图片：").grid(row=0, column=0, padx=5, pady=6, sticky="w")
        ttk.Entry(frame_file, textvariable=self.image_path).grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        ttk.Button(frame_file, text="浏览", width=10,
                   command=self._select_image).grid(row=0, column=2, padx=5, pady=6)

        ttk.Label(frame_file, text="输出头文件：").grid(row=1, column=0, padx=5, pady=6, sticky="w")
        ttk.Entry(frame_file, textvariable=self.output_path).grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        ttk.Button(frame_file, text="浏览", width=10,
                   command=self._select_output).grid(row=1, column=2, padx=5, pady=6)

        # 参数设置
        frame_param = ttk.LabelFrame(self.root, text="转换参数", padding=(15, 12))
        frame_param.grid(row=2, column=0, sticky="ew", padx=20, pady=8)
        frame_param.grid_columnconfigure(3, weight=1)

        ttk.Label(frame_param, text="目标宽度：").grid(row=0, column=0, padx=5, pady=6, sticky="w")
        ttk.Entry(frame_param, textvariable=self.target_w, width=8).grid(row=0, column=1, padx=5, pady=6, sticky="w")
        ttk.Label(frame_param, text="目标高度：").grid(row=0, column=2, padx=(15, 5), pady=6, sticky="w")
        ttk.Entry(frame_param, textvariable=self.target_h, width=8).grid(row=0, column=3, padx=5, pady=6, sticky="w")

        ttk.Label(frame_param, text="缩放方式：").grid(row=1, column=0, padx=5, pady=6, sticky="w")
        mode_frame = ttk.Frame(frame_param)
        mode_frame.grid(row=1, column=1, columnspan=3, sticky="w", padx=5)
        ttk.Radiobutton(mode_frame, text="等比缩放 + 黑边居中",
                        variable=self.fit_mode, value="fit").pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(mode_frame, text="拉伸填充",
                        variable=self.fit_mode, value="stretch").pack(side=tk.LEFT)

        ttk.Label(frame_param, text="数组变量名：").grid(row=2, column=0, padx=5, pady=6, sticky="w")
        ttk.Entry(frame_param, textvariable=self.array_name, width=20).grid(row=2, column=1, padx=5, pady=6, sticky="w")
        ttk.Label(frame_param, text="每行条目数：").grid(row=2, column=2, padx=(15, 5), pady=6, sticky="w")
        ttk.Entry(frame_param, textvariable=self.bytes_per_row, width=8).grid(row=2, column=3, padx=5, pady=6, sticky="w")

        # 预览
        frame_preview = ttk.LabelFrame(self.root, text="预览", padding=(15, 12))
        frame_preview.grid(row=3, column=0, sticky="ew", padx=20, pady=8)
        frame_preview.grid_columnconfigure(1, weight=1)

        self.preview_label = tk.Label(frame_preview, text="选择图片后显示预览",
                                      width=40, height=16, bg="#f0f0f0", fg="#888888")
        self.preview_label.grid(row=0, column=0, padx=5, pady=5, rowspan=4, sticky="n")

        self.info_label = ttk.Label(frame_preview, text="", justify="left",
                                    anchor="nw", wraplength=520)
        self.info_label.grid(row=0, column=1, padx=10, pady=5, sticky="nw")

        # 日志
        frame_log = ttk.LabelFrame(self.root, text="运行日志", padding=(15, 12))
        frame_log.grid(row=4, column=0, sticky="nsew", padx=20, pady=8)
        frame_log.grid_columnconfigure(0, weight=1)
        frame_log.grid_rowconfigure(0, weight=1)

        self.log_text = tk.Text(frame_log, height=8, wrap="word",
                                font=("Consolas", 10), padx=8, pady=8)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame_log, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 操作按钮
        frame_btn = ttk.Frame(self.root, padding=(20, 5, 20, 15))
        frame_btn.grid(row=5, column=0, sticky="ew")
        frame_btn.grid_columnconfigure(0, weight=1)

        self.btn_convert = ttk.Button(frame_btn, text="生成头文件", width=22,
                                      style="Accent.TButton", command=self._start_convert)
        self.btn_convert.grid(row=0, column=0, pady=5)

        self._log("程序启动完成。")

    def _log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def _set_busy(self, busy):
        self.is_converting = busy
        state = "disabled" if busy else "normal"
        for child in self.root.winfo_children():
            pass
        self.btn_convert.config(state=state)

    # ==================== 交互 ====================
    def _select_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片文件",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("所有文件", "*.*")]
        )
        if not file_path:
            return
        self.image_path.set(file_path)
        self._log(f"已选择图片：{file_path}")

        # 自动填充输出路径与数组名
        base_dir = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        if not self.output_path.get().strip():
            self.output_path.set(os.path.join(base_dir, f"{base_name}.h"))
        var_name = re.sub(r"[^0-9A-Za-z_]+", "_", base_name).strip("_").lower()
        if var_name and not var_name[0].isdigit():
            self.array_name.set(var_name + "_data" if not var_name.endswith("data") else var_name)

        self._refresh_preview(file_path)

    def _select_output(self):
        initial = self.output_path.get().strip()
        initial_dir = os.path.dirname(initial) if initial else os.getcwd()
        file_path = filedialog.asksaveasfilename(
            title="保存头文件",
            initialdir=initial_dir,
            defaultextension=".h",
            filetypes=[("C 头文件", "*.h"), ("C++ 头文件", "*.hpp"), ("所有文件", "*.*")]
        )
        if file_path:
            self.output_path.set(file_path)
            self._log(f"输出头文件：{file_path}")

    def _refresh_preview(self, image_path):
        try:
            img = Image.open(image_path).convert("RGB")
        except Exception as e:
            self._log(f"无法读取图片：{e}")
            return

        self._show_preview(img)
        self.info_label.config(
            text=(f"原始尺寸：{img.width} x {img.height}\n"
                  f"文件：{os.path.basename(image_path)}")
        )

    def _show_preview(self, pil_img):
        box_w, box_h = 300, 320
        ratio = min(box_w / pil_img.width, box_h / pil_img.height)
        w = max(1, int(pil_img.width * ratio))
        h = max(1, int(pil_img.height * ratio))
        resample = Image.NEAREST if ratio > 1 else Image.LANCZOS
        self.preview_photo = ImageTk.PhotoImage(pil_img.resize((w, h), resample))
        self.preview_label.config(image=self.preview_photo, text="")

    # ==================== 转换 ====================
    def _validate_params(self):
        image_path = self.image_path.get().strip()
        if not image_path or not os.path.exists(image_path):
            raise ValueError("请选择有效的图片文件！")

        output_path = self.output_path.get().strip()
        if not output_path:
            raise ValueError("请选择头文件输出路径！")

        try:
            width = int(self.target_w.get().strip())
            height = int(self.target_h.get().strip())
        except ValueError:
            raise ValueError("目标宽/高必须是整数！")
        if width <= 0 or height <= 0:
            raise ValueError("目标宽/高必须大于 0！")

        array_name = self.array_name.get().strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", array_name):
            raise ValueError("数组变量名必须是合法的 C 标识符！")

        try:
            per_row = int(self.bytes_per_row.get().strip())
        except ValueError:
            raise ValueError("每行条目数必须是整数！")
        if per_row <= 0:
            raise ValueError("每行条目数必须大于 0！")

        return {
            "image_path": image_path,
            "output_path": output_path,
            "width": width,
            "height": height,
            "fit_mode": self.fit_mode.get(),
            "array_name": array_name,
            "per_row": per_row,
        }

    def _start_convert(self):
        if self.is_converting:
            return
        try:
            params = self._validate_params()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            self._log(f"参数校验失败：{e}")
            return

        self._set_busy(True)
        self._log("开始转换...")
        self._log(f"目标尺寸：{params['width']} x {params['height']}")
        self._log(f"缩放方式：{'等比缩放 + 黑边居中' if params['fit_mode'] == 'fit' else '拉伸填充'}")

        threading.Thread(target=self._convert_worker, args=(params,), daemon=True).start()

    def _convert_worker(self, params):
        try:
            img, count = self._convert_to_rgb565(**params)
            self.root.after(0, lambda: self._on_success(params, img, count))
        except Exception as e:
            self.root.after(0, lambda: self._on_error(e))

    def _on_success(self, params, img, count):
        self._set_busy(False)
        self._show_preview(img)
        out_path = params["output_path"]
        try:
            size_kb = os.path.getsize(out_path) / 1024.0
        except OSError:
            size_kb = 0.0

        self.info_label.config(
            text=(f"输出尺寸：{img.width} x {img.height}\n"
                  f"像素数量：{count}（{count * 2} 字节）\n"
                  f"数组名：{params['array_name']}\n"
                  f"输出文件：{out_path}\n"
                  f"文件大小：{size_kb:.1f} KB")
        )
        self._log("转换完成。")
        self._log(f"输出文件：{out_path}")
        self._log(f"像素数量：{count}，共 {count * 2} 字节")
        messagebox.showinfo("完成", f"头文件生成成功！\n\n像素数量：{count}\n输出文件：{out_path}")

    def _on_error(self, error):
        self._set_busy(False)
        self._log(f"转换失败：{error}")
        messagebox.showerror("错误", str(error))

    @staticmethod
    def _make_guard(output_path):
        base = os.path.splitext(os.path.basename(output_path))[0]
        base = re.sub(r"[^0-9A-Za-z]+", "_", base).strip("_").upper()
        if not base:
            base = "IMAGE"
        if base[0].isdigit():
            base = "IMAGE_" + base
        return f"__{base}_H__"

    @staticmethod
    def _convert_to_rgb565(image_path, output_path, width, height,
                           fit_mode, array_name, per_row):
        img = Image.open(image_path).convert("RGB")

        if fit_mode == "fit":
            ratio = min(width / img.width, height / img.height)
            new_w = max(1, int(round(img.width * ratio)))
            new_h = max(1, int(round(img.height * ratio)))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new("RGB", (width, height), (0, 0, 0))
            canvas.paste(resized, ((width - new_w) // 2, (height - new_h) // 2))
            img = canvas
        else:
            img = img.resize((width, height), Image.LANCZOS)

        px = img.load()
        items = []
        for y in range(height):
            for x in range(width):
                r, g, b = px[x, y]
                rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                items.append("0x%02X,0x%02X" % ((rgb565 >> 8) & 0xFF, rgb565 & 0xFF))

        lines = [",".join(items[i:i + per_row]) for i in range(0, len(items), per_row)]

        guard = ImageToRGB565GUI._make_guard(output_path)
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("/* Auto-generated from %s, %dx%d RGB565 */\n"
                    % (os.path.basename(image_path), width, height))
            f.write(f"#ifndef {guard}\n#define {guard}\n\n")
            f.write(f"#define IMG_W {width}\n#define IMG_H {height}\n\n")
            f.write(f"static const uint8_t {array_name}[] = {{\n")
            for ln in lines:
                f.write("    " + ln + ",\n")
            f.write(f"}};\n\n#endif /* {guard} */\n")

        return img, len(items)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageToRGB565GUI(root)
    root.mainloop()