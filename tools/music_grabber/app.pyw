# -*- coding: utf-8 -*-
"""
抓歌打包器 —— 图形界面（工具箱风格）
=====================================
* 使用 toolbox 的统一主题 ui_theme（浅色、字号与其它工具一致）
* 输入改成「表格」形式：一行一首，双击可就地编辑、可增删行
* 每首的进度和结果直接显示在表格里，不用翻日志
"""
import os
import sys
import queue
import threading
import traceback

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
# 让引擎（同目录）和 ui_theme（toolbox 根）都能被导入
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

try:
    import musicgrab
except Exception as e:
    import tkinter.messagebox as mb
    mb.showerror('启动失败', '无法加载引擎 musicgrab.py\n\n%s\n\n%s' % (HERE, e))
    sys.exit(1)

try:
    import ui_theme
    HAS_THEME = True
except Exception:
    HAS_THEME = False
    ui_theme = None

APP_TITLE = '抓歌打包器'
DEFAULT_OUT = os.path.join(HERE, 'output')

COL_INDEX, COL_TITLE, COL_ARTIST, COL_STATUS, COL_RESULT = (
    'idx', 'title', 'artist', 'status', 'result')

STATUS_TEXT = {
    'wait': '等待中',
    'search': '搜索中…',
    'download': '下载中…',
    'convert': '转码中…',
    'package': '打包中…',
    'done': '✓ 完成',
    'error': '✗ 失败',
}
WORKING = ('search', 'download', 'convert', 'package')


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.running = False
        self._build()
        self.root.after(120, self._pump)

    # ---------------- 字体 ----------------
    def _font(self, size=None, bold=False):
        if HAS_THEME:
            return ui_theme.ui_font(size, bold)
        fam = 'Microsoft YaHei UI'
        return (fam, size or 11, 'bold') if bold else (fam, size or 11)

    def _mono(self, size=None):
        if HAS_THEME:
            return ui_theme.mono_font(size)
        return ('Consolas', size or 10)

    # ---------------- 界面 ----------------
    def _build(self):
        r = self.root
        r.title(APP_TITLE)

        if HAS_THEME:
            ui_theme.apply(r)
            ui_theme.center(r, 900, 760, min_w=780, min_h=640)
            C = ui_theme.COLORS
        else:
            r.geometry('900x760')
            C = {'bg': '#f4f6fa', 'surface': '#ffffff', 'border': '#d8dee7',
                 'text': '#202124', 'text_secondary': '#5f6368',
                 'text_muted': '#98a1ad', 'primary': '#1a73e8',
                 'hover': '#eaf1fb', 'success': '#1e8e3e', 'danger': '#d93025'}
        self.C = C

        style = ttk.Style()
        style.configure('Go.TButton', font=self._font(12, True), padding=(24, 11))
        style.configure('Mini.TButton', font=self._font(11), padding=(12, 5))
        # 表格：加大字体与行高（原来的字太小）
        style.configure('Treeview', font=self._font(11), rowheight=36)
        style.configure('Treeview.Heading', font=self._font(11, True), padding=(8, 8))

        # ---------- 头部 ----------
        head = tk.Frame(r, bg=C['surface'])
        head.pack(fill='x')
        hi = tk.Frame(head, bg=C['surface'])
        hi.pack(fill='x', padx=22, pady=(18, 14))
        tk.Label(hi, text='🎵 抓歌打包器', bg=C['surface'], fg=C['primary'],
                 font=self._font(17, True)).pack(anchor='w')
        tk.Label(hi, text='填歌名 → 生成 zip（含封面与歌词）→ 拖进 QQ/微信发到手机',
                 bg=C['surface'], fg=C['text_secondary'],
                 font=self._font(11)).pack(anchor='w', pady=(5, 0))
        tk.Frame(r, bg=C['border'], height=1).pack(fill='x')

        body = tk.Frame(r, bg=C['bg'])
        body.pack(fill='both', expand=True, padx=18, pady=14)

        # ---------- 歌单表格 ----------
        lf = tk.LabelFrame(body, text=' 歌单（双击单元格可编辑） ',
                           bg=C['bg'], fg=C['text_secondary'],
                           font=self._font(11, True), bd=1, relief='solid')
        lf.pack(fill='x', expand=False)

        tw = tk.Frame(lf, bg=C['surface'])
        tw.pack(fill='both', expand=True, padx=10, pady=(8, 6))

        cols = (COL_INDEX, COL_TITLE, COL_ARTIST, COL_STATUS, COL_RESULT)
        self.tree = ttk.Treeview(tw, columns=cols, show='headings',
                                 height=6, selectmode='browse')
        for key, text in ((COL_INDEX, '#'), (COL_TITLE, '歌名'),
                          (COL_ARTIST, '歌手（可留空）'), (COL_STATUS, '状态'),
                          (COL_RESULT, '结果')):
            self.tree.heading(key, text=text)
        self.tree.column(COL_INDEX, width=46, anchor='center', stretch=False)
        self.tree.column(COL_TITLE, width=300, anchor='w')
        self.tree.column(COL_ARTIST, width=190, anchor='w')
        self.tree.column(COL_STATUS, width=112, anchor='center', stretch=False)
        self.tree.column(COL_RESULT, width=180, anchor='w', stretch=False)

        vs = ttk.Scrollbar(tw, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')

        self.tree.tag_configure('done', foreground=C.get('success', '#1e8e3e'))
        self.tree.tag_configure('error', foreground=C.get('danger', '#d93025'))
        self.tree.tag_configure('working', foreground=C['primary'])
        self.tree.bind('<Double-1>', self._on_edit)

        # ---------- 行操作 ----------
        rowbar = tk.Frame(lf, bg=C['bg'])
        rowbar.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(rowbar, text='＋ 添加一行', style='Mini.TButton',
                   command=self._add_row).pack(side='left')
        ttk.Button(rowbar, text='－ 删除选中', style='Mini.TButton',
                   command=self._del_row).pack(side='left', padx=6)
        ttk.Button(rowbar, text='清空', style='Mini.TButton',
                   command=self._clear_rows).pack(side='left')
        tk.Label(rowbar, text='歌名后加「 - 歌手」匹配更准，可避免抓到翻唱或伴奏',
                 bg=C['bg'], fg=C['text_muted'],
                 font=self._font(10)).pack(side='right')

        # ---------- 选项 ----------
        opt = tk.Frame(body, bg=C['bg'])
        opt.pack(fill='x', pady=(12, 4))
        self.fmt = tk.StringVar(value='mp3')
        tk.Label(opt, text='格式', bg=C['bg'], fg=C['text'],
                 font=self._font(11, True)).pack(side='left')
        ttk.Radiobutton(opt, text='MP3 320k（推荐，微信可直接发）',
                        variable=self.fmt, value='mp3').pack(side='left', padx=(10, 0))
        ttk.Radiobutton(opt, text='FLAC 无损',
                        variable=self.fmt, value='flac').pack(side='left', padx=(14, 0))

        outrow = tk.Frame(body, bg=C['bg'])
        outrow.pack(fill='x', pady=(8, 4))
        tk.Label(outrow, text='保存到', bg=C['bg'], fg=C['text'],
                 font=self._font(11, True)).pack(side='left')
        self.outvar = tk.StringVar(value=DEFAULT_OUT)
        ttk.Entry(outrow, textvariable=self.outvar, font=self._font(11)).pack(
            side='left', fill='x', expand=True, padx=(10, 8))
        ttk.Button(outrow, text='浏览…', style='Mini.TButton',
                   command=self._pick_out).pack(side='left')
        ttk.Button(outrow, text='打开', style='Mini.TButton',
                   command=self._open_out).pack(side='left', padx=(6, 0))

        # ---------- 主按钮 ----------
        act = tk.Frame(body, bg=C['bg'])
        act.pack(fill='x', pady=(12, 6))
        self.btn = ttk.Button(act, text='开 始 抓 取', style='Go.TButton',
                              command=self._start)
        self.btn.pack(side='left')
        self.btn_open = ttk.Button(act, text='打开输出文件夹', style='Mini.TButton',
                                   command=self._open_out, state='disabled')
        self.btn_open.pack(side='left', padx=10)
        self.prog = ttk.Progressbar(act, mode='determinate', length=220)
        self.prog.pack(side='right', pady=8)

        # ---------- 日志 ----------
        logf = tk.LabelFrame(body, text=' 日志 ', bg=C['bg'],
                             fg=C['text_secondary'], font=self._font(11, True),
                             bd=1, relief='solid')
        logf.pack(fill='both', expand=True, pady=(8, 0))
        self.log = tk.Text(logf, height=5, font=self._mono(10), wrap='word',
                           state='disabled', relief='flat', bg=C['surface'])
        lsb = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True, padx=10, pady=8)
        if HAS_THEME:
            try:
                ui_theme.style_text(self.log)
            except Exception:
                pass

        self._add_row('Uptown Funk', 'Mark Ronson')
        self._add_row('Rather Be', 'Clean Bandit')

        self._say('提示：')
        self._say('  · 双击表格里的「歌名」「歌手」单元格可直接编辑')
        self._say('  · 用「＋ 添加一行」批量录入，一次可抓多首')
        self._say('  · 单首通常 30~60 秒（取决于平台响应速度），请耐心等待')
        self._say('')

    # ---------------- 表格 ----------------
    def _add_row(self, title='', artist=''):
        iid = self.tree.insert('', 'end', values=(
            len(self.tree.get_children()) + 1, title, artist,
            STATUS_TEXT['wait'], ''))
        self.tree.see(iid)
        return iid

    def _del_row(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('未选中', '请先在表格里点选一行。')
            return
        for iid in sel:
            self.tree.delete(iid)
        self._renumber()

    def _clear_rows(self):
        rows = self.tree.get_children()
        if rows and not messagebox.askyesno('确认', '清空所有行？'):
            return
        for iid in rows:
            self.tree.delete(iid)

    def _renumber(self):
        for n, iid in enumerate(self.tree.get_children(), 1):
            self.tree.set(iid, COL_INDEX, n)

    def _on_edit(self, event):
        if self.running:
            return
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or col not in ('#2', '#3'):
            return
        key = COL_TITLE if col == '#2' else COL_ARTIST
        box = self.tree.bbox(iid, col)
        if not box or not box[2]:
            return
        x, y, w, h = box
        ent = tk.Entry(self.tree, font=self._font(11), relief='solid', bd=1)
        ent.insert(0, self.tree.set(iid, key))
        ent.select_range(0, 'end')
        ent.place(x=x, y=y, width=w, height=h)

        def commit(_e=None):
            self.tree.set(iid, key, ent.get().strip())
            ent.destroy()

        ent.bind('<Return>', commit)
        ent.bind('<FocusOut>', commit)
        ent.bind('<Escape>', lambda _e: ent.destroy())
        ent.focus_set()

    def _rows(self):
        out = []
        for iid in self.tree.get_children():
            t = (self.tree.set(iid, COL_TITLE) or '').strip()
            a = (self.tree.set(iid, COL_ARTIST) or '').strip()
            if t:
                out.append((iid, t, a))
        return out

    # ---------------- 杂项 ----------------
    def _say(self, m):
        self.log.configure(state='normal')
        self.log.insert('end', m + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.outvar.get() or HERE)
        if d:
            self.outvar.set(d)

    def _open_out(self):
        d = self.outvar.get().strip()
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as e:
            messagebox.showerror('打不开', str(e))

    def _set(self, iid, col, text, tag=None):
        try:
            self.tree.set(iid, col, text)
            if tag is not None:
                self.tree.item(iid, tags=(tag,) if tag else ())
        except Exception:
            pass

    # ---------------- 抓取 ----------------
    def _start(self):
        rows = self._rows()
        if not rows:
            messagebox.showwarning('没有内容', '请先在表格里填写至少一首歌名。')
            return
        out_root = self.outvar.get().strip() or DEFAULT_OUT
        try:
            os.makedirs(out_root, exist_ok=True)
        except Exception as e:
            messagebox.showerror('目录不可用',
                                 '无法创建输出目录：\n%s\n\n%s' % (out_root, e))
            return

        lose = (self.fmt.get() == 'flac')
        self.running = True
        self.btn.configure(state='disabled')
        self.prog.configure(maximum=len(rows), value=0)
        for iid, _, _ in rows:
            self._set(iid, COL_STATUS, STATUS_TEXT['wait'], '')
            self._set(iid, COL_RESULT, '')

        def run():
            ok = 0
            for n, (iid, t, a) in enumerate(rows, 1):
                self.q.put(('log', '\n[%d/%d] %s%s' % (
                    n, len(rows), t, (' - ' + a) if a else '')))

                def on_stage(k, d='', _iid=iid):
                    self.q.put(('stage', (_iid, k, d)))

                try:
                    res = musicgrab.grab_one(
                        t, a, out_root, want_lossless=lose,
                        on_log=lambda m: self.q.put(('log', m)),
                        on_stage=on_stage)
                except Exception as e:
                    res = {'ok': False, 'error': str(e)}
                    self.q.put(('log', '    异常：%s' % e))
                    self.q.put(('log', traceback.format_exc()))

                if res.get('ok'):
                    ok += 1
                    self.q.put(('fill', (iid, res.get('title', ''),
                                         res.get('artist', ''))))
                    self.q.put(('result', (iid, '%.1f MB · %s' % (
                        res['zip_mb'], res.get('source', '')))))
                    self.q.put(('log', '    ✓ %s (%.1f MB)' % (
                        os.path.basename(res['zip']), res['zip_mb'])))
                else:
                    self.q.put(('stage', (iid, 'error', '')))
                    self.q.put(('result', (iid, res.get('error', '未知错误'))))
                    self.q.put(('log', '    ✗ %s' % res.get('error', '未知')))
                self.q.put(('prog', n))

            self.q.put(('finish', (ok, len(rows), out_root)))

        threading.Thread(target=run, daemon=True).start()

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'log':
                    self._say(payload)
                elif kind == 'prog':
                    self.prog.configure(value=payload)
                elif kind == 'stage':
                    iid, key, _detail = payload
                    text = STATUS_TEXT.get(key, key)
                    tag = ('working' if key in WORKING else
                           'done' if key == 'done' else
                           'error' if key == 'error' else '')
                    self._set(iid, COL_STATUS, text, tag)
                elif kind == 'fill':
                    iid, title, artist = payload
                    if title:
                        self.tree.set(iid, COL_TITLE, title)
                    if artist:
                        self.tree.set(iid, COL_ARTIST, artist)
                elif kind == 'result':
                    self._set(payload[0], COL_RESULT, payload[1])
                elif kind == 'finish':
                    ok, total, out_root = payload
                    self.running = False
                    self.btn.configure(state='normal')
                    self.btn_open.configure(state='normal')
                    self._say('')
                    self._say('=' * 50)
                    self._say('结束：成功 %d / %d' % (ok, total))
                    if ok:
                        self._say('zip 在：%s' % out_root)
                        self._say('拖进 QQ / 微信发到手机即可。')
                    self._say('=' * 50)
                    if ok:
                        try:
                            os.startfile(out_root)
                        except Exception:
                            pass
        except queue.Empty:
            pass
        self.root.after(120, self._pump)


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
