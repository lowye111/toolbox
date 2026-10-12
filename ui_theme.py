# -*- coding: utf-8 -*-
"""工具箱统一 UI 主题

集中管理字体、配色与 ttk 样式：各工具在创建根窗口后调用 ui_theme.apply(root)，
即可获得一致的现代浅色外观。本模块只影响视觉（字体/配色/控件样式），不含业务逻辑。

用法：
    import ui_theme
    ui_theme.apply(root)
    ui_theme.center(root, 900, 700, min_w=800, min_h=600)
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---------------- 配色（浅色现代风） ----------------
COLORS = {
    "primary": "#1a73e8",
    "primary_hover": "#3f8df0",
    "primary_active": "#1558b0",
    "primary_soft": "#e8f0fe",
    "success": "#1e8e3e",
    "success_hover": "#27a04a",
    "success_active": "#15702f",
    "danger": "#d93025",
    "danger_hover": "#e5483d",
    "warning": "#f9ab00",
    "bg": "#f4f6fa",
    "surface": "#ffffff",
    "border": "#d8dee7",
    "text": "#202124",
    "text_secondary": "#5f6368",
    "text_muted": "#98a1ad",
    "hover": "#eaf1fb",
    "stripe": "#f7f9fd",
    "select": "#d2e3fc",
    "dark_bg": "#1e1e1e",
    "dark_fg": "#d4d4d4",
    "log_bg": "#fbfcfe",
}

UI_FAMILIES = ("Microsoft YaHei UI", "微软雅黑", "Microsoft YaHei", "SimHei")
MONO_FAMILIES = ("Consolas", "Cascadia Mono", "Courier New")

_ui_family = "Microsoft YaHei UI"
_mono_family = "Consolas"
BASE_SIZE = 10


def ui_font(size=None, bold=False):
    """界面字体元组（可直接传给 tk/ttk 控件的 font 参数）"""
    if bold:
        return (_ui_family, size or BASE_SIZE, "bold")
    return (_ui_family, size or BASE_SIZE)


def mono_font(size=None, bold=False):
    """等宽字体元组（日志、代码预览）"""
    if bold:
        return (_mono_family, size or BASE_SIZE, "bold")
    return (_mono_family, size or BASE_SIZE)


# ---------------- 内部实现 ----------------

def _pick_family(root, families, fallback):
    try:
        available = set(root.tk.call("font", "families"))
    except Exception:
        return fallback
    for name in families:
        if name in available:
            return name
    return fallback


_NAMED_FONTS = {
    "TkDefaultFont": (0, "normal"),
    "TkTextFont": (0, "normal"),
    "TkMenuFont": (0, "normal"),
    "TkHeadingFont": (0, "bold"),
    "TkIconFont": (0, "normal"),
    "TkTooltipFont": (-1, "normal"),
    "TkCaptionFont": (1, "bold"),
    "TkSmallCaptionFont": (-1, "normal"),
}


def _setup_named_fonts(root):
    """统一经典 tk 控件的默认字体（tk.Button / tk.Label / tk.Text 等）"""
    for name, (delta, weight) in _NAMED_FONTS.items():
        try:
            tkfont.nametofont(name).configure(
                family=_ui_family, size=BASE_SIZE + delta, weight=weight)
        except Exception:
            pass


def _setup_ttk(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    c = COLORS
    base = BASE_SIZE
    ui = _ui_family

    # 全局默认
    style.configure(".", font=(ui, base), background=c["bg"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
                    troughcolor=c["bg"], focuscolor=c["primary"],
                    selectbackground=c["primary"], selectforeground="#ffffff")

    style.configure("TFrame", background=c["bg"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("TSeparator", background=c["border"])

    # ---- 按钮：普通 / 主色 / 成功 / 危险 / 幽灵 ----
    style.configure("TButton", font=(ui, base), padding=(14, 6), relief="flat",
                    background=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
                    focuscolor=c["surface"])
    style.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["border"]), ("active", c["hover"])],
              foreground=[("disabled", c["text_muted"])])

    for name, color, hover, active in (
            ("Primary.TButton", c["primary"], c["primary_hover"], c["primary_active"]),
            ("Accent.TButton", c["primary"], c["primary_hover"], c["primary_active"]),
            ("Success.TButton", c["success"], c["success_hover"], c["success_active"]),
            ("Danger.TButton", c["danger"], c["danger_hover"], "#b3261c")):
        style.configure(name, font=(ui, base), padding=(14, 6), relief="flat",
                        background=color, foreground="#ffffff",
                        bordercolor=color, lightcolor=color, darkcolor=color,
                        focuscolor=color)
        style.map(name,
                  background=[("disabled", "#bcc8d8"), ("pressed", active), ("active", hover)],
                  bordercolor=[("disabled", "#bcc8d8"), ("pressed", active), ("active", hover)],
                  foreground=[("disabled", "#f2f5f9")])

    style.configure("Tool.TButton", font=(ui, base + 1), padding=(18, 12), relief="flat",
                    background=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
                    focuscolor=c["surface"])
    style.map("Tool.TButton",
              background=[("pressed", c["border"]), ("active", c["hover"])])

    style.configure("Ghost.TButton", font=(ui, base), padding=(14, 6), relief="flat",
                    background=c["bg"], foreground=c["text_secondary"],
                    bordercolor=c["bg"], lightcolor=c["bg"], darkcolor=c["bg"],
                    focuscolor=c["bg"])
    style.map("Ghost.TButton",
              background=[("pressed", c["border"]), ("active", c["hover"])],
              bordercolor=[("pressed", c["border"]), ("active", c["hover"])])

    # ---- 单选 / 复选 ----
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=c["bg"], foreground=c["text"], font=(ui, base),
                        focuscolor=c["bg"], indicatorcolor=c["surface"])
        style.map(name,
                  background=[("active", c["bg"])],
                  foreground=[("disabled", c["text_muted"])])
        try:
            style.map(name, indicatorcolor=[("selected", c["primary"])])
        except Exception:
            pass

    # ---- 输入框 / 下拉框 ----
    style.configure("TEntry", padding=(8, 6), relief="flat",
                    fieldbackground=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                    insertcolor=c["text"])
    style.map("TEntry",
              bordercolor=[("focus", c["primary"])],
              lightcolor=[("focus", c["primary"])],
              darkcolor=[("focus", c["primary"])])

    style.configure("TCombobox", padding=(8, 5), relief="flat",
                    fieldbackground=c["surface"], background=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                    arrowcolor=c["text_secondary"])
    style.map("TCombobox",
              fieldbackground=[("readonly", c["surface"]), ("disabled", c["bg"])],
              bordercolor=[("focus", c["primary"])],
              lightcolor=[("focus", c["primary"])],
              darkcolor=[("focus", c["primary"])],
              arrowcolor=[("active", c["primary"])])
    root.option_add("*TCombobox*Listbox.font", (ui, base))
    root.option_add("*TCombobox*Listbox.background", c["surface"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["primary"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ---- 分组框 ----
    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["text_secondary"],
                    font=(ui, base, "bold"))

    # ---- 选项卡 ----
    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], borderwidth=0,
                    tabmargins=(4, 6, 4, 0))
    style.configure("TNotebook.Tab", font=(ui, base + 1), padding=(18, 9),
                    background="#e7ecf4", foreground=c["text_secondary"],
                    bordercolor=c["border"], lightcolor="#e7ecf4", darkcolor="#e7ecf4")
    style.map("TNotebook.Tab",
              background=[("selected", c["surface"]), ("active", c["hover"])],
              foreground=[("selected", c["primary"])],
              lightcolor=[("selected", c["surface"])],
              darkcolor=[("selected", c["surface"])])

    # ---- 进度条 / 滚动条 ----
    style.configure("TProgressbar", thickness=14, troughcolor="#e7ecf4",
                    background=c["primary"], bordercolor="#e7ecf4",
                    lightcolor=c["primary"], darkcolor=c["primary"])

    for orient in ("Vertical", "Horizontal"):
        name = orient + ".TScrollbar"
        style.configure(name, background="#c9d3e0", troughcolor=c["bg"],
                        bordercolor=c["bg"], lightcolor="#c9d3e0", darkcolor="#c9d3e0",
                        arrowcolor=c["text_secondary"], relief="flat")
        style.map(name, background=[("active", "#b3c0d1"), ("pressed", "#9fb0c7")])

    # ---- 表格 ----
    style.configure("Treeview", font=(ui, base), rowheight=int(base * 2.7),
                    background=c["surface"], fieldbackground=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"])
    style.map("Treeview",
              background=[("selected", c["select"])],
              foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", font=(ui, base, "bold"), padding=(8, 6),
                    background="#e7ecf4", foreground=c["text_secondary"],
                    bordercolor=c["border"], lightcolor="#e7ecf4", darkcolor="#e7ecf4",
                    relief="flat")
    style.map("Treeview.Heading", background=[("active", c["hover"])])

    # ---- 文本样式 ----
    style.configure("Title.TLabel", font=(ui, base + 8, "bold"), foreground=c["primary"])
    style.configure("PageTitle.TLabel", font=(ui, base + 4, "bold"), foreground=c["primary"])
    style.configure("Section.TLabel", font=(ui, base, "bold"), foreground=c["text_secondary"])
    style.configure("Description.TLabel", font=(ui, base - 1), foreground=c["text_secondary"])
    style.configure("Tip.TLabel", font=(ui, base - 1), foreground=c["text_muted"])
    style.configure("Info.TLabel", font=(ui, base), foreground=c["text"])
    style.configure("Accent.TLabel", font=(ui, base), foreground=c["primary"])
    style.configure("Status.TLabel", font=(ui, base - 1), background="#e7ecf4",
                    foreground=c["text_secondary"], padding=(10, 5))
    return style


# ---------------- 对外工具函数 ----------------

def apply(root=None):
    """应用统一主题；同一窗口只需调用一次（可重复调用）"""
    global _ui_family, _mono_family
    if root is None:
        root = getattr(tk, "_default_root", None)
    if root is None:
        return None
    _ui_family = _pick_family(root, UI_FAMILIES, _ui_family)
    _mono_family = _pick_family(root, MONO_FAMILIES, _mono_family)
    _setup_named_fonts(root)
    style = _setup_ttk(root)
    try:
        root.configure(bg=COLORS["bg"])
    except Exception:
        pass
    return style


def center(root, width=None, height=None, min_w=None, min_h=None):
    """窗口居中显示（略偏上），可选设置最小尺寸。

    会把尺寸收敛到屏幕可用范围内，避免小屏（如 1366x768）上窗口过大、
    底部控件被挤出屏幕。
    """
    root.update_idletasks()
    if width is None or height is None:
        try:
            size = root.geometry().split("+")[0].split("x")
            cw, ch = int(size[0]), int(size[1])
        except Exception:
            cw, ch = 800, 600
        width = width or cw
        height = height or ch

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    # 预留一点边距，避免窗口正好等于屏幕导致边框/任务栏遮挡
    max_w, max_h = max(320, sw - 40), max(240, sh - 80)
    width = min(int(width), max_w)
    height = min(int(height), max_h)

    x = max(0, (sw - width) // 2)
    y = max(0, min(int((sh - height) * 0.35), sh - height))
    root.geometry(f"{width}x{height}+{x}+{y}")
    if min_w and min_h:
        # 最小尺寸也不能超过屏幕，否则用户无法把窗口缩小到可见范围
        root.minsize(min(int(min_w), max_w), min(int(min_h), max_h))


def style_text(widget, dark=False, wrap=None):
    """统一文本/日志区域外观"""
    c = COLORS
    if dark:
        widget.configure(bg=c["dark_bg"], fg=c["dark_fg"],
                         insertbackground=c["dark_fg"],
                         selectbackground="#264f78", selectforeground="#ffffff",
                         relief="flat", borderwidth=0, padx=10, pady=8)
    else:
        widget.configure(bg=c["log_bg"], fg=c["text"],
                         insertbackground=c["text"],
                         selectbackground=c["select"], selectforeground=c["text"],
                         relief="flat", borderwidth=0, padx=10, pady=8)
    if wrap is not None:
        widget.configure(wrap=wrap)


def make_status_bar(parent, textvariable, **pack_options):
    """创建底部状态栏"""
    bar = ttk.Label(parent, textvariable=textvariable, style="Status.TLabel", anchor="w")
    if not pack_options:
        pack_options = {"fill": tk.X}
    bar.pack(**pack_options)
    return bar