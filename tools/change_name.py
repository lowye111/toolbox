import os
import shutil
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui_theme


def _is_ascii_number(text):
    """严格判断是否可为 int() 解析的纯 ASCII 数字（isdigit() 对 '²' 也返回 True，不能直接用）"""
    return text.isascii() and text.isdigit()


class FileRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件批量重命名工具")
        self.root.geometry("750x650")

        # 设置现代化样式
        self.setup_styles()

        # 创建主框架
        main_frame = ttk.Frame(root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = ttk.Label(title_frame, text="🔄 文件批量重命名工具",
                                font=ui_theme.ui_font(14, True), foreground=ui_theme.COLORS["primary"])
        title_label.pack(side=tk.LEFT)

        # 功能选择卡片
        func_card = ttk.LabelFrame(main_frame, text="功能选择", padding="10")
        func_card.pack(fill=tk.X, pady=(0, 10))

        self.function_var = tk.StringVar(value="number_modify")

        func_frame = ttk.Frame(func_card)
        func_frame.pack()

        ttk.Radiobutton(func_frame, text="📊 数字后缀修改",
                        variable=self.function_var, value="number_modify",
                        command=self.toggle_function).pack(side=tk.LEFT, padx=20)
        ttk.Radiobutton(func_frame, text="📝 文件名修改",
                        variable=self.function_var, value="filename_modify",
                        command=self.toggle_function).pack(side=tk.LEFT, padx=20)

        # 路径设置卡片
        path_card = ttk.LabelFrame(main_frame, text="路径设置", padding="10")
        path_card.pack(fill=tk.X, pady=(0, 10))

        # 源目录
        source_frame = ttk.Frame(path_card)
        source_frame.pack(fill=tk.X, pady=2)

        ttk.Label(source_frame, text="源目录:", width=8).pack(side=tk.LEFT)
        self.source_path = tk.StringVar(value="")
        ttk.Entry(source_frame, textvariable=self.source_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(source_frame, text="📁", command=self.browse_source, width=3).pack(side=tk.RIGHT)

        # 保存位置
        save_frame = ttk.Frame(path_card)
        save_frame.pack(fill=tk.X, pady=2)

        self.save_in_place = tk.BooleanVar(value=True)
        ttk.Checkbutton(save_frame, text="保存在原位", variable=self.save_in_place,
                        command=self.toggle_save_location).pack(side=tk.LEFT)

        # 目标目录容器
        self.target_container = ttk.Frame(path_card)
        self.target_container.pack(fill=tk.X, pady=2)

        target_inner = ttk.Frame(self.target_container)
        target_inner.pack(fill=tk.X)

        ttk.Label(target_inner, text="目标目录:", width=8).pack(side=tk.LEFT)
        self.target_path = tk.StringVar(value="")
        ttk.Entry(target_inner, textvariable=self.target_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(target_inner, text="📁", command=self.browse_target, width=3).pack(side=tk.RIGHT)

        # 参数卡片
        self.params_card = ttk.LabelFrame(main_frame, text="参数设置", padding="10")
        self.params_card.pack(fill=tk.X, pady=(0, 10))

        # 数字后缀修改参数
        self.number_frame = ttk.Frame(self.params_card)

        # 操作类型
        op_frame = ttk.Frame(self.number_frame)
        op_frame.pack(fill=tk.X, pady=2)
        ttk.Label(op_frame, text="操作:", width=8).pack(side=tk.LEFT)
        self.operation_var = tk.StringVar(value="+")
        ttk.Radiobutton(op_frame, text="增加 +", variable=self.operation_var, value="+").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(op_frame, text="减少 -", variable=self.operation_var, value="-").pack(side=tk.LEFT, padx=5)
        ttk.Label(op_frame, text="数值:", width=6).pack(side=tk.LEFT, padx=(20, 0))
        self.modify_value = tk.StringVar(value="1")
        ttk.Entry(op_frame, textvariable=self.modify_value, width=8).pack(side=tk.LEFT)

        # 数字范围
        range_frame = ttk.Frame(self.number_frame)
        range_frame.pack(fill=tk.X, pady=2)
        ttk.Label(range_frame, text="范围:", width=8).pack(side=tk.LEFT)
        self.range_from = tk.StringVar(value="201")
        ttk.Entry(range_frame, textvariable=self.range_from, width=8).pack(side=tk.LEFT)
        ttk.Label(range_frame, text="至").pack(side=tk.LEFT, padx=5)
        self.range_to = tk.StringVar(value="227")
        ttk.Entry(range_frame, textvariable=self.range_to, width=8).pack(side=tk.LEFT)

        # 文件名修改参数
        self.filename_frame = ttk.Frame(self.params_card)

        name_frame = ttk.Frame(self.filename_frame)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="起始数字:", width=8).pack(side=tk.LEFT)
        self.start_number = tk.StringVar(value="229")
        ttk.Entry(name_frame, textvariable=self.start_number, width=8).pack(side=tk.LEFT)
        ttk.Label(name_frame, text="(同名文件同数字)", font=ui_theme.ui_font(8), foreground=ui_theme.COLORS["text_muted"]).pack(side=tk.LEFT,
                                                                                                     padx=10)

        # 预览卡片
        preview_card = ttk.LabelFrame(main_frame, text="预览", padding="10")
        preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 预览文本框
        preview_frame = ttk.Frame(preview_card)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_text = tk.Text(preview_frame, height=12, width=80,
                                    font=ui_theme.mono_font(9), wrap=tk.WORD)
        ui_theme.style_text(self.preview_text)
        scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=scrollbar.set)

        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        btn_inner = ttk.Frame(btn_frame)
        btn_inner.pack()

        ttk.Button(btn_inner, text="👁️ 预览", command=self.preview_changes,
                   width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_inner, text="⚡ 执行", command=self.execute_rename,
                   style="Accent.TButton", width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_inner, text="🧹 清除", command=self.clear_preview,
                   width=12).pack(side=tk.LEFT, padx=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ui_theme.make_status_bar(main_frame, self.status_var, fill=tk.X, pady=(8, 0))

        # 初始状态
        self.target_container.pack_forget()
        self.toggle_function()

        ui_theme.center(self.root, 750, 650, min_w=680, min_h=560)

    def setup_styles(self):
        """应用统一主题"""
        ui_theme.apply(self.root)

    def browse_source(self):
        directory = filedialog.askdirectory(initialdir=self.source_path.get())
        if directory:
            self.source_path.set(directory)
            self.status_var.set(f"已选择源目录: {directory}")

    def browse_target(self):
        directory = filedialog.askdirectory(initialdir=self.target_path.get())
        if directory:
            self.target_path.set(directory)
            self.status_var.set(f"已选择目标目录: {directory}")

    def toggle_save_location(self):
        if self.save_in_place.get():
            self.target_container.pack_forget()
            self.status_var.set("模式: 直接修改原文件")
        else:
            self.target_container.pack(fill=tk.X, pady=2)
            self.status_var.set("模式: 复制到新目录")

    def toggle_function(self):
        # 清空参数卡片
        for widget in self.params_card.winfo_children():
            widget.pack_forget()

        if self.function_var.get() == "number_modify":
            self.number_frame.pack(fill=tk.X)
            self.status_var.set("功能: 数字后缀修改")
        else:
            self.filename_frame.pack(fill=tk.X)
            self.status_var.set("功能: 文件名修改")

    def get_files_info(self):
        source_dir = self.source_path.get()
        if not os.path.exists(source_dir):
            messagebox.showerror("错误", "源目录不存在！")
            return None

        files = []
        for filename in os.listdir(source_dir):
            filepath = os.path.join(source_dir, filename)
            if os.path.isfile(filepath):
                name, ext = os.path.splitext(filename)
                files.append({
                    'original_name': filename,
                    'name': name,
                    'ext': ext,
                    'path': filepath
                })
        return files

    def preview_changes(self):
        files = self.get_files_info()
        if files is None:
            return

        self.preview_text.delete(1.0, tk.END)

        if self.function_var.get() == "number_modify":
            self.preview_number_modify(files)
        else:
            self.preview_filename_modify(files)

    def preview_number_modify(self, files):
        try:
            range_from = int(self.range_from.get())
            range_to = int(self.range_to.get())
            modify_value = int(self.modify_value.get())
            operation = self.operation_var.get()

            target_files = []
            for f in files:
                if _is_ascii_number(f['name']):
                    num = int(f['name'])
                    if range_from <= num <= range_to:
                        target_files.append(f)

            target_files.sort(key=lambda x: int(x['name']))

            if operation == "+":
                target_files.reverse()

            self.preview_text.insert(tk.END, f"📊 找到 {len(target_files)} 个符合条件的文件\n")
            self.preview_text.insert(tk.END, "─" * 50 + "\n")

            for f in target_files:
                old_num = int(f['name'])
                new_num = old_num + modify_value if operation == "+" else old_num - modify_value
                new_name = f"{new_num}{f['ext']}"
                arrow = "→" if operation == "+" else "←"
                self.preview_text.insert(tk.END, f"{f['original_name']:30} {arrow} {new_name}\n")

            self.status_var.set(f"预览完成: {len(target_files)} 个文件将被修改")

        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字！")

    def preview_filename_modify(self, files):
        try:
            start_num = int(self.start_number.get())

            non_digit_files = [f for f in files if not _is_ascii_number(f['name'])]

            name_groups = {}
            for f in non_digit_files:
                base_name = f['name']
                if base_name not in name_groups:
                    name_groups[base_name] = []
                name_groups[base_name].append(f)

            self.preview_text.insert(tk.END, f"📝 找到 {len(non_digit_files)} 个非数字命名的文件\n")
            self.preview_text.insert(tk.END, "─" * 50 + "\n")

            current_num = start_num
            for base_name, group in name_groups.items():
                for f in group:
                    new_name = f"{current_num}{f['ext']}"
                    self.preview_text.insert(tk.END, f"{f['original_name']:30} → {new_name}\n")
                current_num += 1

            self.status_var.set(f"预览完成: {len(non_digit_files)} 个文件将被重命名")

        except ValueError:
            messagebox.showerror("错误", "请输入有效的起始数字！")

    def collect_target_names(self, files):
        """按当前参数算出本批次将产生的目标文件名（只读计算，不修改任何文件），参数非法时返回 None"""
        target_names = []
        if self.function_var.get() == "number_modify":
            try:
                range_from = int(self.range_from.get())
                range_to = int(self.range_to.get())
                modify_value = int(self.modify_value.get())
            except ValueError:
                return None
            operation = self.operation_var.get()
            for f in files:
                if _is_ascii_number(f['name']):
                    num = int(f['name'])
                    if range_from <= num <= range_to:
                        new_num = num + modify_value if operation == "+" else num - modify_value
                        target_names.append(f"{new_num}{f['ext']}")
        else:
            try:
                start_num = int(self.start_number.get())
            except ValueError:
                return None
            name_groups = {}
            for f in files:
                if not _is_ascii_number(f['name']):
                    name_groups.setdefault(f['name'], []).append(f)
            current_num = start_num
            for base_name, group in name_groups.items():
                for f in group:
                    target_names.append(f"{current_num}{f['ext']}")
                current_num += 1
        return target_names

    def execute_rename(self):
        if not messagebox.askyesno("确认", "确定要执行重命名操作吗？此操作不可逆！"):
            return

        files = self.get_files_info()
        if files is None:
            return

        if self.save_in_place.get():
            target_dir = self.source_path.get()
        else:
            target_dir = self.target_path.get()
            os.makedirs(target_dir, exist_ok=True)

        # 冲突检查：复制模式（shutil.copy2）会静默覆盖目标目录中的同名文件，执行前先确认
        if not self.save_in_place.get():
            target_names = self.collect_target_names(files)
            if target_names is None:
                return
            conflicts = []
            if os.path.isdir(target_dir):
                for name in target_names:
                    if os.path.exists(os.path.join(target_dir, name)):
                        conflicts.append(name)
            seen = set()
            for name in target_names:
                if name in seen and name not in conflicts:
                    conflicts.append(name)
                seen.add(name)
            if conflicts:
                preview = "\n".join(conflicts[:10])
                more = f"\n... 等共 {len(conflicts)} 个" if len(conflicts) > 10 else ""
                if not messagebox.askyesno(
                        "目标文件已存在",
                        f"以下 {len(conflicts)} 个目标文件已存在，继续将覆盖它们：\n\n{preview}{more}\n\n是否继续？"):
                    self.status_var.set("已取消：存在同名目标文件")
                    return

        success_count = 0
        error_count = 0

        if self.function_var.get() == "number_modify":
            success_count, error_count = self.execute_number_modify(files, target_dir)
        else:
            success_count, error_count = self.execute_filename_modify(files, target_dir)

        result_msg = f"✅ 完成！成功: {success_count} | 失败: {error_count}"
        messagebox.showinfo("完成", result_msg)
        self.status_var.set(result_msg)
        self.preview_changes()

    def execute_number_modify(self, files, target_dir):
        try:
            range_from = int(self.range_from.get())
            range_to = int(self.range_to.get())
            modify_value = int(self.modify_value.get())
            operation = self.operation_var.get()

            target_files = []
            for f in files:
                if _is_ascii_number(f['name']):
                    num = int(f['name'])
                    if range_from <= num <= range_to:
                        target_files.append(f)

            if operation == "+":
                target_files.sort(key=lambda x: int(x['name']), reverse=True)
            else:
                target_files.sort(key=lambda x: int(x['name']))

            success_count = 0
            error_count = 0

            for f in target_files:
                try:
                    old_num = int(f['name'])
                    new_num = old_num + modify_value if operation == "+" else old_num - modify_value
                    new_name = f"{new_num}{f['ext']}"

                    if self.save_in_place.get():
                        new_path = os.path.join(target_dir, new_name)
                        os.rename(f['path'], new_path)
                    else:
                        new_path = os.path.join(target_dir, new_name)
                        shutil.copy2(f['path'], new_path)

                    success_count += 1
                except Exception as e:
                    print(f"处理文件 {f['original_name']} 时出错: {e}")
                    error_count += 1

            return success_count, error_count

        except Exception as e:
            messagebox.showerror("错误", f"执行过程中出错: {e}")
            return 0, 0

    def execute_filename_modify(self, files, target_dir):
        try:
            start_num = int(self.start_number.get())

            non_digit_files = [f for f in files if not _is_ascii_number(f['name'])]

            name_groups = {}
            for f in non_digit_files:
                base_name = f['name']
                if base_name not in name_groups:
                    name_groups[base_name] = []
                name_groups[base_name].append(f)

            success_count = 0
            error_count = 0
            current_num = start_num

            for base_name, group in name_groups.items():
                for f in group:
                    try:
                        new_name = f"{current_num}{f['ext']}"

                        if self.save_in_place.get():
                            new_path = os.path.join(target_dir, new_name)
                            os.rename(f['path'], new_path)
                        else:
                            new_path = os.path.join(target_dir, new_name)
                            shutil.copy2(f['path'], new_path)

                        success_count += 1
                    except Exception as e:
                        print(f"处理文件 {f['original_name']} 时出错: {e}")
                        error_count += 1
                current_num += 1

            return success_count, error_count

        except Exception as e:
            messagebox.showerror("错误", f"执行过程中出错: {e}")
            return 0, 0

    def clear_preview(self):
        self.preview_text.delete(1.0, tk.END)
        self.status_var.set("预览已清除")


if __name__ == "__main__":
    root = tk.Tk()
    app = FileRenamerApp(root)
    root.mainloop()