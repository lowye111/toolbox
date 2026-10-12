import cv2
import glob
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui_theme


class VideoFrameExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("视频抽帧工具")
        self.root.geometry("1100x940")
        self.root.minsize(980, 740)
        self.root.resizable(True, True)

        self.video_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.extract_mode = tk.StringVar(value="interval")
        self.frame_interval = tk.StringVar(value="30")
        self.time_interval = tk.StringVar(value="5.0")
        self.specific_frames = tk.StringVar(value="100,200,500")

        self.video_info = {
            "fps": 0.0,
            "total_frames": 0,
            "duration": 0.0,
            "width": 0,
            "height": 0
        }

        self.is_extracting = False
        self._cancel_flag = False
        # 关窗标志：置位后抽帧线程不再回调 UI，避免对已销毁的窗口调用 after 抛 TclError
        self._closing = False
        # 记录上一次“自动生成”的默认输出目录，用于判断用户是否手工改过输出目录
        self._auto_output_dir = ""

        self._setup_style()
        self._create_widgets()

        # 关窗时先通知抽帧线程停止
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        ui_theme.center(self.root, 1100, 940, min_w=980, min_h=740)

    def _setup_style(self):
        ui_theme.apply(self.root)

    def _create_widgets(self):
        self.root.grid_rowconfigure(5, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # ===== 顶部标题 =====
        title_frame = ttk.Frame(self.root, padding=(20, 8))
        title_frame.grid(row=0, column=0, sticky="ew")
        title_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(
            title_frame,
            text="视频抽帧工具",
            font=ui_theme.ui_font(18, True),
            foreground=ui_theme.COLORS["primary"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        ttk.Label(
            title_frame,
            text="支持按帧间隔、按时间间隔、按指定帧号抽取图片",
            style="Tip.TLabel"
        ).grid(row=1, column=0, sticky="w")

        # ===== 视频文件选择 =====
        frame_video = ttk.LabelFrame(self.root, text="视频文件选择", padding=(15, 8))
        frame_video.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        frame_video.grid_columnconfigure(1, weight=1)

        ttk.Label(frame_video, text="视频路径：").grid(row=0, column=0, padx=5, pady=4, sticky="w")
        self.entry_video = ttk.Entry(frame_video, textvariable=self.video_path)
        self.entry_video.grid(row=0, column=1, padx=5, pady=4, sticky="ew")

        self.btn_video_browse = ttk.Button(frame_video, text="浏览", command=self._select_video, width=10)
        self.btn_video_browse.grid(row=0, column=2, padx=5, pady=4)

        self.btn_parse = ttk.Button(frame_video, text="解析视频信息", command=self._parse_video_info, width=14)
        self.btn_parse.grid(row=1, column=1, padx=5, pady=4, sticky="w")

        # ===== 视频信息 =====
        frame_info = ttk.LabelFrame(self.root, text="视频基本信息", padding=(15, 8))
        frame_info.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        frame_info.grid_columnconfigure(0, weight=1)

        self.info_label = ttk.Label(
            frame_info,
            text="未解析视频信息，请先选择视频文件并点击“解析视频信息”，或直接点击“开始抽帧”自动解析。",
            style="Info.TLabel",
            wraplength=1000,
            justify="left"
        )
        self.info_label.grid(row=0, column=0, padx=5, pady=4, sticky="w")

        # ===== 抽帧模式 =====
        frame_mode = ttk.LabelFrame(self.root, text="抽帧模式设置", padding=(15, 8))
        frame_mode.grid(row=3, column=0, sticky="ew", padx=20, pady=6)
        frame_mode.grid_columnconfigure(0, weight=1)

        radio_frame = ttk.Frame(frame_mode)
        radio_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        radio_frame.grid_columnconfigure(0, weight=1)

        ttk.Radiobutton(
            radio_frame,
            text="按帧数间隔抽帧",
            variable=self.extract_mode,
            value="interval",
            command=self._switch_mode
        ).grid(row=0, column=0, padx=10, pady=4, sticky="w")

        ttk.Radiobutton(
            radio_frame,
            text="按时间间隔抽帧",
            variable=self.extract_mode,
            value="time",
            command=self._switch_mode
        ).grid(row=1, column=0, padx=10, pady=4, sticky="w")

        ttk.Radiobutton(
            radio_frame,
            text="抽取指定帧",
            variable=self.extract_mode,
            value="specific",
            command=self._switch_mode
        ).grid(row=2, column=0, padx=10, pady=4, sticky="w")

        self.mode_frame = ttk.Frame(frame_mode)
        self.mode_frame.grid(row=1, column=0, sticky="ew")
        self.mode_frame.grid_columnconfigure(1, weight=1)

        self._switch_mode()

        # ===== 输出目录 =====
        frame_output = ttk.LabelFrame(self.root, text="输出路径设置", padding=(15, 8))
        frame_output.grid(row=4, column=0, sticky="ew", padx=20, pady=6)
        frame_output.grid_columnconfigure(1, weight=1)

        ttk.Label(frame_output, text="输出目录：").grid(row=0, column=0, padx=5, pady=4, sticky="w")
        self.entry_output = ttk.Entry(frame_output, textvariable=self.output_dir)
        self.entry_output.grid(row=0, column=1, padx=5, pady=4, sticky="ew")

        self.btn_output_browse = ttk.Button(frame_output, text="浏览", command=self._select_output_dir, width=10)
        self.btn_output_browse.grid(row=0, column=2, padx=5, pady=4)

        self.btn_auto_output = ttk.Button(frame_output, text="自动生成", command=self._auto_fill_output_dir, width=10)
        self.btn_auto_output.grid(row=0, column=3, padx=5, pady=4)

        # ===== 控制区 =====
        frame_control = ttk.Frame(self.root, padding=(20, 10))
        frame_control.grid(row=5, column=0, sticky="nsew")
        frame_control.grid_columnconfigure(0, weight=1)
        frame_control.grid_rowconfigure(2, weight=1)

        btn_area = ttk.Frame(frame_control)
        btn_area.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        btn_area.grid_columnconfigure(0, weight=1)

        btn_row = ttk.Frame(btn_area)
        btn_row.grid(row=0, column=0, pady=4)

        self.btn_extract = ttk.Button(
            btn_row,
            text="开始抽帧",
            command=self._start_extract,
            style="Accent.TButton",
            width=22
        )
        self.btn_extract.grid(row=0, column=0)

        self.btn_cancel = ttk.Button(
            btn_row,
            text="取消",
            command=self._cancel_extract,
            width=12,
            state="disabled"
        )
        self.btn_cancel.grid(row=0, column=1, padx=(10, 0))

        # 进度条
        progress_frame = ttk.LabelFrame(frame_control, text="处理进度", padding=(15, 8))
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=5, pady=4)

        self.progress_label = ttk.Label(progress_frame, text="等待开始...", style="Tip.TLabel")
        self.progress_label.grid(row=1, column=0, sticky="w", padx=5)

        # 日志区
        log_frame = ttk.LabelFrame(frame_control, text="运行日志", padding=(15, 8))
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            font=ui_theme.mono_font(10)
        )
        ui_theme.style_text(self.log_text)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)

        self._log("程序启动完成。")

    def _log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def _ui_call(self, func):
        """从抽帧线程安全地回到 UI 线程；窗口已关闭时直接丢弃回调。"""
        if self._closing:
            return
        try:
            self.root.after(0, func)
        except tk.TclError:
            # 窗口正在销毁，忽略即可，不影响抽帧线程收尾
            self._closing = True

    def _set_extracting_state(self, extracting):
        self.is_extracting = extracting
        state = "disabled" if extracting else "normal"

        self.btn_video_browse.config(state=state)
        self.btn_output_browse.config(state=state)
        self.btn_auto_output.config(state=state)
        self.btn_parse.config(state=state)
        self.btn_extract.config(state=state)
        self.entry_video.config(state=state)
        self.entry_output.config(state=state)
        # 抽帧中才能点“取消”
        self.btn_cancel.config(state="normal" if extracting else "disabled")

    def _cancel_extract(self):
        if not self.is_extracting:
            return
        self._cancel_flag = True
        self.btn_cancel.config(state="disabled")
        self.progress_label.config(text="正在取消，请稍候...")
        self._log("已请求取消抽帧，等待当前帧处理完成后停止...")

    def _on_close(self):
        # 关窗前先置位取消/关窗标志，避免抽帧线程继续写文件或回调已销毁的窗口
        self._closing = True
        if self.is_extracting:
            self._cancel_flag = True
        self.root.destroy()

    def _select_video(self):
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.mpeg *.mpg"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            # 判断当前输出目录是否仍是上一个视频“自动生成”的默认值
            current_output = self.output_dir.get().strip()
            is_auto_default = bool(self._auto_output_dir) and current_output == self._auto_output_dir

            self.video_path.set(file_path)
            self._log(f"已选择视频：{file_path}")

            # 自动填充默认输出目录：输出目录为空，或仍等于上一个视频的自动默认值
            # （说明用户没手工填过），则跟随新视频更新
            if not current_output or is_auto_default:
                self._auto_fill_output_dir()

    def _select_output_dir(self):
        dir_path = filedialog.askdirectory(title="选择抽帧输出目录")
        if dir_path:
            self.output_dir.set(dir_path)
            self._log(f"已选择输出目录：{dir_path}")

    def _auto_fill_output_dir(self):
        video_path = self.video_path.get().strip()
        if not video_path:
            messagebox.showwarning("提示", "请先选择视频文件！")
            return

        base_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        auto_dir = os.path.join(base_dir, f"{video_name}_frames")
        self.output_dir.set(auto_dir)
        # 记住这个自动生成的默认值，供 _select_video 判断是否跟随新视频更新
        self._auto_output_dir = auto_dir
        self._log(f"已自动生成输出目录：{auto_dir}")

    def _read_video_info(self, video_path):
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError("请选择有效的视频文件！")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("无法打开视频文件，请检查文件是否损坏！")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps and fps > 0 else 0

        cap.release()

        if fps <= 0 or total_frames <= 0:
            raise RuntimeError("读取到的视频信息无效，无法进行抽帧！")

        return {
            "fps": round(fps, 4),
            "total_frames": total_frames,
            "duration": round(duration, 4),
            "width": width,
            "height": height
        }

    def _parse_video_info(self):
        video_path = self.video_path.get().strip()

        try:
            self.video_info = self._read_video_info(video_path)
            self._refresh_video_info_display()
            self._switch_mode()
            self._log("视频信息解析完成。")
            messagebox.showinfo("成功", "视频信息解析完成！")
        except Exception as e:
            messagebox.showerror("错误", str(e))
            self._log(f"视频信息解析失败：{e}")

    def _refresh_video_info_display(self):
        info_text = (
            f"帧率：{self.video_info['fps']} fps\n"
            f"总帧数：{self.video_info['total_frames']}\n"
            f"总时长：{self.video_info['duration']} 秒\n"
            f"分辨率：{self.video_info['width']} x {self.video_info['height']}"
        )
        self.info_label.config(text=info_text)

    def _switch_mode(self):
        for widget in self.mode_frame.winfo_children():
            widget.destroy()

        mode = self.extract_mode.get()
        total_frames = self.video_info.get("total_frames", 0)
        duration = self.video_info.get("duration", 0)

        if mode == "interval":
            ttk.Label(self.mode_frame, text="抽帧间隔（帧数）：").grid(
                row=0, column=0, padx=5, pady=4, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.frame_interval).grid(
                row=0, column=1, padx=5, pady=4, sticky="ew"
            )

            tip = (
                f"说明：每隔 N 帧抽取 1 帧，例如填 30 表示每 30 帧抽 1 张。"
                f"{' 当前视频总帧数：' + str(total_frames) if total_frames > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=4, sticky="w"
            )

        elif mode == "time":
            ttk.Label(self.mode_frame, text="抽帧间隔（秒）：").grid(
                row=0, column=0, padx=5, pady=4, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.time_interval).grid(
                row=0, column=1, padx=5, pady=4, sticky="ew"
            )

            tip = (
                f"说明：每隔 N 秒抽取 1 帧，例如填 5 表示每 5 秒抽 1 张。"
                f"{' 当前视频总时长：' + str(duration) + ' 秒' if duration > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=4, sticky="w"
            )

        elif mode == "specific":
            ttk.Label(self.mode_frame, text="指定帧号（逗号分隔）：").grid(
                row=0, column=0, padx=5, pady=4, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.specific_frames).grid(
                row=0, column=1, padx=5, pady=4, sticky="ew"
            )

            tip = (
                f"说明：输入要抽取的帧号，例如 10,50,120。"
                f"{' 有效范围：0 ~ ' + str(total_frames - 1) if total_frames > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=4, sticky="w"
            )

    def _validate_and_prepare_params(self):
        video_path = self.video_path.get().strip()
        output_dir = self.output_dir.get().strip()

        if not video_path or not os.path.exists(video_path):
            raise ValueError("请选择有效的视频文件！")

        # 自动解析视频信息，避免必须手动先点“解析视频信息”
        self.video_info = self._read_video_info(video_path)
        self._refresh_video_info_display()
        self._switch_mode()

        if not output_dir:
            self._auto_fill_output_dir()
            output_dir = self.output_dir.get().strip()

        if not output_dir:
            raise ValueError("请选择抽帧输出目录！")

        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        mode = self.extract_mode.get()

        params = {
            "video_path": video_path,
            "output_dir": output_dir,
            "extract_mode": mode,
            "frame_interval": None,
            "time_interval": None,
            "specific_frames": None
        }

        if mode == "interval":
            text = self.frame_interval.get().strip()
            if not text:
                raise ValueError("请输入抽帧间隔（帧数）！")

            frame_interval = int(text)
            if frame_interval <= 0:
                raise ValueError("帧数间隔必须是大于 0 的整数！")

            params["frame_interval"] = frame_interval

        elif mode == "time":
            text = self.time_interval.get().strip()
            if not text:
                raise ValueError("请输入抽帧间隔（秒）！")

            time_interval = float(text)
            if time_interval <= 0:
                raise ValueError("时间间隔必须是大于 0 的数字！")

            params["time_interval"] = time_interval

        elif mode == "specific":
            frames_str = self.specific_frames.get().strip()
            if not frames_str:
                raise ValueError("请输入指定的帧号（逗号分隔）！")

            raw_list = [x.strip() for x in frames_str.split(",") if x.strip()]
            if not raw_list:
                raise ValueError("请输入有效的帧号列表！")

            frame_list = []
            for item in raw_list:
                # 先按整数解析，再单独校验范围："--5" 这类非法输入会在这里解析失败，
                # 而不是拖到后面抛 ValueError 并报出与真实原因不符的错误
                try:
                    frame_num = int(item)
                except ValueError:
                    raise ValueError(f"帧号“{item}”不是有效整数！")
                if frame_num < 0:
                    raise ValueError(f"帧号 {frame_num} 不能为负数（帧号从 0 开始）！")
                if frame_num >= self.video_info["total_frames"]:
                    raise ValueError(
                        f"帧号 {frame_num} 超出有效范围（0 ~ {self.video_info['total_frames'] - 1}）！"
                    )
                frame_list.append(frame_num)

            # 去重并排序
            frame_list = sorted(set(frame_list))

            params["specific_frames"] = frame_list

        return params

    def _start_extract(self):
        if self.is_extracting:
            return

        try:
            params = self._validate_and_prepare_params()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            self._log(f"参数校验失败：{e}")
            return

        # 覆盖防护：输出目录已有同名模式的帧文件时，先让用户确认一次
        existing = glob.glob(os.path.join(params["output_dir"], "frame_*_time_*s.jpg"))
        if existing:
            confirmed = messagebox.askyesno(
                "确认覆盖",
                f"输出目录中已存在 {len(existing)} 个抽帧文件：\n{params['output_dir']}\n\n"
                f"继续将覆盖同名文件，是否继续？"
            )
            if not confirmed:
                self.progress_label.config(text="已取消")
                self._log("用户取消了本次抽帧（输出目录已有同名文件）。")
                return
            self._log(f"输出目录已存在 {len(existing)} 个同名帧文件，用户确认覆盖。")

        self.progress["value"] = 0
        self.progress_label.config(text="开始处理...")
        self._log("开始抽帧...")
        self._log(f"视频文件：{params['video_path']}")
        self._log(f"输出目录：{params['output_dir']}")
        self._log(f"抽取模式：{params['extract_mode']}")

        if params["extract_mode"] == "interval":
            self._log(f"帧数间隔：{params['frame_interval']}")
        elif params["extract_mode"] == "time":
            self._log(f"时间间隔：{params['time_interval']} 秒")
        elif params["extract_mode"] == "specific":
            self._log(f"指定帧号：{params['specific_frames']}")

        self._cancel_flag = False
        self._set_extracting_state(True)

        thread = threading.Thread(target=self._video_frame_extract_worker, args=(params,), daemon=True)
        thread.start()

    def _video_frame_extract_worker(self, params):
        try:
            result = self._video_frame_extract(
                video_path=params["video_path"],
                output_dir=params["output_dir"],
                extract_mode=params["extract_mode"],
                frame_interval=params["frame_interval"],
                time_interval=params["time_interval"],
                specific_frames=params["specific_frames"]
            )

            self._ui_call(lambda: self._on_extract_success(result))
        except Exception as e:
            # 注意：except 块结束时会自动 del e，必须先用默认参数把异常对象绑定进闭包
            self._ui_call(lambda err=e: self._on_extract_error(err))

    def _on_extract_success(self, result):
        self._set_extracting_state(False)
        self._cancel_flag = False

        failed_count = result.get("failed_count", 0)

        if result.get("cancelled"):
            self.progress_label.config(text="已取消")
            self._log("抽帧已取消。")
            self._log(f"已抽取 {result['extracted_count']} 帧")
            if failed_count:
                self._log(f"保存失败 {failed_count} 帧")
            messagebox.showinfo(
                "已取消",
                f"抽帧已取消。\n\n"
                f"已抽取：{result['extracted_count']} 帧"
                + (f"\n保存失败：{failed_count} 帧" if failed_count else "")
                + f"\n保存目录：{result['output_dir']}"
            )
            return

        self.progress["value"] = 100
        self.progress_label.config(text="抽帧完成")
        self._log("抽帧完成。")
        self._log(f"共抽取 {result['extracted_count']} 帧")
        if failed_count:
            self._log(f"有 {failed_count} 帧保存失败（imwrite 返回 False），请检查输出目录权限或磁盘空间。")
        self._log(f"保存目录：{result['output_dir']}")

        messagebox.showinfo(
            "完成",
            f"抽帧完成！\n\n"
            f"共抽取：{result['extracted_count']} 帧\n"
            + (f"保存失败：{failed_count} 帧\n" if failed_count else "")
            + f"保存目录：{result['output_dir']}"
        )

    def _on_extract_error(self, error):
        self._set_extracting_state(False)
        self._cancel_flag = False
        self.progress_label.config(text="抽帧失败")
        self._log(f"抽帧失败：{error}")
        messagebox.showerror("错误", str(error))

    def _video_frame_extract(
        self,
        video_path,
        output_dir,
        extract_mode="interval",
        frame_interval=None,
        time_interval=None,
        specific_frames=None
    ):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频：{video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total_frames <= 0:
            cap.release()
            raise RuntimeError("视频帧率或总帧数无效，无法抽帧！")

        extracted_count = 0
        failed_count = 0
        frame_count = 0
        cancelled = False

        # 指定帧模式时使用集合，加快判断
        target_frame_set = set(specific_frames) if specific_frames else set()

        # 时间模式：使用“目标时间点”而不是 current_time-last_extract_time
        # 更稳定，能真正按指定秒数间隔抽取
        next_extract_time = 0.0

        while True:
            # 取消检查：每帧读完后立即响应取消请求
            if self._cancel_flag:
                cancelled = True
                self._ui_call(lambda: self._log("抽帧已取消。"))
                break

            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_count / fps
            need_save = False

            if extract_mode == "interval":
                if frame_interval is None or frame_interval <= 0:
                    cap.release()
                    raise ValueError("无效的帧数间隔参数！")

                if frame_count % frame_interval == 0:
                    need_save = True

            elif extract_mode == "time":
                if time_interval is None or time_interval <= 0:
                    cap.release()
                    raise ValueError("无效的时间间隔参数！")

                # 加一个很小的容差，避免浮点数误差导致跳过
                if current_time + 1e-9 >= next_extract_time:
                    need_save = True
                    next_extract_time += time_interval

            elif extract_mode == "specific":
                if frame_count in target_frame_set:
                    need_save = True

            if need_save:
                save_path = os.path.join(
                    output_dir,
                    f"frame_{frame_count:06d}_time_{current_time:.3f}s.jpg"
                )
                success = cv2.imwrite(save_path, frame)
                if success:
                    extracted_count += 1
                else:
                    # imwrite 返回 False 表示这一帧没写成功（磁盘满、权限不足、
                    # 路径过长或编码器不支持等），必须记录并计入失败
                    failed_count += 1
                    self._ui_call(
                        lambda p=save_path: self._log(f"保存失败（imwrite 返回 False）：{p}")
                    )

            # 指定帧模式：若所有目标帧都取完则提前结束
            if extract_mode == "specific" and target_frame_set:
                if frame_count in target_frame_set:
                    target_frame_set.remove(frame_count)
                if not target_frame_set:
                    frame_count += 1
                    progress_percent = frame_count / total_frames * 100
                    self._ui_call(
                        lambda p=progress_percent, c=frame_count, t=total_frames: self._update_progress(p, c, t)
                    )
                    break

            frame_count += 1

            # 每处理一定帧数更新一次进度，避免界面过度刷新
            if frame_count % 10 == 0 or frame_count == total_frames:
                progress_percent = frame_count / total_frames * 100
                self._ui_call(
                    lambda p=progress_percent, c=frame_count, t=total_frames: self._update_progress(p, c, t)
                )

        cap.release()

        return {
            "extracted_count": extracted_count,
            "failed_count": failed_count,
            "cancelled": cancelled,
            "output_dir": output_dir
        }

    def _update_progress(self, percent, current_frame, total_frames):
        self.progress["value"] = percent
        self.progress_label.config(
            text=f"处理中：{current_frame}/{total_frames} 帧（{percent:.1f}%）"
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoFrameExtractorGUI(root)
    root.mainloop()