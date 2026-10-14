import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_theme
import env_check

# 长按判定：按住超过这个毫秒数即进入拖动模式（短按仍是启动工具）
LONG_PRESS_MS = 350
# 判定为"开始拖动"前允许的鼠标移动量（像素）；超过则视为误触，取消长按
DRAG_TOLERANCE = 6

# ---- 拖动动画参数 ----
CARD_GAP = 10          # 卡片之间的垂直间距
ANIM_INTERVAL = 12     # 动画帧间隔（毫秒），约 80fps
ANIM_EASE = 0.30       # 其它卡片让位时每帧向目标靠近的比例（越大越快）
SETTLE_EPS = 0.6       # 与目标距离小于该值即吸附，避免长尾抖动
DRAG_SHADOW = 3        # 拖动中卡片阴影偏移量（营造"抬起"感）


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
            {"name": "抓歌打包器", "description": "输入歌名 → 生成 zip（MP3/FLAC + 封面 + 歌词），拖进 QQ/微信即可发到手机", "file": "tools/music_grabber.py", "icon": "🎵"},
        ]

        # 卡片控件与拖动状态
        self.cards = {}          # file -> {"card","widgets","tool","y","target_y","lifted"}
        self.drag = None         # 拖动中的临时状态
        self._order_dirty = False
        self._anim_job = None    # 位移动画的 after id

        self._load_order()
        self._create_widgets()
        self.check_environment()

    # ==================== 顺序持久化 ====================

    def _load_order(self):
        """按 config.json 里保存的顺序重排 self.tools。

        未记录的新工具按定义顺序追加到末尾；
        已不存在的工具会被忽略。这样以后新增/删除工具都不会乱。
        """
        saved = env_check.load_config().get("tool_order") or []
        if not isinstance(saved, list) or not saved:
            return
        by_file = {t["file"]: t for t in self.tools}
        ordered = [by_file[f] for f in saved if f in by_file]
        known = {t["file"] for t in ordered}
        ordered.extend(t for t in self.tools if t["file"] not in known)
        if len(ordered) == len(self.tools):
            self.tools = ordered

    def _save_order(self):
        """把当前顺序写回 config.json"""
        try:
            cfg = env_check.load_config()
            cfg["tool_order"] = [t["file"] for t in self.tools]
            env_check.save_config(cfg)
            self._order_dirty = False
        except Exception as e:
            messagebox.showwarning("提示", f"顺序保存失败：{e}")

    # ==================== 界面 ====================

    def _create_widgets(self):
        c = ui_theme.COLORS

        # 顶部标题区
        header = tk.Frame(self.root, bg=c["surface"])
        header.pack(fill=tk.X)
        header_inner = tk.Frame(header, bg=c["surface"])
        header_inner.pack(fill=tk.X, padx=22, pady=(18, 16))
        tk.Label(header_inner, text="🛠️ 工具箱", bg=c["surface"], fg=c["primary"],
                 font=ui_theme.ui_font(17, True)).pack(anchor="w")
        tk.Label(header_inner, text="点击卡片启动 · 长按卡片可拖动排序",
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

        self._render_cards()

        # 底部提示
        footer = tk.Frame(self.root, bg=c["bg"])
        footer.pack(fill=tk.X, padx=22, pady=(0, 12))
        tk.Label(footer, text="点击卡片启动 · 长按拖动排序（顺序会自动记住）",
                 bg=c["bg"], fg=c["text_muted"],
                 font=ui_theme.ui_font(9)).pack(anchor="w")

    def _render_cards(self):
        """按 self.tools 的顺序重建卡片（用 place 绝对定位，便于做位移动画）"""
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        self.cards.clear()
        for tool in self.tools:
            self._create_card(self.scrollable_frame, tool)
        # 重建后先把卡片摆到各自的目标位置（无动画）
        self.scrollable_frame.update_idletasks()
        self._layout_cards(animate=False)

    def _card_height(self):
        """卡片高度：取一张实测值，避免每帧重复测量导致抖动"""
        for tool in self.tools:
            info = self.cards.get(tool["file"])
            if info:
                try:
                    h = info["card"].winfo_reqheight()
                    if h > 1:
                        return h
                except Exception:
                    pass
        return 64

    def _slot_y(self, index):
        """第 index 个卡片的目标 y 坐标"""
        return index * (self._card_height() + CARD_GAP)

    def _layout_cards(self, animate=True):
        """把每张卡片移动到它当前顺序对应的位置。

        animate=True 时用逐帧缓动（各自卡片向目标值靠近），
        这样换位时有平滑的"让位"动画，而不是瞬间跳过去。
        """
        frame = self.scrollable_frame
        h = self._card_height()
        total = max(1, len(self.tools) * (h + CARD_GAP))
        frame.configure(height=total)

        for i, tool in enumerate(self.tools):
            info = self.cards.get(tool["file"])
            if not info:
                continue
            card = info["card"]
            target = self._slot_y(i)
            info["target_y"] = target
            if not animate:
                info["y"] = target
                card.place(x=0, relwidth=1.0, y=target, height=h)
            elif info.get("y") is None:
                info["y"] = target
                card.place(x=0, relwidth=1.0, y=target, height=h)
        if animate:
            self._anim_step()

    def _anim_step(self):
        """一帧缓动：让每张卡片朝自己的目标槽位靠近一点"""
        self._anim_job = None
        moving = False
        for tool in self.tools:
            info = self.cards.get(tool["file"])
            if not info or info.get("y") is None:
                continue
            cur = info["y"]
            target = info.get("target_y", cur)
            diff = target - cur
            # 正在被拖动的卡片不受缓动影响（它的位置由鼠标决定）
            if self.drag and self.drag.get("active") and info["tool"] is self.drag["tool"]:
                continue
            if abs(diff) < SETTLE_EPS:
                if cur != target:
                    info["y"] = target
                    info["card"].place_configure(y=int(target))
                continue
            moving = True
            new_y = cur + diff * ANIM_EASE
            info["y"] = new_y
            info["card"].place_configure(y=int(round(new_y)))
        if moving:
            self._anim_job = self.root.after(ANIM_INTERVAL, self._anim_step)

    def _create_card(self, parent, tool):
        """创建单个工具卡片（悬停高亮、短按启动、长按拖动排序）

        卡片用 place 绝对定位（而不是 pack），这样拖动时可以对 y 坐标做动画。
        """
        c = ui_theme.COLORS

        # 卡片固定 1px 边框；拖动高亮改用外层额外边框，避免改 highlightthickness
        # 导致尺寸变化、整列卡片跟着抖动
        card = tk.Frame(parent, bg=c["surface"], highlightbackground=c["border"],
                        highlightthickness=1, cursor="hand2")

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
        self.cards[tool["file"]] = {
            "card": card, "widgets": widgets, "tool": tool,
            "y": None,          # 当前显示位置（动画插值用，浮点）
            "target_y": 0,      # 目标槽位
            "lifted": False,    # 是否处于"拿起"状态
        }

        def set_hover(hover):
            if self.cards.get(tool["file"], {}).get("lifted"):
                return          # 拖动中不叠加 hover 效果
            bg = c["hover"] if hover else c["surface"]
            for w in widgets:
                w.configure(bg=bg)
            card.configure(highlightbackground=c["primary"] if hover else c["border"])

        def on_enter(_event):
            if self.drag is None:
                set_hover(True)

        def on_leave(_event):
            if self.drag is None and not self._pointer_in(card):
                set_hover(False)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, t=tool, c_=card: self._on_press(e, t, c_))
            w.bind("<B1-Motion>", self._on_motion)
            w.bind("<ButtonRelease-1>", lambda e, t=tool: self._on_release(e, t))
            w.bind("<MouseWheel>", self.on_mousewheel)

    # ==================== 长按拖动 ====================

    def _on_press(self, event, tool, card):
        """按下：起一个定时器，按住够久就进入拖动模式"""
        self.drag = {
            "tool": tool,
            "card": card,
            "press_xy": (event.x_root, event.y_root),
            "active": False,       # 是否已进入拖动模式
            "cancelled": False,    # 是否因移动过多而取消
            "timer": None,
            "insert_index": None,
            "grab_dy": 0,          # 按下点相对卡片顶部的偏移（拖动时保持不变）
        }
        self.drag["timer"] = self.root.after(LONG_PRESS_MS, self._enter_drag_mode)

    def _enter_drag_mode(self):
        """长按到时：进入拖动模式（把卡片"抬起来"）"""
        d = self.drag
        if not d or d["cancelled"]:
            return
        d["active"] = True
        info = self.cards.get(d["tool"]["file"])
        if not info:
            return

        # 记下抓取点相对卡片顶部的偏移：之后卡片跟随鼠标移动时保持这个偏移，
        # 手感才像"捏住了卡片的这个位置"，而不是卡片突然跳到鼠标下
        press_y = d["press_xy"][1]
        try:
            d["grab_dy"] = press_y - info["card"].winfo_rooty()
        except Exception:
            d["grab_dy"] = 0
        d["insert_index"] = self.tools.index(d["tool"])

        # 抬起来：换描边颜色但保持 thickness=1（改粗细会让整列卡片抖动），
        # 用阴影色背景 + 提前抬高一点做视觉反馈
        info["card"].configure(highlightbackground=ui_theme.COLORS["primary"],
                               highlightcolor=ui_theme.COLORS["primary"])
        info["lifted"] = True
        for w in info["widgets"]:
            w.configure(cursor="fleur")
        self.root.configure(cursor="fleur")

    def _on_motion(self, event):
        d = self.drag
        if not d:
            return
        # 还没进入拖动模式时，若移动过多就取消长按（避免"想点却轻微滑动"被当成拖动）
        if not d["active"]:
            x0, y0 = d["press_xy"]
            if abs(event.x_root - x0) > DRAG_TOLERANCE or abs(event.y_root - y0) > DRAG_TOLERANCE:
                d["cancelled"] = True
                if d["timer"]:
                    self.root.after_cancel(d["timer"])
                    d["timer"] = None
            return

        self._follow_cursor(event.y_root)
        self._reorder_to(event.y_root)
        self._autoscroll(event.y_root)

    def _follow_cursor(self, y_root):
        """让被拖动的卡片跟随鼠标（保持按下时的抓取偏移）"""
        d = self.drag
        info = self.cards.get(d["tool"]["file"])
        if not info:
            return
        try:
            frame_top = self.scrollable_frame.winfo_rooty()
        except Exception:
            return
        # y_root 是屏幕坐标，转成滚动内容里的坐标
        canvas_y = y_root - self.canvas.winfo_rooty()
        content_y = self.canvas.canvasy(canvas_y)
        new_y = content_y - d["grab_dy"]
        # 限制在内容范围内，避免拖出边界后卡片"飞走"
        max_y = max(0, len(self.tools) * (self._card_height() + CARD_GAP))
        new_y = max(0, min(new_y, max_y))
        info["y"] = new_y
        info["target_y"] = new_y
        info["card"].place_configure(y=int(round(new_y)))

    def _reorder_to(self, y_root):
        """根据鼠标位置，把正在拖的卡片插到对应下标（只改顺序，位置交给动画）"""
        d = self.drag
        index = self._index_at(y_root)
        if index is None or index == d.get("insert_index"):
            return
        d["insert_index"] = index

        tool = d["tool"]
        cur = self.tools.index(tool)
        if index == cur:
            return

        # 只交换顺序并更新各卡片的目标位置，实际位移交给缓动动画：
        # 这样其它卡片是"滑开让位"，而不是瞬间跳过去
        self.tools.pop(cur)
        self.tools.insert(index, tool)
        self._layout_cards(animate=True)

    def _index_at(self, y_root):
        """算出鼠标纵向位置对应的插入下标。

        用卡片的目标槽位（而非当前动画位置）计算：动画进行中卡片位置是
        滞后的，若按当前位置算，换位判定会来回抖动、反复插入。
        """
        n = len(self.tools)
        if n == 0:
            return 0
        h = self._card_height()
        try:
            content_top = self.scrollable_frame.winfo_rooty()
        except Exception:
            return n - 1
        rel = y_root - content_top
        idx = int(rel // (h + CARD_GAP))
        return max(0, min(idx, n - 1))

    def _autoscroll(self, y_root):
        """拖到可视区域上下边缘时自动滚动（越靠边滚得越快）"""
        try:
            top = self.canvas.winfo_rooty()
            height = self.canvas.winfo_height()
        except Exception:
            return
        margin = 34
        step = 0
        if y_root < top + margin:
            ratio = 1.0 - max(0.0, (y_root - top)) / margin
            step = -max(1, int(round(ratio * 3)))
        elif y_root > top + height - margin:
            ratio = 1.0 - max(0.0, (top + height - y_root)) / margin
            step = max(1, int(round(ratio * 3)))
        if step:
            self.canvas.yview_scroll(step, "units")
            # 滚动后内容整体位移，拖动中的卡片要重新贴合鼠标
            self._follow_cursor(y_root)

    def _on_release(self, event, tool):
        """松手：短按则启动工具；长按拖动过则保存顺序（不启动）

        注意：必须以 self.drag["tool"] 为准，不能用事件参数里的 tool。
        拖动过程中顺序会变化，松手时鼠标下的卡片可能已经不是按住的那张，
        用事件参数会导致被拖卡片的高亮状态清不掉。
        """
        d = self.drag
        self.drag = None
        self.root.configure(cursor="")

        if d and d["timer"]:
            self.root.after_cancel(d["timer"])
            d["timer"] = None

        dragged_tool = d["tool"] if d else tool
        was_drag = bool(d and d["active"])

        # 清理被拖卡片的状态（用真正的被拖对象）
        info = self.cards.get(dragged_tool["file"])
        if info:
            info["lifted"] = False
            info["card"].configure(highlightbackground=ui_theme.COLORS["border"],
                                   highlightcolor=ui_theme.COLORS["border"])
            for w in info["widgets"]:
                w.configure(cursor="hand2")
        # 保险起见，把所有卡片的高亮都复位（避免任何残留）
        if was_drag:
            for t in self.tools:
                other = self.cards.get(t["file"])
                if other and other["lifted"]:
                    other["lifted"] = False
                    other["card"].configure(highlightbackground=ui_theme.COLORS["border"],
                                            highlightcolor=ui_theme.COLORS["border"])

        if was_drag:
            # 松手后让卡片平滑归位到它所属的槽位
            self._layout_cards(animate=True)
            self._save_order()
            if info:
                self._flash(info["card"], "✅ 顺序已保存")
            return

        # 短按：照旧启动
        self.launch_tool(tool)

    def _flash(self, widget, text):
        """在卡片上短暂显示一条提示（拖动结束后反馈）"""
        try:
            tip = tk.Label(widget, text=text, bg=ui_theme.COLORS["primary"], fg="#ffffff",
                           font=ui_theme.ui_font(9, True), padx=10, pady=3)
            tip.place(relx=1.0, rely=0.5, anchor="e", x=-12)
            self.root.after(1200, tip.destroy)
        except Exception:
            pass

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
        # 拖动过程中不要滚动（交给 _autoscroll 处理）
        if self.drag and self.drag.get("active"):
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ==================== 启动 ====================

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