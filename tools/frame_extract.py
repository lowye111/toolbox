import cv2
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


class VideoFrameExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("视频抽帧工具")
        self.root.geometry("1100x820")
        self.root.minsize(980, 720)
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

        self._setup_style()
        self._create_widgets()

    def _setup_style(self):
        default_font = ("SimHei", 11)
        title_font = ("SimHei", 12, "bold")
        big_btn_font = ("SimHei", 12, "bold")

        style = ttk.Style(self.root)
        style.configure(".", font=default_font)
        style.configure("TLabelframe.Label", font=title_font)
        style.configure("Accent.TButton", font=big_btn_font)
        style.configure("Info.TLabel", font=("SimHei", 11), foreground="#1f1f1f")
        style.configure("Tip.TLabel", font=("SimHei", 10), foreground="gray")

    def _create_widgets(self):
        self.root.grid_rowconfigure(5, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # ===== 顶部标题 =====
        title_frame = ttk.Frame(self.root, padding=(20, 15))
        title_frame.grid(row=0, column=0, sticky="ew")
        title_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(
            title_frame,
            text="视频抽帧工具",
            font=("SimHei", 18, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        ttk.Label(
            title_frame,
            text="支持按帧间隔、按时间间隔、按指定帧号抽取图片",
            style="Tip.TLabel"
        ).grid(row=1, column=0, sticky="w")

        # ===== 视频文件选择 =====
        frame_video = ttk.LabelFrame(self.root, text="视频文件选择", padding=(15, 12))
        frame_video.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        frame_video.grid_columnconfigure(1, weight=1)

        ttk.Label(frame_video, text="视频路径：").grid(row=0, column=0, padx=5, pady=8, sticky="w")
        self.entry_video = ttk.Entry(frame_video, textvariable=self.video_path)
        self.entry_video.grid(row=0, column=1, padx=5, pady=8, sticky="ew")

        self.btn_video_browse = ttk.Button(frame_video, text="浏览", command=self._select_video, width=10)
        self.btn_video_browse.grid(row=0, column=2, padx=5, pady=8)

        self.btn_parse = ttk.Button(frame_video, text="解析视频信息", command=self._parse_video_info, width=14)
        self.btn_parse.grid(row=1, column=1, padx=5, pady=8, sticky="w")

        # ===== 视频信息 =====
        frame_info = ttk.LabelFrame(self.root, text="视频基本信息", padding=(15, 12))
        frame_info.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        frame_info.grid_columnconfigure(0, weight=1)

        self.info_label = ttk.Label(
            frame_info,
            text="未解析视频信息，请先选择视频文件并点击“解析视频信息”，或直接点击“开始抽帧”自动解析。",
            style="Info.TLabel",
            wraplength=1000,
            justify="left"
        )
        self.info_label.grid(row=0, column=0, padx=5, pady=8, sticky="w")

        # ===== 抽帧模式 =====
        frame_mode = ttk.LabelFrame(self.root, text="抽帧模式设置", padding=(15, 12))
        frame_mode.grid(row=3, column=0, sticky="ew", padx=20, pady=10)
        frame_mode.grid_columnconfigure(0, weight=1)

        radio_frame = ttk.Frame(frame_mode)
        radio_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        radio_frame.grid_columnconfigure(0, weight=1)

        ttk.Radiobutton(
            radio_frame,
            text="按帧数间隔抽帧",
            variable=self.extract_mode,
            value="interval",
            command=self._switch_mode
        ).grid(row=0, column=0, padx=10, pady=5, sticky="w")

        ttk.Radiobutton(
            radio_frame,
            text="按时间间隔抽帧",
            variable=self.extract_mode,
            value="time",
            command=self._switch_mode
        ).grid(row=1, column=0, padx=10, pady=5, sticky="w")

        ttk.Radiobutton(
            radio_frame,
            text="抽取指定帧",
            variable=self.extract_mode,
            value="specific",
            command=self._switch_mode
        ).grid(row=2, column=0, padx=10, pady=5, sticky="w")

        self.mode_frame = ttk.Frame(frame_mode)
        self.mode_frame.grid(row=1, column=0, sticky="ew")
        self.mode_frame.grid_columnconfigure(1, weight=1)

        self._switch_mode()

        # ===== 输出目录 =====
        frame_output = ttk.LabelFrame(self.root, text="输出路径设置", padding=(15, 12))
        frame_output.grid(row=4, column=0, sticky="ew", padx=20, pady=10)
        frame_output.grid_columnconfigure(1, weight=1)

        ttk.Label(frame_output, text="输出目录：").grid(row=0, column=0, padx=5, pady=8, sticky="w")
        self.entry_output = ttk.Entry(frame_output, textvariable=self.output_dir)
        self.entry_output.grid(row=0, column=1, padx=5, pady=8, sticky="ew")

        self.btn_output_browse = ttk.Button(frame_output, text="浏览", command=self._select_output_dir, width=10)
        self.btn_output_browse.grid(row=0, column=2, padx=5, pady=8)

        self.btn_auto_output = ttk.Button(frame_output, text="自动生成", command=self._auto_fill_output_dir, width=10)
        self.btn_auto_output.grid(row=0, column=3, padx=5, pady=8)

        # ===== 控制区 =====
        frame_control = ttk.Frame(self.root, padding=(20, 10))
        frame_control.grid(row=5, column=0, sticky="nsew")
        frame_control.grid_columnconfigure(0, weight=1)
        frame_control.grid_rowconfigure(2, weight=1)

        btn_area = ttk.Frame(frame_control)
        btn_area.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        btn_area.grid_columnconfigure(0, weight=1)

        self.btn_extract = ttk.Button(
            btn_area,
            text="开始抽帧",
            command=self._start_extract,
            style="Accent.TButton",
            width=22
        )
        self.btn_extract.grid(row=0, column=0, pady=8)

        # 进度条
        progress_frame = ttk.LabelFrame(frame_control, text="处理进度", padding=(15, 12))
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=5, pady=8)

        self.progress_label = ttk.Label(progress_frame, text="等待开始...", style="Tip.TLabel")
        self.progress_label.grid(row=1, column=0, sticky="w", padx=5)

        # 日志区
        log_frame = ttk.LabelFrame(frame_control, text="运行日志", padding=(15, 12))
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)

        self._log("程序启动完成。")

    def _log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

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

    def _select_video(self):
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.mpeg *.mpg"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.video_path.set(file_path)
            self._log(f"已选择视频：{file_path}")

            # 自动填充默认输出目录
            if not self.output_dir.get().strip():
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
                row=0, column=0, padx=5, pady=8, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.frame_interval).grid(
                row=0, column=1, padx=5, pady=8, sticky="ew"
            )

            tip = (
                f"说明：每隔 N 帧抽取 1 帧，例如填 30 表示每 30 帧抽 1 张。"
                f"{' 当前视频总帧数：' + str(total_frames) if total_frames > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=8, sticky="w"
            )

        elif mode == "time":
            ttk.Label(self.mode_frame, text="抽帧间隔（秒）：").grid(
                row=0, column=0, padx=5, pady=8, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.time_interval).grid(
                row=0, column=1, padx=5, pady=8, sticky="ew"
            )

            tip = (
                f"说明：每隔 N 秒抽取 1 帧，例如填 5 表示每 5 秒抽 1 张。"
                f"{' 当前视频总时长：' + str(duration) + ' 秒' if duration > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=8, sticky="w"
            )

        elif mode == "specific":
            ttk.Label(self.mode_frame, text="指定帧号（逗号分隔）：").grid(
                row=0, column=0, padx=5, pady=8, sticky="w"
            )
            ttk.Entry(self.mode_frame, textvariable=self.specific_frames).grid(
                row=0, column=1, padx=5, pady=8, sticky="ew"
            )

            tip = (
                f"说明：输入要抽取的帧号，例如 10,50,120。"
                f"{' 有效范围：0 ~ ' + str(total_frames - 1) if total_frames > 0 else ''}"
            )
            ttk.Label(self.mode_frame, text=tip, style="Tip.TLabel", wraplength=700).grid(
                row=0, column=2, padx=10, pady=8, sticky="w"
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
                if not item.lstrip("-").isdigit():
                    raise ValueError(f"帧号“{item}”不是有效整数！")
                frame_num = int(item)
                if frame_num < 0 or frame_num >= self.video_info["total_frames"]:
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

            self.root.after(0, lambda: self._on_extract_success(result))
        except Exception as e:
            self.root.after(0, lambda: self._on_extract_error(e))

    def _on_extract_success(self, result):
        self._set_extracting_state(False)
        self.progress["value"] = 100
        self.progress_label.config(text="抽帧完成")
        self._log("抽帧完成。")
        self._log(f"共抽取 {result['extracted_count']} 帧")
        self._log(f"保存目录：{result['output_dir']}")

        messagebox.showinfo(
            "完成",
            f"抽帧完成！\n\n"
            f"共抽取：{result['extracted_count']} 帧\n"
            f"保存目录：{result['output_dir']}"
        )

    def _on_extract_error(self, error):
        self._set_extracting_state(False)
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
        frame_count = 0

        # 指定帧模式时使用集合，加快判断
        target_frame_set = set(specific_frames) if specific_frames else set()

        # 时间模式：使用“目标时间点”而不是 current_time-last_extract_time
        # 更稳定，能真正按指定秒数间隔抽取
        next_extract_time = 0.0

        while True:
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

            # 指定帧模式：若所有目标帧都取完则提前结束
            if extract_mode == "specific" and target_frame_set:
                if frame_count in target_frame_set:
                    target_frame_set.remove(frame_count)
                if not target_frame_set:
                    frame_count += 1
                    progress_percent = frame_count / total_frames * 100
                    self.root.after(
                        0,
                        lambda p=progress_percent, c=frame_count, t=total_frames: self._update_progress(p, c, t)
                    )
                    break

            frame_count += 1

            # 每处理一定帧数更新一次进度，避免界面过度刷新
            if frame_count % 10 == 0 or frame_count == total_frames:
                progress_percent = frame_count / total_frames * 100
                self.root.after(
                    0,
                    lambda p=progress_percent, c=frame_count, t=total_frames: self._update_progress(p, c, t)
                )

        cap.release()

        return {
            "extracted_count": extracted_count,
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