import os
import re
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import cv2
import numpy as np
import subprocess
import threading
from datetime import datetime
from PIL import Image, ImageTk


class YOLODataPrepApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO 数据集预处理与训练工具")
        self.root.geometry("1100x800")

        # 初始化属性
        self.has_gpu = self.check_gpu()
        self.last_train_result = None
        self.last_model_path = None
        self.train_process = None
        self.test_process = None
        self.preview_images = []
        self.current_preview_index = 0
        self.current_dir = os.path.dirname(os.path.abspath(__file__))  # 获取当前脚本所在目录

        # 设置样式
        self.setup_styles()

        # 创建选项卡
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 创建五个选项卡
        self.prep_tab = ttk.Frame(self.notebook)  # 图片预处理
        self.wizard_tab = ttk.Frame(self.notebook)  # 配置向导
        self.train_tab = ttk.Frame(self.notebook)  # 训练
        self.test_tab = ttk.Frame(self.notebook)  # 测试
        self.export_tab = ttk.Frame(self.notebook)  # 模型导出

        self.notebook.add(self.prep_tab, text="📸 图片预处理")
        self.notebook.add(self.wizard_tab, text="📋 配置向导")
        self.notebook.add(self.train_tab, text="🚀 训练")
        self.notebook.add(self.test_tab, text="🧪 测试")
        self.notebook.add(self.export_tab, text="📦 模型导出")

        # 初始化各选项卡
        self.setup_prep_tab()
        self.setup_wizard_tab()
        self.setup_train_tab()
        self.setup_test_tab()
        self.setup_export_tab()

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W,
                               font=('微软雅黑', 8))
        status_bar.pack(fill=tk.X, padx=10, pady=(0, 5))

    def check_gpu(self):
        """检查GPU是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False

    def setup_styles(self):
        """设置样式"""
        style = ttk.Style()
        style.theme_use('clam')

        # 颜色配置
        self.colors = {
            'primary': '#2196F3',
            'success': '#4CAF50',
            'warning': '#FF9800',
            'error': '#F44336',
            'bg': '#f5f5f5'
        }

        # 配置样式
        style.configure('TLabel', font=('微软雅黑', 9))
        style.configure('TButton', font=('微软雅黑', 9))
        style.configure('TRadiobutton', font=('微软雅黑', 9))
        style.configure('TCheckbutton', font=('微软雅黑', 9))
        style.configure('TEntry', font=('微软雅黑', 9))
        style.configure('TLabelframe', font=('微软雅黑', 9, 'bold'))
        style.configure('TLabelframe.Label', font=('微软雅黑', 9, 'bold'))
        style.configure('Success.TButton', foreground='white', background='#4CAF50')

    # ==================== 图片预处理选项卡 ====================
    def setup_prep_tab(self):
        """设置图片预处理选项卡"""
        main_frame = ttk.Frame(self.prep_tab, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="📸 数据集图片预处理",
                                font=('微软雅黑', 14, 'bold'), foreground='#2196F3')
        title_label.pack(anchor=tk.W, pady=(0, 15))

        # 输入目录选择
        input_frame = ttk.LabelFrame(main_frame, text="输入目录", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # 训练集图片目录
        img_row = ttk.Frame(input_frame)
        img_row.pack(fill=tk.X, pady=2)
        ttk.Label(img_row, text="训练集图片:", width=10).pack(side=tk.LEFT)
        self.prep_images_dir = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\images\train")
        ttk.Entry(img_row, textvariable=self.prep_images_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(img_row, text="📁", command=lambda: self.browse_dir(self.prep_images_dir), width=3).pack(
            side=tk.RIGHT)

        # 训练集标签目录
        label_row = ttk.Frame(input_frame)
        label_row.pack(fill=tk.X, pady=2)
        ttk.Label(label_row, text="训练集标签:", width=10).pack(side=tk.LEFT)
        self.prep_labels_dir = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\labels\train")
        ttk.Entry(label_row, textvariable=self.prep_labels_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(label_row, text="📁", command=lambda: self.browse_dir(self.prep_labels_dir), width=3).pack(
            side=tk.RIGHT)

        # 输出目录设置
        output_frame = ttk.LabelFrame(main_frame, text="输出设置", padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        # 输出根目录
        out_row = ttk.Frame(output_frame)
        out_row.pack(fill=tk.X, pady=2)
        ttk.Label(out_row, text="输出根目录:", width=10).pack(side=tk.LEFT)
        self.prep_output_root = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\processed")
        ttk.Entry(out_row, textvariable=self.prep_output_root).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(out_row, text="📁", command=lambda: self.browse_dir(self.prep_output_root), width=3).pack(
            side=tk.RIGHT)

        # 数据集名称
        name_row = ttk.Frame(output_frame)
        name_row.pack(fill=tk.X, pady=2)
        ttk.Label(name_row, text="数据集名称:", width=10).pack(side=tk.LEFT)
        self.prep_dataset_name = tk.StringVar(value="soldier_dataset_320")
        ttk.Entry(name_row, textvariable=self.prep_dataset_name).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(name_row, text="(将创建子目录)").pack(side=tk.LEFT, padx=5)

        # 图片大小设置
        size_frame = ttk.LabelFrame(main_frame, text="图片大小设置", padding="10")
        size_frame.pack(fill=tk.X, pady=(0, 10))

        size_row = ttk.Frame(size_frame)
        size_row.pack(fill=tk.X, pady=2)

        ttk.Label(size_row, text="目标尺寸:").pack(side=tk.LEFT)
        self.prep_size = tk.StringVar(value="320")

        ttk.Radiobutton(size_row, text="320x320", variable=self.prep_size,
                        value="320").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(size_row, text="416x416", variable=self.prep_size,
                        value="416").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(size_row, text="640x640", variable=self.prep_size,
                        value="640").pack(side=tk.LEFT, padx=5)
        ttk.Label(size_row, text="自定义:").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Entry(size_row, textvariable=self.prep_size, width=8).pack(side=tk.LEFT, padx=5)

        # 验证集设置
        val_frame = ttk.LabelFrame(main_frame, text="验证集设置", padding="10")
        val_frame.pack(fill=tk.X, pady=(0, 10))

        # 是否转换验证集
        self.prep_convert_val = tk.BooleanVar(value=False)
        ttk.Checkbutton(val_frame, text="转换验证集（单独处理验证集图片）",
                        variable=self.prep_convert_val,
                        command=self.toggle_val_conversion).pack(anchor=tk.W, pady=2)

        # 验证集目录选择（默认隐藏）
        self.prep_val_dir_frame = ttk.Frame(val_frame)

        val_img_row = ttk.Frame(self.prep_val_dir_frame)
        val_img_row.pack(fill=tk.X, pady=2)
        ttk.Label(val_img_row, text="验证集图片:", width=10).pack(side=tk.LEFT)
        self.prep_val_images = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\images\val")
        ttk.Entry(val_img_row, textvariable=self.prep_val_images).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(val_img_row, text="📁", command=lambda: self.browse_dir(self.prep_val_images), width=3).pack(
            side=tk.RIGHT)

        val_label_row = ttk.Frame(self.prep_val_dir_frame)
        val_label_row.pack(fill=tk.X, pady=2)
        ttk.Label(val_label_row, text="验证集标签:", width=10).pack(side=tk.LEFT)
        self.prep_val_labels = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\labels\val")
        ttk.Entry(val_label_row, textvariable=self.prep_val_labels).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(val_label_row, text="📁", command=lambda: self.browse_dir(self.prep_val_labels), width=3).pack(
            side=tk.RIGHT)

        # 提示标签
        self.prep_val_hint = ttk.Label(val_frame,
                                       text="若不转换验证集，将使用训练集作为验证集（data.yaml中设置 val: train）",
                                       font=('微软雅黑', 8), foreground='gray')
        self.prep_val_hint.pack(anchor=tk.W, pady=2)

        # 初始隐藏验证集目录
        self.prep_val_dir_frame.pack_forget()

        # 操作按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="🔍 预览处理", command=self.preview_preprocessing,
                   width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="⚡ 开始处理", command=self.start_preprocessing,
                   width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🚀 处理后直接训练", command=self.preprocess_and_train,
                   width=20).pack(side=tk.LEFT, padx=5)

        # 预览区域
        preview_frame = ttk.LabelFrame(main_frame, text="处理预览", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.prep_preview = ScrolledText(preview_frame, height=10,
                                         font=('Consolas', 9), wrap=tk.WORD,
                                         bg='#fafafa')
        self.prep_preview.pack(fill=tk.BOTH, expand=True)

    def toggle_val_conversion(self):
        """切换验证集转换选项"""
        if self.prep_convert_val.get():
            self.prep_val_dir_frame.pack(fill=tk.X, pady=5)
            self.prep_val_hint.config(text="将独立处理验证集图片，生成单独的 val 目录")
        else:
            self.prep_val_dir_frame.pack_forget()
            self.prep_val_hint.config(text="若不转换验证集，将使用训练集作为验证集（data.yaml中设置 val: train）")

    def browse_dir(self, var):
        """浏览目录"""
        directory = filedialog.askdirectory(initialdir=var.get())
        if directory:
            var.set(directory)

    def preview_preprocessing(self):
        """预览预处理结果"""
        self.prep_preview.delete(1.0, tk.END)

        # 检查输入目录
        if not os.path.exists(self.prep_images_dir.get()):
            messagebox.showerror("错误", "训练集图片目录不存在！")
            return

        # 统计训练集图片
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
        train_images = [f for f in Path(self.prep_images_dir.get()).iterdir()
                        if f.suffix.lower() in image_extensions]

        self.prep_preview.insert(tk.END, f"📊 训练集: 找到 {len(train_images)} 张图片\n")

        # 预览训练集前3张
        for i, img_path in enumerate(train_images[:3]):
            try:
                img = cv2.imread(str(img_path))
                if img is not None:
                    h, w = img.shape[:2]
                    self.prep_preview.insert(tk.END, f"  ├─ {img_path.name}: {w}x{h}\n")

                    # 检查对应的标签
                    label_path = Path(self.prep_labels_dir.get()) / (img_path.stem + '.txt')
                    if label_path.exists():
                        with open(label_path, 'r') as f:
                            lines = f.readlines()
                        self.prep_preview.insert(tk.END, f"  │  └─ 标签: {len(lines)} 个标注\n")
                    else:
                        self.prep_preview.insert(tk.END, f"  │  └─ ⚠️ 缺少标签\n")
            except Exception as e:
                self.prep_preview.insert(tk.END, f"  ├─ {img_path.name}: 读取失败\n")

        if len(train_images) > 3:
            self.prep_preview.insert(tk.END, f"  └─ ... 等 {len(train_images) - 3} 张图片\n")

        # 预览验证集（如果启用）
        if self.prep_convert_val.get() and os.path.exists(self.prep_val_images.get()):
            val_images = [f for f in Path(self.prep_val_images.get()).iterdir()
                          if f.suffix.lower() in image_extensions]
            self.prep_preview.insert(tk.END, f"\n📊 验证集: 找到 {len(val_images)} 张图片\n")

        # 输出目录信息
        target_size = int(self.prep_size.get())
        output_dir = os.path.join(self.prep_output_root.get(), self.prep_dataset_name.get())
        self.prep_preview.insert(tk.END, "\n" + "─" * 50 + "\n")
        self.prep_preview.insert(tk.END, f"📁 输出目录: {output_dir}\n")
        self.prep_preview.insert(tk.END, f"🖼️  目标尺寸: {target_size}x{target_size}\n")

        if self.prep_convert_val.get():
            self.prep_preview.insert(tk.END, f"✅ 验证集: 独立处理，生成 val 目录\n")
        else:
            self.prep_preview.insert(tk.END, f"✅ 验证集: 使用训练集 (data.yaml中设置 val: train)\n")

    def process_images(self, images_dir, labels_dir, output_images_dir, output_labels_dir, target_size):
        """处理图片和标签的通用函数"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
        images = [f for f in Path(images_dir).iterdir()
                  if f.suffix.lower() in image_extensions]

        success = 0
        failed = 0

        for img_path in images:
            try:
                # 读取图片
                img = cv2.imread(str(img_path))
                if img is None:
                    failed += 1
                    continue

                original_h, original_w = img.shape[:2]

                # 计算缩放
                scale = target_size / max(original_w, original_h)
                new_w = int(original_w * scale)
                new_h = int(original_h * scale)

                # 创建画布
                canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)

                # 缩放图片
                resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

                # 居中放置
                x_offset = (target_size - new_w) // 2
                y_offset = (target_size - new_h) // 2

                canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized

                # 保存图片
                output_img_path = os.path.join(output_images_dir, img_path.name)
                cv2.imwrite(output_img_path, canvas)

                # 处理标签
                label_path = Path(labels_dir) / (img_path.stem + '.txt')
                if label_path.exists():
                    with open(label_path, 'r') as f:
                        lines = f.readlines()

                    new_lines = []
                    for line in lines:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            class_id = parts[0]
                            x_center = float(parts[1]) * original_w
                            y_center = float(parts[2]) * original_h
                            width = float(parts[3]) * original_w
                            height = float(parts[4]) * original_h

                            # 计算新坐标
                            new_x_center = (x_center * scale + x_offset) / target_size
                            new_y_center = (y_center * scale + y_offset) / target_size
                            new_width = (width * scale) / target_size
                            new_height = (height * scale) / target_size

                            # 确保坐标有效
                            new_x_center = max(0, min(1, new_x_center))
                            new_y_center = max(0, min(1, new_y_center))
                            new_width = max(0, min(1, new_width))
                            new_height = max(0, min(1, new_height))

                            new_lines.append(
                                f"{class_id} {new_x_center:.6f} {new_y_center:.6f} {new_width:.6f} {new_height:.6f}\n")

                    # 保存新标签
                    output_label_path = os.path.join(output_labels_dir, img_path.stem + '.txt')
                    with open(output_label_path, 'w') as f:
                        f.writelines(new_lines)

                success += 1

            except Exception as e:
                failed += 1
                self.prep_preview.insert(tk.END, f"处理 {img_path.name} 失败: {e}\n")

        return success, failed

    def start_preprocessing(self):
        """开始预处理"""
        if not messagebox.askyesno("确认", "开始处理数据集？这可能需要一些时间。"):
            return

        self.prep_preview.delete(1.0, tk.END)
        self.prep_preview.insert(tk.END, "🚀 开始处理数据集...\n")
        self.root.update()

        try:
            target_size = int(self.prep_size.get())
            output_root = self.prep_output_root.get()
            dataset_name = self.prep_dataset_name.get()

            # 创建输出目录
            output_base = os.path.join(output_root, dataset_name)
            train_output_images = os.path.join(output_base, 'images', 'train')
            train_output_labels = os.path.join(output_base, 'labels', 'train')

            os.makedirs(train_output_images, exist_ok=True)
            os.makedirs(train_output_labels, exist_ok=True)

            # 处理训练集
            self.prep_preview.insert(tk.END, "\n📚 处理训练集...\n")
            train_success, train_failed = self.process_images(
                self.prep_images_dir.get(),
                self.prep_labels_dir.get(),
                train_output_images,
                train_output_labels,
                target_size
            )

            self.prep_preview.insert(tk.END, f"训练集完成: 成功 {train_success} 张, 失败 {train_failed} 张\n")

            # 处理验证集（如果启用）
            val_success = 0
            val_failed = 0
            if self.prep_convert_val.get() and os.path.exists(self.prep_val_images.get()):
                self.prep_preview.insert(tk.END, "\n📚 处理验证集...\n")

                val_output_images = os.path.join(output_base, 'images', 'val')
                val_output_labels = os.path.join(output_base, 'labels', 'val')
                os.makedirs(val_output_images, exist_ok=True)
                os.makedirs(val_output_labels, exist_ok=True)

                val_success, val_failed = self.process_images(
                    self.prep_val_images.get(),
                    self.prep_val_labels.get(),
                    val_output_images,
                    val_output_labels,
                    target_size
                )

                self.prep_preview.insert(tk.END, f"验证集完成: 成功 {val_success} 张, 失败 {val_failed} 张\n")

            # 生成data.yaml
            self.generate_data_yaml(output_base)

            # 搜索并复制模型文件 - 只在指定目录搜索
            self.prep_preview.insert(tk.END, "\n🔍 搜索模型文件...\n")

            # 从训练集图片路径提取根目录
            train_images_path = self.prep_images_dir.get()
            # 去掉 \images\train 部分，得到基础目录
            base_dir = os.path.dirname(os.path.dirname(train_images_path))

            self.prep_preview.insert(tk.END, f"  在目录中搜索: {base_dir}\n")
            self.root.update()

            # 只搜索这个基础目录
            model_files = []
            model_patterns = ['yolo*.pt', 'yolov*.pt', 'yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt']

            try:
                base_path = Path(base_dir)
                if base_path.exists():
                    for pattern in model_patterns:
                        # 使用 glob 而不是 rglob，只搜索当前目录，不递归子目录
                        found = list(base_path.glob(pattern))
                        model_files.extend(found)

                        # 也搜索根目录下的 models 文件夹（如果有）
                        models_dir = base_path / 'models'
                        if models_dir.exists():
                            found = list(models_dir.glob(pattern))
                            model_files.extend(found)
            except Exception as e:
                self.prep_preview.insert(tk.END, f"  搜索出错: {e}\n")

            # 复制找到的模型文件
            copied_files = []
            for model_file in model_files:
                try:
                    target_path = os.path.join(output_base, model_file.name)
                    if not os.path.exists(target_path):
                        shutil.copy2(str(model_file), target_path)
                        copied_files.append(model_file.name)
                        self.prep_preview.insert(tk.END, f"  📄 已复制: {model_file.name}\n")
                        self.root.update()
                except Exception as e:
                    self.prep_preview.insert(tk.END, f"  ⚠️ 复制 {model_file.name} 失败: {e}\n")

            if copied_files:
                self.prep_preview.insert(tk.END, f"✅ 已复制模型文件到数据集目录: {', '.join(set(copied_files))}\n")
            else:
                self.prep_preview.insert(tk.END, f"⚠️ 未找到模型文件，请手动下载并放入: {output_base}\n")
                self.prep_preview.insert(tk.END, f"   建议下载: yolo11n.pt, yolo11s.pt, yolo11m.pt, yolo11l.pt\n")

            self.prep_preview.insert(tk.END, "\n" + "=" * 50 + "\n")
            self.prep_preview.insert(tk.END, f"✅ 处理完成！\n")
            self.prep_preview.insert(tk.END, f"📁 数据集位置: {output_base}\n")

            messagebox.showinfo("完成", f"数据集预处理完成！\n保存位置: {output_base}")

        except Exception as e:
            messagebox.showerror("错误", f"处理过程中出错: {e}")

    def generate_data_yaml(self, output_base):
        """生成data.yaml文件"""
        # 判断验证集设置
        if self.prep_convert_val.get():
            val_setting = 'val'  # 使用独立的验证集
        else:
            val_setting = 'train'  # 使用训练集作为验证集

        yaml_content = f"""# 数据集根目录（使用绝对路径）
path: {output_base}/images

# 训练图片和标签的文件夹
train: train    # 训练集目录
val: {val_setting}      # 验证集目录

# 类别数量
nc: 13

# 类别名称（注意顺序）
names:
  - rssn
  - wskg
  - bpsg
  - gskg
  - rskng
  - gssn
  - wssg
  - bssn
  - wssn
  - gssg
  - rssgg
  - rssg
  - bssg
"""
        yaml_path = os.path.join(output_base, 'data.yaml')
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        self.prep_preview.insert(tk.END, f"\n📄 已生成 data.yaml: {yaml_path}\n")

    def preprocess_and_train(self):
        """预处理后直接训练"""
        # 先运行预处理
        self.start_preprocessing()

        # 询问是否立即训练
        if messagebox.askyesno("训练", "预处理完成！是否立即开始训练？"):
            # 设置训练参数
            output_base = os.path.join(self.prep_output_root.get(), self.prep_dataset_name.get())
            self.train_dataset.set(output_base)
            self.imgsz.set(self.prep_size.get())

            # 切换到训练选项卡
            self.notebook.select(self.train_tab)

            # 提示用户
            messagebox.showinfo("提示", "训练参数已自动设置，请确认后点击'开始训练'")

    # ==================== 配置向导选项卡 ====================
    def setup_wizard_tab(self):
        """设置配置向导选项卡"""
        main_frame = ttk.Frame(self.wizard_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title = ttk.Label(main_frame, text="📋 数据集配置向导", font=('微软雅黑', 14, 'bold'), foreground='#2196F3')
        title.pack(anchor=tk.W, pady=(0, 20))

        # 数据集根目录选择
        path_frame = ttk.LabelFrame(main_frame, text="数据集位置", padding="15")
        path_frame.pack(fill=tk.X, pady=(0, 15))

        path_select = ttk.Frame(path_frame)
        path_select.pack(fill=tk.X)

        ttk.Label(path_select, text="根目录:").pack(side=tk.LEFT)
        self.dataset_path = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data")
        ttk.Entry(path_select, textvariable=self.dataset_path, width=50).pack(side=tk.LEFT, padx=10, fill=tk.X,
                                                                              expand=True)
        ttk.Button(path_select, text="📁", command=self.browse_dataset).pack(side=tk.RIGHT)

        # 文件结构说明
        struct_frame = ttk.LabelFrame(main_frame, text="📁 期望的文件结构", padding="15")
        struct_frame.pack(fill=tk.X, pady=(0, 15))

        struct_text = """C:\\Users\\84820\\Desktop\\soldier_data\\
├── images\\
│   └── train\\          ← 存放所有图片
├── labels\\
│   └── train\\          ← 存放所有对应的 .txt 标注文件
└── data.yaml            ← 数据集配置文件（将自动生成）"""

        ttk.Label(struct_frame, text=struct_text, font=('Consolas', 9), foreground='#666').pack(anchor=tk.W)

        # data.yaml 模板
        yaml_frame = ttk.LabelFrame(main_frame, text="📄 data.yaml 模板", padding="15")
        yaml_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        yaml_template = """# 数据集根目录（使用绝对路径）
path: {}/images

# 训练图片和标签的文件夹
train: train    # 存放图片的文件夹
val: train      # 验证集目录

# 类别数量
nc: 13

# 类别名称（注意顺序）
names:
  - rssn
  - wskg
  - bpsg
  - gskg
  - rskng
  - gssn
  - wssg
  - bssn
  - wssn
  - gssg
  - rssgg
  - rssg
  - bssg"""

        self.yaml_text = ScrolledText(yaml_frame, height=15, font=('Consolas', 10))
        self.yaml_text.pack(fill=tk.BOTH, expand=True)
        self.yaml_text.insert('1.0', yaml_template.format(self.dataset_path.get()))

        # 让文本可选
        self.yaml_text.configure(wrap=tk.NONE)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="📋 复制到剪贴板", command=self.copy_yaml).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="💾 保存 data.yaml", command=self.save_yaml).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🧹 清除缓存文件", command=self.clear_cache).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="✅ 验证数据集", command=self.validate_dataset).pack(side=tk.LEFT, padx=5)

        # 提示信息
        notice = ttk.Label(main_frame,
                           text="⚠️ 提示：如果新增数据集，请清除 labels 中的 .cache 缓存文件",
                           foreground='red', font=('微软雅黑', 9))
        notice.pack(anchor=tk.W, pady=10)

    def browse_dataset(self):
        """浏览数据集目录"""
        directory = filedialog.askdirectory(initialdir=self.dataset_path.get())
        if directory:
            self.dataset_path.set(directory)
            # 更新yaml模板中的路径
            current_content = self.yaml_text.get('1.0', tk.END)
            lines = current_content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('path:'):
                    lines[i] = f'path: {directory}/images'
                    break
            self.yaml_text.delete('1.0', tk.END)
            self.yaml_text.insert('1.0', '\n'.join(lines))

    def copy_yaml(self):
        """复制yaml内容到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.yaml_text.get('1.0', tk.END))
        messagebox.showinfo("成功", "data.yaml 内容已复制到剪贴板")

    def save_yaml(self):
        """保存yaml文件"""
        filepath = os.path.join(self.dataset_path.get(), 'data.yaml')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.yaml_text.get('1.0', tk.END))
            messagebox.showinfo("成功", f"data.yaml 已保存到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def clear_cache(self):
        """清除缓存文件"""
        labels_dir = os.path.join(self.dataset_path.get(), 'labels', 'train')
        if os.path.exists(labels_dir):
            cache_files = list(Path(labels_dir).glob('*.cache'))
            for f in cache_files:
                try:
                    os.remove(f)
                except:
                    pass
            messagebox.showinfo("成功", f"已清除 {len(cache_files)} 个缓存文件")
        else:
            messagebox.showwarning("警告", "labels/train 目录不存在")

    def validate_dataset(self):
        """验证数据集"""
        images_dir = os.path.join(self.dataset_path.get(), 'images', 'train')
        labels_dir = os.path.join(self.dataset_path.get(), 'labels', 'train')

        if not os.path.exists(images_dir):
            messagebox.showerror("错误", f"图片目录不存在: {images_dir}")
            return

        if not os.path.exists(labels_dir):
            messagebox.showerror("错误", f"标签目录不存在: {labels_dir}")
            return

        images = list(Path(images_dir).glob('*.*'))
        labels = list(Path(labels_dir).glob('*.txt'))

        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
        images = [f for f in images if f.suffix.lower() in image_extensions]

        msg = f"📊 数据集统计:\n\n"
        msg += f"图片数量: {len(images)} 张\n"
        msg += f"标签数量: {len(labels)} 个\n"

        # 检查匹配情况
        image_names = {f.stem for f in images}
        label_names = {f.stem for f in labels}

        missing_labels = image_names - label_names
        missing_images = label_names - image_names

        if missing_labels:
            msg += f"\n⚠️ 缺少标签的图片: {len(missing_labels)} 个\n"
        if missing_images:
            msg += f"⚠️ 缺少图片的标签: {len(missing_images)} 个\n"

        msg += f"\n✅ 匹配的图片-标签对: {len(image_names & label_names)} 个"

        messagebox.showinfo("数据集验证结果", msg)

    # ==================== 训练选项卡 ====================
    def setup_train_tab(self):
        """设置训练选项卡（改进版）"""
        main_frame = ttk.Frame(self.train_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title = ttk.Label(main_frame, text="🚀 YOLO 训练配置", font=('微软雅黑', 14, 'bold'), foreground='#2196F3')
        title.pack(anchor=tk.W, pady=(0, 20))

        # 基本配置
        basic_frame = ttk.LabelFrame(main_frame, text="基本配置", padding="15")
        basic_frame.pack(fill=tk.X, pady=(0, 15))

        # 数据集路径
        row1 = ttk.Frame(basic_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="数据集根目录:", width=12).pack(side=tk.LEFT)
        self.train_dataset = tk.StringVar(value=r"C:\Users\84820\Desktop\soldier_data\processed\soldier_dataset_320")
        ttk.Entry(row1, textvariable=self.train_dataset).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="📁", command=self.browse_train_dataset, width=3).pack(side=tk.RIGHT)

        # Python环境
        row2 = ttk.Frame(basic_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Python路径:", width=12).pack(side=tk.LEFT)
        self.python_path = tk.StringVar(value=r"C:\Users\84820\anaconda3\envs\yolov11\python.exe")
        ttk.Entry(row2, textvariable=self.python_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row2, text="📁", command=self.browse_python, width=3).pack(side=tk.RIGHT)

        # 训练参数
        params_frame = ttk.LabelFrame(main_frame, text="训练参数", padding="15")
        params_frame.pack(fill=tk.X, pady=(0, 15))

        # 第一行
        row3 = ttk.Frame(params_frame)
        row3.pack(fill=tk.X, pady=2)

        ttk.Label(row3, text="训练轮次:", width=10).pack(side=tk.LEFT)
        self.epochs = tk.StringVar(value="100")
        ttk.Entry(row3, textvariable=self.epochs, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Label(row3, text="Batch Size:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        self.batch = tk.StringVar(value="16")
        ttk.Entry(row3, textvariable=self.batch, width=8).pack(side=tk.LEFT, padx=5)

        # 图片大小
        row4 = ttk.Frame(params_frame)
        row4.pack(fill=tk.X, pady=2)

        ttk.Label(row4, text="图片大小:", width=10).pack(side=tk.LEFT)
        self.imgsz = tk.StringVar(value="320")

        ttk.Radiobutton(row4, text="320", variable=self.imgsz, value="320").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(row4, text="416", variable=self.imgsz, value="416").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(row4, text="640", variable=self.imgsz, value="640").pack(side=tk.LEFT, padx=2)
        ttk.Entry(row4, textvariable=self.imgsz, width=8).pack(side=tk.LEFT, padx=5)

        # 设备选择
        row5 = ttk.Frame(params_frame)
        row5.pack(fill=tk.X, pady=2)

        ttk.Label(row5, text="使用设备:", width=10).pack(side=tk.LEFT)
        self.device = tk.StringVar(value="gpu" if self.has_gpu else "cpu")

        gpu_state = "可用" if self.has_gpu else "不可用"
        ttk.Radiobutton(row5, text=f"GPU ({gpu_state})", variable=self.device,
                        value="gpu", state=tk.NORMAL if self.has_gpu else tk.DISABLED).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(row5, text="CPU", variable=self.device, value="cpu").pack(side=tk.LEFT, padx=5)

        # 模型选择
        row6 = ttk.Frame(params_frame)
        row6.pack(fill=tk.X, pady=2)

        ttk.Label(row6, text="模型版本:", width=10).pack(side=tk.LEFT)
        self.model = tk.StringVar(value="yolo11n.pt")
        ttk.Combobox(row6, textvariable=self.model,
                     values=["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt"],
                     width=15).pack(side=tk.LEFT)

        # 进度显示 - 改为文本显示
        progress_frame = ttk.LabelFrame(main_frame, text="训练进度", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        # 进度信息 - 显示当前训练轮次/总训练轮次
        progress_info_frame = ttk.Frame(progress_frame)
        progress_info_frame.pack(fill=tk.X, pady=2)

        self.epoch_info = tk.StringVar(value="等待开始...")
        ttk.Label(progress_info_frame, textvariable=self.epoch_info, font=('微软雅黑', 10, 'bold')).pack(side=tk.LEFT,
                                                                                                         padx=5)

        self.loss_info = tk.StringVar(value="")
        ttk.Label(progress_info_frame, textvariable=self.loss_info).pack(side=tk.RIGHT, padx=5)

        # 命令预览
        preview_frame = ttk.LabelFrame(main_frame, text="命令预览", padding="10")
        preview_frame.pack(fill=tk.X, pady=(0, 15))

        self.preview_text = ScrolledText(preview_frame, height=3, font=('Consolas', 9))
        self.preview_text.pack(fill=tk.X)
        self.update_train_preview()

        # 绑定更新预览
        self.epochs.trace('w', lambda *args: self.update_train_preview())
        self.batch.trace('w', lambda *args: self.update_train_preview())
        self.imgsz.trace('w', lambda *args: self.update_train_preview())
        self.model.trace('w', lambda *args: self.update_train_preview())
        self.device.trace('w', lambda *args: self.update_train_preview())
        self.train_dataset.trace('w', lambda *args: self.update_train_preview())

        # 训练控制
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 15))

        self.train_btn = ttk.Button(control_frame, text="▶ 开始训练", command=self.start_training,
                                    width=15)
        self.train_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="⏹ 停止训练", command=self.stop_training,
                                   state=tk.DISABLED, width=15)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 训练输出
        output_frame = ttk.LabelFrame(main_frame, text="训练输出", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.train_output = ScrolledText(output_frame, height=12, font=('Consolas', 9),
                                         bg='#1e1e1e', fg='#d4d4d4')
        self.train_output.pack(fill=tk.BOTH, expand=True)

    def browse_train_dataset(self):
        """浏览训练数据集目录"""
        directory = filedialog.askdirectory(initialdir=self.train_dataset.get())
        if directory:
            self.train_dataset.set(directory)
            self.update_train_preview()

    def browse_python(self):
        """浏览Python可执行文件"""
        filepath = filedialog.askopenfilename(
            title="选择Python可执行文件",
            filetypes=[("Python", "python.exe"), ("All Files", "*.*")]
        )
        if filepath:
            self.python_path.set(filepath)

    def update_train_preview(self):
        """更新训练命令预览"""
        data_yaml = os.path.join(self.train_dataset.get(), 'data.yaml')
        device_arg = "0" if self.device.get() == "gpu" else "cpu"
        # 训练结果将保存在数据集目录的 runs/detect/ 下
        cmd = f"yolo train data={data_yaml} model={self.model.get()} epochs={self.epochs.get()} imgsz={self.imgsz.get()} batch={self.batch.get()} device={device_arg} project={self.train_dataset.get()} name=runs/detect/train exist_ok=True"

        self.preview_text.delete('1.0', tk.END)
        self.preview_text.insert('1.0', cmd)

    def start_training(self):
        """开始训练（改进版）- 显示当前训练轮次/总训练轮次"""
        data_yaml = os.path.join(self.train_dataset.get(), 'data.yaml')
        if not os.path.exists(data_yaml):
            messagebox.showerror("错误", f"data.yaml 不存在: {data_yaml}\n请先在配置向导中创建")
            return

        # 重置进度信息
        self.epoch_info.set("正在初始化...")
        self.loss_info.set("")

        device_arg = "0" if self.device.get() == "gpu" else "cpu"

        # 获取模型文件路径 - 优先使用数据集目录下的模型文件
        model_name = self.model.get()
        model_path = os.path.join(self.train_dataset.get(), model_name)
        if not os.path.exists(model_path):
            # 如果数据集目录下没有，尝试使用当前目录
            model_path = os.path.join(self.current_dir, model_name)
            if not os.path.exists(model_path):
                # 如果都没有，就使用默认的（YOLO会自动下载）
                model_path = model_name
                self.append_train_output(f"⚠️ 未找到本地模型文件 {model_name}，将自动下载\n")

        # 构建命令 - 指定保存到数据集目录的 runs/detect/ 下
        cmd = [
            "yolo",
            "train",
            f"data={data_yaml}",
            f"model={model_path}",
            f"epochs={self.epochs.get()}",
            f"imgsz={self.imgsz.get()}",
            f"batch={self.batch.get()}",
            f"device={device_arg}",
            f"project={self.train_dataset.get()}",
            "name=runs/detect/train",
            "exist_ok=True",
            "amp=True"
        ]

        self.train_output.delete('1.0', tk.END)
        self.train_output.insert('1.0', f"🚀 开始训练...\n")
        self.train_output.insert('1.0', f"📁 结果将保存到: {os.path.join(self.train_dataset.get(), 'runs/detect')}\n")
        self.train_output.insert('1.0', "=" * 50 + "\n")

        self.train_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        def run_training():
            try:
                import re
                # ANSI转义序列的正则表达式
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=False,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.train_process = process

                # 正则表达式匹配训练进度
                epoch_pattern = re.compile(r'Epoch\s+(\d+)/(\d+)')
                total_epochs = int(self.epochs.get())

                for line in process.stdout:
                    try:
                        # 尝试多种编码解码
                        try:
                            decoded_line = line.decode('utf-8', errors='ignore')
                        except:
                            try:
                                decoded_line = line.decode('gbk', errors='ignore')
                            except:
                                decoded_line = line.decode('latin-1', errors='ignore')

                        # 移除ANSI转义序列
                        clean_line = ansi_escape.sub('', decoded_line)

                        if clean_line.strip():
                            self.root.after(0, self.append_train_output, clean_line)

                            # 解析进度 - 更新当前训练轮次/总训练轮次
                            epoch_match = epoch_pattern.search(clean_line)
                            if epoch_match:
                                current_epoch = int(epoch_match.group(1))
                                self.root.after(0, self.update_epoch_info,
                                                f"当前训练: {current_epoch}/{total_epochs} 轮次")

                            # 解析损失
                            if 'cls_loss' in clean_line:
                                parts = clean_line.strip().split()
                                if len(parts) >= 8:
                                    loss_info = f"box: {parts[3]}, cls: {parts[4]}, dfl: {parts[5]}"
                                    self.root.after(0, self.loss_info.set, loss_info)

                    except Exception as e:
                        pass  # 忽略解析错误

                process.wait()

                if process.returncode == 0:
                    self.root.after(0, self.training_finished, True)
                else:
                    self.root.after(0, self.training_finished, False)

            except Exception as e:
                self.root.after(0, self.append_train_output, f"错误: {e}\n")
                self.root.after(0, self.training_finished, False)

        thread = threading.Thread(target=run_training)
        thread.daemon = True
        thread.start()

    def update_epoch_info(self, info):
        """更新训练轮次信息"""
        self.epoch_info.set(info)
        self.root.update_idletasks()

    def append_train_output(self, text):
        """添加训练输出"""
        try:
            self.train_output.insert(tk.END, text)
            self.train_output.see(tk.END)
            self.root.update_idletasks()
        except Exception as e:
            print(f"显示输出错误: {e}")

    def stop_training(self):
        """停止训练"""
        if self.train_process:
            self.train_process.terminate()
            self.append_train_output("\n🛑 训练已停止\n")
            self.training_finished(False)

    def training_finished(self, success):
        """训练完成"""
        self.train_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if success:
            self.epoch_info.set("训练完成！")

            # 查找训练结果（在数据集目录的runs/detect/下）
            detect_dir = os.path.join(self.train_dataset.get(), 'runs', 'detect')
            if os.path.exists(detect_dir):
                # 获取所有训练目录
                train_dirs = [d for d in Path(detect_dir).iterdir() if d.is_dir() and d.name.startswith('train')]
                if train_dirs:
                    # 按修改时间排序，最新的在前
                    train_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                    latest = train_dirs[0]
                    self.last_train_result = str(latest)
                    weights_dir = os.path.join(str(latest), 'weights')
                    if os.path.exists(weights_dir):
                        best_model = os.path.join(weights_dir, 'best.pt')
                        if os.path.exists(best_model):
                            self.last_model_path = best_model

                    msg = f"\n✅ 训练完成！\n"
                    msg += f"结果保存到: {self.last_train_result}\n"
                    if self.last_model_path:
                        msg += f"最佳模型: {self.last_model_path}"
                    self.append_train_output(msg)

                    # 更新测试和导出选项卡的默认模型路径
                    if hasattr(self, 'test_model') and self.last_model_path:
                        self.test_model.set(self.last_model_path)
                    if hasattr(self, 'export_model') and self.last_model_path:
                        self.export_model.set(self.last_model_path)

                    messagebox.showinfo("训练完成", msg)
        else:
            self.epoch_info.set("训练失败或已停止")

    # ==================== 测试选项卡 ====================
    def setup_test_tab(self):
        """设置测试选项卡"""
        main_frame = ttk.Frame(self.test_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title = ttk.Label(main_frame, text="🧪 模型测试", font=('微软雅黑', 14, 'bold'), foreground='#2196F3')
        title.pack(anchor=tk.W, pady=(0, 20))

        # 模型选择
        model_frame = ttk.LabelFrame(main_frame, text="模型选择", padding="15")
        model_frame.pack(fill=tk.X, pady=(0, 15))

        row1 = ttk.Frame(model_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="模型文件:", width=10).pack(side=tk.LEFT)
        self.test_model = tk.StringVar()
        if self.last_model_path:
            self.test_model.set(self.last_model_path)
        ttk.Entry(row1, textvariable=self.test_model).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="📁", command=self.browse_test_model, width=3).pack(side=tk.RIGHT)

        # 测试数据
        data_frame = ttk.LabelFrame(main_frame, text="测试数据", padding="15")
        data_frame.pack(fill=tk.X, pady=(0, 15))

        row2 = ttk.Frame(data_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="测试图片:", width=10).pack(side=tk.LEFT)
        self.test_source = tk.StringVar()
        ttk.Entry(row2, textvariable=self.test_source).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        btn_frame = ttk.Frame(row2)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="📷 选择图片", command=self.browse_test_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📁 选择文件夹", command=self.browse_test_folder).pack(side=tk.LEFT, padx=2)

        # 参数设置
        param_frame = ttk.LabelFrame(main_frame, text="测试参数", padding="15")
        param_frame.pack(fill=tk.X, pady=(0, 15))

        row3 = ttk.Frame(param_frame)
        row3.pack(fill=tk.X, pady=2)

        ttk.Label(row3, text="置信度阈值:", width=10).pack(side=tk.LEFT)
        self.test_conf = tk.StringVar(value="0.25")
        ttk.Entry(row3, textvariable=self.test_conf, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Label(row3, text="IOU阈值:", width=8).pack(side=tk.LEFT, padx=(20, 0))
        self.test_iou = tk.StringVar(value="0.45")
        ttk.Entry(row3, textvariable=self.test_iou, width=8).pack(side=tk.LEFT, padx=5)

        # 测试控制
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 15))

        self.test_btn = ttk.Button(control_frame, text="▶ 开始测试", command=self.start_test,
                                   width=15)
        self.test_btn.pack(side=tk.LEFT, padx=5)

        self.test_stop_btn = ttk.Button(control_frame, text="⏹ 停止测试", command=self.stop_test,
                                        state=tk.DISABLED, width=15)
        self.test_stop_btn.pack(side=tk.LEFT, padx=5)

        # 创建左右分栏
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左侧 - 文本输出
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        output_frame = ttk.LabelFrame(left_frame, text="测试输出", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.test_output = ScrolledText(output_frame, height=12, font=('Consolas', 9),
                                        bg='#1e1e1e', fg='#d4d4d4')
        self.test_output.pack(fill=tk.BOTH, expand=True)

        # 右侧 - 图片预览
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        preview_frame = ttk.LabelFrame(right_frame, text="检测结果预览", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True)

        # 预览画布
        self.preview_canvas = tk.Canvas(preview_frame, bg='white', highlightthickness=1,
                                        highlightbackground='#ccc')
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=5)

        self.preview_image_label = ttk.Label(self.preview_canvas)
        self.preview_image_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # 预览控制
        preview_control = ttk.Frame(preview_frame)
        preview_control.pack(fill=tk.X, pady=5)

        self.prev_btn = ttk.Button(preview_control, text="◀ 上一张",
                                   command=self.prev_image, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)

        self.next_btn = ttk.Button(preview_control, text="下一张 ▶",
                                   command=self.next_image, state=tk.DISABLED)
        self.next_btn.pack(side=tk.RIGHT, padx=5)

        self.preview_info = ttk.Label(preview_control, text="")
        self.preview_info.pack(side=tk.BOTTOM, pady=2)

        # 绑定画布大小变化事件，以便重新调整预览图片
        self.preview_canvas.bind('<Configure>', self.on_canvas_configure)

    def on_canvas_configure(self, event):
        """画布大小改变时重新显示当前图片"""
        if self.preview_images:
            self.show_preview()

    def browse_test_model(self):
        """浏览测试模型"""
        filepath = filedialog.askopenfilename(
            title="选择模型文件",
            filetypes=[("PyTorch Model", "*.pt"), ("All Files", "*.*")]
        )
        if filepath:
            self.test_model.set(filepath)

    def browse_test_image(self):
        """浏览测试图片"""
        filepath = filedialog.askopenfilename(
            title="选择测试图片",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp"), ("All Files", "*.*")]
        )
        if filepath:
            self.test_source.set(filepath)

    def browse_test_folder(self):
        """浏览测试文件夹"""
        directory = filedialog.askdirectory(title="选择测试图片文件夹")
        if directory:
            self.test_source.set(directory)

    def start_test(self):
        """开始测试"""
        if not self.test_model.get():
            messagebox.showerror("错误", "请选择模型文件")
            return

        if not self.test_source.get():
            messagebox.showerror("错误", "请选择测试图片或文件夹")
            return

        # 清空预览列表
        self.preview_images = []
        self.current_preview_index = 0
        self.prev_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.DISABLED)
        self.preview_info.config(text="")

        # 获取数据集根目录（从训练选项卡获取）
        dataset_root = self.train_dataset.get()

        # 构建测试命令 - 使用yolo命令格式
        cmd = [
            "yolo",
            "predict",
            f"model={self.test_model.get()}",
            f"source={self.test_source.get()}",
            f"conf={self.test_conf.get()}",
            f"iou={self.test_iou.get()}",
            f"project={dataset_root}",
            "name=runs/detect/predict",
            "exist_ok=True",
            "save=True"
        ]

        self.test_output.delete('1.0', tk.END)
        self.test_output.insert('1.0', f"🔍 开始测试...\n")
        self.test_output.insert('1.0', f"模型: {self.test_model.get()}\n")
        self.test_output.insert('1.0', f"测试源: {self.test_source.get()}\n")
        self.test_output.insert('1.0', f"数据集根目录: {dataset_root}\n")
        self.test_output.insert('1.0', "=" * 50 + "\n")

        self.test_btn.config(state=tk.DISABLED)
        self.test_stop_btn.config(state=tk.NORMAL)

        def run_test():
            try:
                import re
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=False,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.test_process = process

                for line in process.stdout:
                    try:
                        # 尝试多种编码解码
                        try:
                            decoded_line = line.decode('utf-8', errors='ignore')
                        except:
                            try:
                                decoded_line = line.decode('gbk', errors='ignore')
                            except:
                                decoded_line = line.decode('latin-1', errors='ignore')

                        # 移除ANSI转义序列
                        clean_line = ansi_escape.sub('', decoded_line)

                        if clean_line.strip():
                            self.root.after(0, self.append_test_output, clean_line)
                    except:
                        pass

                process.wait()

                if process.returncode == 0:
                    self.root.after(0, self.test_finished, True)
                else:
                    self.root.after(0, self.test_finished, False)

            except Exception as e:
                self.root.after(0, self.append_test_output, f"错误: {e}\n")
                self.root.after(0, self.test_finished, False)

        thread = threading.Thread(target=run_test)
        thread.daemon = True
        thread.start()

    def append_test_output(self, text):
        """添加测试输出"""
        self.test_output.insert(tk.END, text)
        self.test_output.see(tk.END)
        self.root.update_idletasks()

    def stop_test(self):
        """停止测试"""
        if self.test_process:
            self.test_process.terminate()
            self.append_test_output("\n🛑 测试已停止\n")
            self.test_finished(False)

    def test_finished(self, success):
        """测试完成"""
        self.test_btn.config(state=tk.NORMAL)
        self.test_stop_btn.config(state=tk.DISABLED)

        if success:
            self.append_test_output("\n✅ 测试完成！\n")

            # 查找最新的预测结果（在数据集目录的runs/detect/下）
            dataset_root = self.train_dataset.get()
            detect_dir = os.path.join(dataset_root, 'runs', 'detect')

            if os.path.exists(detect_dir):
                # 获取所有predict目录
                predict_dirs = [d for d in Path(detect_dir).iterdir() if d.is_dir() and d.name.startswith('predict')]
                if predict_dirs:
                    # 按修改时间排序，最新的在前
                    predict_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                    latest_predict = predict_dirs[0]

                    self.append_test_output(f"结果保存到: {latest_predict}\n")

                    # 加载预览图片
                    self.preview_images = list(latest_predict.glob('*.jpg')) + \
                                          list(latest_predict.glob('*.png'))
                    if self.preview_images:
                        self.current_preview_index = 0
                        self.show_preview()
                        self.prev_btn.config(state=tk.NORMAL)
                        self.next_btn.config(state=tk.NORMAL)
                        self.preview_info.config(text=f"共 {len(self.preview_images)} 张结果图片")
                    else:
                        self.append_test_output("⚠️ 未找到预览图片\n")
                else:
                    self.append_test_output(f"⚠️ 未找到预测结果目录\n")
            else:
                self.append_test_output(f"⚠️ 检测目录不存在: {detect_dir}\n")

    def show_preview(self):
        """显示预览图片，自适应画布大小"""
        if not self.preview_images:
            return

        img_path = self.preview_images[self.current_preview_index]
        try:
            # 加载并缩放图片
            img = Image.open(img_path)

            # 获取画布大小
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()

            if canvas_width > 10 and canvas_height > 10:
                # 计算缩放比例，保持宽高比，留出边距
                max_width = canvas_width - 20
                max_height = canvas_height - 20

                # 复制图片以避免修改原图
                img_copy = img.copy()
                img_copy.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # 转换为PhotoImage
                photo = ImageTk.PhotoImage(img_copy)
                self.preview_image_label.config(image=photo)
                self.preview_image_label.image = photo  # 保持引用

                # 更新信息
                self.preview_info.config(
                    text=f"{img_path.name} ({self.current_preview_index + 1}/{len(self.preview_images)})")

        except Exception as e:
            self.append_test_output(f"预览错误: {e}\n")

    def prev_image(self):
        """上一张图片"""
        if self.preview_images and self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.show_preview()

    def next_image(self):
        """下一张图片"""
        if self.preview_images and self.current_preview_index < len(self.preview_images) - 1:
            self.current_preview_index += 1
            self.show_preview()

    # ==================== 导出选项卡 ====================
    def setup_export_tab(self):
        """设置导出选项卡"""
        main_frame = ttk.Frame(self.export_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title = ttk.Label(main_frame, text="📦 模型导出", font=('微软雅黑', 14, 'bold'), foreground='#2196F3')
        title.pack(anchor=tk.W, pady=(0, 20))

        # 模型选择
        model_frame = ttk.LabelFrame(main_frame, text="源模型", padding="15")
        model_frame.pack(fill=tk.X, pady=(0, 15))

        row1 = ttk.Frame(model_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="模型文件:", width=10).pack(side=tk.LEFT)
        self.export_model = tk.StringVar()
        if self.last_model_path:
            self.export_model.set(self.last_model_path)
        ttk.Entry(row1, textvariable=self.export_model).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="📁", command=self.browse_export_model, width=3).pack(side=tk.RIGHT)

        # 导出参数
        param_frame = ttk.LabelFrame(main_frame, text="导出参数", padding="15")
        param_frame.pack(fill=tk.X, pady=(0, 15))

        row2 = ttk.Frame(param_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="导出格式:", width=10).pack(side=tk.LEFT)
        self.export_format = tk.StringVar(value="onnx")
        format_combo = ttk.Combobox(row2, textvariable=self.export_format,
                                    values=["onnx", "torchscript", "engine", "openvino"],
                                    width=15)
        format_combo.pack(side=tk.LEFT)

        row3 = ttk.Frame(param_frame)
        row3.pack(fill=tk.X, pady=2)

        ttk.Label(row3, text="图片大小:", width=10).pack(side=tk.LEFT)
        self.export_imgsz = tk.StringVar(value="320")
        ttk.Entry(row3, textvariable=self.export_imgsz, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(row3, text="(如: 320)").pack(side=tk.LEFT)

        # 精度选择
        precision_frame = ttk.LabelFrame(main_frame, text="精度设置", padding="15")
        precision_frame.pack(fill=tk.X, pady=(0, 15))

        row4 = ttk.Frame(precision_frame)
        row4.pack(fill=tk.X, pady=2)

        self.export_precision = tk.StringVar(value="fp32")

        ttk.Radiobutton(row4, text="FP32 (32位浮点, 无损)", variable=self.export_precision,
                        value="fp32").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(row4, text="FP16 (16位半精度, 体积减半)", variable=self.export_precision,
                        value="fp16").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(row4, text="INT8 (8位整数量化, 体积最小)", variable=self.export_precision,
                        value="int8").pack(anchor=tk.W, pady=2)

        # 导出按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        self.export_btn = ttk.Button(btn_frame, text="📦 导出模型", command=self.export_model_func,
                                     width=15)
        self.export_btn.pack(side=tk.LEFT, padx=5)

        # 导出输出
        output_frame = ttk.LabelFrame(main_frame, text="导出输出", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.export_output = ScrolledText(output_frame, height=10, font=('Consolas', 9),
                                          bg='#1e1e1e', fg='#d4d4d4')
        self.export_output.pack(fill=tk.BOTH, expand=True)

    def browse_export_model(self):
        """浏览导出模型"""
        filepath = filedialog.askopenfilename(
            title="选择要导出的模型文件",
            filetypes=[("PyTorch Model", "*.pt"), ("All Files", "*.*")]
        )
        if filepath:
            self.export_model.set(filepath)

    def export_model_func(self):
        """导出模型"""
        if not self.export_model.get():
            messagebox.showerror("错误", "请选择要导出的模型文件")
            return

        # 构建导出命令
        half = 'True' if self.export_precision.get() == 'fp16' else 'False'
        int8 = 'True' if self.export_precision.get() == 'int8' else 'False'

        cmd = [
            "yolo",
            "export",
            f"model={self.export_model.get()}",
            f"format={self.export_format.get()}",
            f"imgsz={self.export_imgsz.get()}",
            f"half={half}",
            f"int8={int8}"
        ]

        self.export_output.delete('1.0', tk.END)
        self.export_output.insert('1.0', f"📦 开始导出...\n")
        self.export_output.insert('1.0', f"模型: {self.export_model.get()}\n")
        self.export_output.insert('1.0', f"格式: {self.export_format.get()}\n")
        self.export_output.insert('1.0', f"精度: {self.export_precision.get()}\n")
        self.export_output.insert('1.0', "=" * 50 + "\n")

        self.export_btn.config(state=tk.DISABLED)

        def run_export():
            try:
                import re
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=False,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                for line in process.stdout:
                    try:
                        decoded_line = line.decode('utf-8', errors='ignore')
                        clean_line = ansi_escape.sub('', decoded_line)
                        if clean_line.strip():
                            self.root.after(0, self.append_export_output, clean_line)
                    except:
                        pass

                process.wait()

                if process.returncode == 0:
                    self.root.after(0, self.export_finished, True)
                else:
                    self.root.after(0, self.export_finished, False)

            except Exception as e:
                self.root.after(0, self.append_export_output, f"错误: {e}\n")
                self.root.after(0, self.export_finished, False)

        thread = threading.Thread(target=run_export)
        thread.daemon = True
        thread.start()

    def append_export_output(self, text):
        """添加导出输出"""
        self.export_output.insert(tk.END, text)
        self.export_output.see(tk.END)
        self.root.update_idletasks()

    def export_finished(self, success):
        """导出完成"""
        self.export_btn.config(state=tk.NORMAL)

        if success:
            self.append_export_output("\n✅ 导出完成！\n")

            # 显示导出文件位置
            model_path = Path(self.export_model.get())
            export_path = model_path.with_suffix(f'.{self.export_format.get()}')
            if self.export_format.get() == 'onnx':
                export_path = model_path.with_suffix('.onnx')
            elif self.export_format.get() == 'torchscript':
                export_path = model_path.with_suffix('.torchscript')
            elif self.export_format.get() == 'engine':
                export_path = model_path.with_suffix('.engine')
            elif self.export_format.get() == 'openvino':
                export_path = model_path.parent / f"{model_path.stem}_openvino_model"

            if os.path.exists(str(export_path)):
                size_mb = os.path.getsize(str(export_path)) / (1024 * 1024) if os.path.isfile(str(export_path)) else 0
                self.append_export_output(f"导出文件: {export_path}\n")
                if size_mb > 0:
                    self.append_export_output(f"文件大小: {size_mb:.2f} MB\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = YOLODataPrepApp(root)
    root.mainloop()