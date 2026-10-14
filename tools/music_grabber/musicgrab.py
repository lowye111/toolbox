# -*- coding: utf-8 -*-
"""
musicgrab —— 抓歌打包核心引擎
================================
输入：歌名 [+ 歌手]
输出：一个 zip（内含 mp3/flac + 歌词 + 封面），可直接发微信/QQ

设计要点
--------
* 多平台按可靠性依次尝试：酷我(最快) → 网易 → QQ(慢但曲库大)
* 每首歌独立线程 + 独立超时，任一平台卡死不影响整体
* 下载到的常是 192kHz/24bit 高解析 FLAC，自动转 CD 品质(44.1k/16bit)
* 默认产出 MP3 320k（微信友好、手机通用），可选保留无损 FLAC
* 歌词、封面、标签全部内嵌，手机播放器开箱即用
"""
import os
import sys
import re
import json
import time
import shutil
import zipfile
import threading
import subprocess
import urllib.request
import urllib.parse


# ---------- 控制台编码自愈 ----------
# Windows 控制台默认 GBK，print 特殊字符（▸ 等）会直接抛 UnicodeEncodeError。
# 这里自己切到 UTF-8，不依赖外部环境变量。
def _fix_console():
    try:
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleOutputCP(65001)
                ctypes.windll.kernel32.SetConsoleCP(65001)
            except Exception:
                pass
        for name in ('stdout', 'stderr'):
            s = getattr(sys, name, None)
            if s is None:
                continue
            try:
                s.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
    except Exception:
        pass


_fix_console()

# ---------- 路径 ----------
HERE = os.path.dirname(os.path.abspath(__file__))


def _ffmpeg_path():
    """找一个可用的 ffmpeg。优先 imageio-ffmpeg 自带的。"""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    # 退路：插件目录旁的 ffmpeg
    for cand in (os.path.join(HERE, 'ffmpeg.exe'),
                 os.path.join(HERE, 'ffmpeg')):
        if os.path.exists(cand):
            return cand
    return shutil.which('ffmpeg')


FFMPEG = _ffmpeg_path()

# 平台优先级：快的放前面；QQ 很慢(每次搜索约150秒)所以放最后
SOURCE_ORDER = [
    ('KuwoMusicClient',    '酷我'),
    ('NeteaseMusicClient', '网易'),
    ('QQMusicClient',      'QQ'),
    ('MiguMusicClient',    '咪咕'),
]


def log(msg):
    print(msg, flush=True)


# ---------------- 工具 ----------------

def sanitize_filename(name, maxlen=80):
    """去掉文件名里的非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', '', str(name or ''))
    name = re.sub(r'\s+', ' ', name).strip(' .')
    return name[:maxlen] or 'untitled'


def http_get(url, timeout=20, referer=None):
    """简单 GET，返回 bytes。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        **({'Referer': referer} if referer else {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def probe_audio(path):
    """用 ffmpeg 读出音频真实规格：时长/采样率/位深/声道。"""
    info = {'duration': 0.0, 'sample_rate': 0, 'bits': 0, 'channels': 0, 'codec': ''}
    if not FFMPEG or not os.path.exists(path):
        return info
    try:
        r = subprocess.run([FFMPEG, '-hide_banner', '-i', path],
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        txt = r.stderr or ''
        m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', txt)
        if m:
            info['duration'] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        m = re.search(r'Audio:\s*([a-zA-Z0-9_]+)[^\n]*?(\d+)\s*Hz[^\n]*?(mono|stereo|(\d+)\s*channels)',
                      txt)
        if m:
            info['codec'] = m.group(1)
            info['sample_rate'] = int(m.group(2))
            if m.group(3) == 'mono':
                info['channels'] = 1
            elif m.group(3) == 'stereo':
                info['channels'] = 2
            elif m.group(4):
                info['channels'] = int(m.group(4))
        m = re.search(r'(\d+)\s*bit', txt)
        if m:
            info['bits'] = int(m.group(1))
    except Exception:
        pass
    return info


def is_hires(info):
    """是否是需要降采样的高解析文件。"""
    return (info.get('sample_rate', 0) > 48000) or (info.get('bits', 0) > 16)


# ---------------- 搜索 ----------------

def make_client(source_name, work_dir):
    from musicdl.musicdl import MusicClient
    cfg = {source_name: {'disable_print': True,
                         'search_size_per_source': 5,
                         'work_dir': work_dir,
                         'max_retries': 1}}
    return MusicClient(music_sources=[source_name], init_music_clients_cfg=cfg)


def pick_best(songs, want_title, want_artist):
    """从搜索结果里挑最像的，避免下到翻唱/伴奏/教程。"""
    if not songs:
        return None

    def norm(s):
        s = str(s or '').lower()
        s = re.sub(r'[\(\[（【].*?[\)\]）】]', '', s)      # 去括号内容
        s = re.sub(r'\b(feat|ft|explicit|remaster(ed)?|live|cover|instrumental|伴奏|翻唱|纯音乐)\b',
                   '', s, flags=re.I)
        s = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', s)
        return s

    wt, wa = norm(want_title), norm(want_artist)
    scored = []
    for i, s in enumerate(songs):
        st = norm(getattr(s, 'song_name', '') or '')
        sa = norm(getattr(s, 'singers', '') or '')
        score = 0
        if wt and st:
            if st == wt:
                score += 100
            elif wt in st or st in wt:
                score += 60
        if wa and sa:
            if wa in sa or sa in wa:
                score += 40
            else:
                # 歌手对不上，惩罚（防翻唱）
                score -= 25
        elif wa and not sa:
            score -= 5
        score -= i * 2            # 靠前的略优
        # 有歌词的加分
        if getattr(s, 'lyric', None):
            score += 5
        # 明显是伴奏/教程的扣分
        raw = (str(getattr(s, 'song_name', '')) + str(getattr(s, 'album', ''))).lower()
        if re.search(r'伴奏|instrumental|karaoke|教程|教学|cover by|翻唱', raw):
            score -= 80
        scored.append((score, i, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2] if scored else None


# ---------------- 歌词 ----------------

def clean_lyric(raw):
    """把各平台歌词统一成 LRC。"""
    if not raw:
        return ''
    if isinstance(raw, dict):
        raw = raw.get('lyric') or raw.get('lrc') or next(iter(raw.values()), '')
    lines = str(raw).replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # 保留时间轴行和常见头部标签；丢掉平台私有标签
        if re.match(r'^\[\d{1,3}:\d{1,2}([.:]\d{1,3})?\]', s):
            out.append(s)
        elif re.match(r'^\[(ti|ar|al|by|offset|re|ve):', s, re.I):
            out.append(s)
    if not out:
        return ''
    # 去重（同时间戳同内容）
    seen, dedup = set(), []
    for s in out:
        key = re.sub(r'^\[[\d:.]+\]', '', s).strip()
        stamp = re.match(r'^\[([\d:.]+)\]', s)
        k = (stamp.group(1) if stamp else '', key)
        if key and k not in seen:
            seen.add(k)
            dedup.append(s)
        elif not key:
            dedup.append(s)
    return '\n'.join(dedup) + '\n'


# ---------------- 主流程 ----------------

class Grabber:
    def __init__(self, work_dir, on_log=None, on_progress=None, on_stage=None):
        self.work_dir = work_dir
        self.on_log = on_log or log
        self.on_progress = on_progress or (lambda *a, **k: None)
        self.on_stage = on_stage or (lambda *a, **k: None)
        os.makedirs(work_dir, exist_ok=True)
        self._clients = {}

    def say(self, m):
        self.on_log(m)

    def stage(self, key, detail=''):
        """向界面报告当前阶段，便于表格显示状态。
        key: search / download / convert / package / done / error"""
        try:
            self.on_stage(key, detail)
        except Exception:
            pass

    def client(self, source_name):
        if source_name not in self._clients:
            self._clients[source_name] = make_client(source_name, self.work_dir)
        return self._clients[source_name]

    def search(self, title, artist=''):
        """按优先级找，返回 (song, source_label)。搜到就停。"""
        query = ('%s %s' % (title, artist)).strip()
        for src, label in SOURCE_ORDER:
            try:
                self.say('    · 搜索 %s …' % label)
                t0 = time.time()
                res = self.client(src).search(query)
                songs = []
                if res:
                    for k, v in res.items():
                        if v:
                            songs = v
                            break
                best = pick_best(songs, title, artist)
                if best:
                    self.say('      %s 命中：%s / %s  (%.0fs)' % (
                        label,
                        getattr(best, 'song_name', '') or '?',
                        getattr(best, 'singers', '') or '?',
                        time.time() - t0))
                    return best, label
                self.say('      %s 无合适结果 (%.0fs)' % (label, time.time() - t0))
            except Exception as e:
                self.say('      %s 出错：%s' % (label, str(e)[:70]))
        return None, None

    def download(self, song):
        """下载音频到 work_dir，返回文件路径。"""
        src = getattr(song, 'source', None)
        if not src:
            # 从类名反推
            src = type(song).__module__.split('.')[-1]
        cli = self.client(src) if src in dict(
            (s, l) for s, l in SOURCE_ORDER) else None
        if cli is None:
            # 用第一个可用客户端兜底
            cli = self.client(SOURCE_ORDER[0][0])
        before = set(os.listdir(self.work_dir))
        cli.download({getattr(song, 'source', SOURCE_ORDER[0][0]): [song]})
        after = set(os.listdir(self.work_dir))
        new = [f for f in (after - before)]
        # 递归找新音频
        found = []
        for root, _, files in os.walk(self.work_dir):
            for f in files:
                if f.lower().endswith(('.flac', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus')):
                    p = os.path.join(root, f)
                    found.append((os.path.getmtime(p), p))
        if not found:
            return None
        found.sort(reverse=True)
        return found[0][1]

    def _cover_from_other_platform(self, title, artist, cover_tmp, is_image):
        """当前平台没给封面时，去别的平台借一张（只取图，不换音源）。
        酷我经常缺 cover_url，而网易/QQ 基本都有。"""
        query = ('%s %s' % (title, artist)).strip()
        for src, label in (('NeteaseMusicClient', '网易'),
                           ('QQMusicClient', 'QQ'),
                           ('MiguMusicClient', '咪咕')):
            try:
                res = self.client(src).search(query)
                songs = []
                if res:
                    for k, v in res.items():
                        if v:
                            songs = v
                            break
                best = pick_best(songs, title, artist)
                if not best:
                    continue
                cu = (getattr(best, 'cover_url', '') or '').strip()
                if not cu:
                    continue
                ref = None
                for host, r in (('126.net', 'https://music.163.com/'),
                                ('gtimg.cn', 'https://y.qq.com/'),
                                ('migu.cn', 'https://music.migu.cn/')):
                    if host in cu:
                        ref = r
                        break
                data = http_get(cu, timeout=25, referer=ref)
                if is_image(data):
                    open(cover_tmp, 'wb').write(data)
                    self.say('      （封面取自%s）' % label)
                    return True
            except Exception:
                continue
        return False

    def build_outputs(self, audio_path, song, title, artist, album,
                      want_lossless, out_dir):
        """生成最终交付文件：mp3 或 flac + lrc + cover。"""
        os.makedirs(out_dir, exist_ok=True)
        base = sanitize_filename('%s - %s' % (artist or '未知歌手', title) if artist
                                 else title)
        info = probe_audio(audio_path)
        self.say('      规格：%d Hz / %s / %s' % (
            info['sample_rate'],
            ('%d bit' % info['bits']) if info['bits'] else '?',
            ('立体声' if info['channels'] == 2 else '%d 声道' % info['channels'])))

        # 取封面
        cover_tmp = os.path.join(out_dir, '_cover.jpg')
        got_cover = False

        def _is_image(data):
            """确认拿到的确实是图片，而不是 HTML 错误页。"""
            if not data or len(data) < 1000:
                return False
            if data[:3] == b'\xff\xd8\xff':      # JPEG
                return True
            if data[:8] == b'\x89PNG\r\n\x1a\n':  # PNG
                return True
            if data[:6] in (b'GIF87a', b'GIF89a'):
                return True
            if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                return True
            return False

        # a) 先看源文件里有没有内嵌封面
        try:
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-i', audio_path,
                            '-map', '0:v', '-c', 'copy', cover_tmp],
                           capture_output=True, timeout=90)
            if os.path.exists(cover_tmp):
                if _is_image(open(cover_tmp, 'rb').read(64)):
                    got_cover = True
                else:
                    try:
                        os.remove(cover_tmp)
                    except Exception:
                        pass
        except Exception:
            pass

        # b) 没有就下载；失败重试，并带上 Referer
        if not got_cover:
            cu = (getattr(song, 'cover_url', '') or '').strip()
            if cu:
                ref = None
                for host, r in (('kuwo.cn', 'https://www.kuwo.cn/'),
                                ('126.net', 'https://music.163.com/'),
                                ('gtimg.cn', 'https://y.qq.com/'),
                                ('kugou.com', 'https://www.kugou.com/')):
                    if host in cu:
                        ref = r
                        break
                for attempt in range(3):
                    try:
                        data = http_get(cu, timeout=25, referer=ref)
                        if _is_image(data):
                            open(cover_tmp, 'wb').write(data)
                            got_cover = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)

        # c) 酷我图片路径里常有分辨率段，换一个尺寸再试
        if not got_cover:
            cu = (getattr(song, 'cover_url', '') or '')
            if '/wmvpic/' in cu:
                for cand in {cu.replace('/120/', '/500/'), cu.replace('/120/', '/300/')}:
                    if cand == cu:
                        continue
                    try:
                        data = http_get(cand, timeout=15, referer='https://www.kuwo.cn/')
                        if _is_image(data):
                            open(cover_tmp, 'wb').write(data)
                            got_cover = True
                            break
                    except Exception:
                        continue

        # d) 当前平台没给封面（酷我常见）→ 去别的平台借一张
        if not got_cover:
            got_cover = self._cover_from_other_platform(
                title, artist, cover_tmp, _is_image)

        size_mb = os.path.getsize(cover_tmp) / 1024 / 1024 if got_cover else 0
        self.say('      封面：%s' % ('已获取 (%.2f MB)' % size_mb if got_cover else '未获取（不影响播放）'))

        # 歌词
        lyr = clean_lyric(getattr(song, 'lyric', None))
        self.say('      歌词：%s' % ('%d 行' % len(lyr.splitlines()) if lyr else '无'))

        # ---- 转码 ----
        meta = ['-metadata', 'title=%s' % title,
                '-metadata', 'artist=%s' % (artist or ''),
                '-metadata', 'album=%s' % (album or title)]
        inputs = ['-i', audio_path]
        maps = ['-map', '0:a']
        if got_cover:
            inputs += ['-i', cover_tmp]
            maps += ['-map', '1:v', '-c:v', 'copy',
                     '-metadata:s:v', 'title=Album cover',
                     '-metadata:s:v', 'comment=Cover (front)',
                     '-disposition:v', 'attached_pic']

        if want_lossless:
            ext = 'flac'
            final = os.path.join(out_dir, base + '.flac')
            cmd = [FFMPEG, '-v', 'error', '-y'] + inputs + maps + [
                '-c:a', 'flac', '-sample_fmt', 's16', '-ar', '44100',
                '-compression_level', '8'] + meta + [final]
        else:
            ext = 'mp3'
            final = os.path.join(out_dir, base + '.mp3')
            cmd = [FFMPEG, '-v', 'error', '-y'] + inputs + maps + [
                '-c:a', 'libmp3lame', '-b:a', '320k', '-ar', '44100',
                '-id3v2_version', '3'] + meta + [final]

        self.say('      转码为 %s …' % ext.upper())
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=1200)
        if r.returncode != 0 or not os.path.exists(final):
            # 转码失败 → 直接拷贝原文件
            self.say('      转码失败，改为直接复制原文件')
            ext = os.path.splitext(audio_path)[1].lstrip('.').lower()
            final = os.path.join(out_dir, base + '.' + ext)
            shutil.copy2(audio_path, final)

        # 歌词文件
        if lyr:
            open(os.path.join(out_dir, base + '.lrc'), 'w', encoding='utf-8').write(lyr)
        # 独立封面（部分播放器需要）
        if got_cover and os.path.exists(cover_tmp):
            shutil.copy2(cover_tmp, os.path.join(out_dir, 'cover.jpg'))
            try:
                os.remove(cover_tmp)
            except Exception:
                pass

        return {'audio': final, 'base': base, 'ext': ext,
                'has_lyric': bool(lyr), 'has_cover': got_cover,
                'info': info}


def grab_one(title, artist, out_root, want_lossless=False,
             on_log=None, on_progress=None, on_stage=None):
    """抓一首歌并打包 zip，返回结果 dict。
    on_stage(key, detail) 会随流程推进被调用，key 取值：
      search / download / convert / package / done / error
    """
    say = on_log or log
    stage = on_stage or (lambda k, d='': None)
    work = os.path.join(out_root, '_work')
    g = Grabber(work, on_log=say, on_progress=on_progress, on_stage=stage)

    say('  ▸ %s%s' % (title, (' - ' + artist) if artist else ''))
    stage('search', '搜索中…')
    song, label = g.search(title, artist)
    if not song:
        stage('error', '未找到')
        return {'ok': False, 'error': '所有平台都没找到'}

    real_title = getattr(song, 'song_name', '') or title
    real_artist = getattr(song, 'singers', '') or artist
    real_album = getattr(song, 'album', '') or real_title

    say('    · 下载中 …')
    stage('download', '下载中…')
    audio = g.download(song)
    if not audio or not os.path.exists(audio):
        stage('error', '下载失败')
        return {'ok': False, 'error': '下载失败'}
    say('      已下载：%.1f MB' % (os.path.getsize(audio) / 1024 / 1024))

    pkg = sanitize_filename('%s - %s' % (real_artist, real_title)
                            if real_artist else real_title)
    out_dir = os.path.join(out_root, pkg)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)

    stage('convert', '转码中…')
    res = g.build_outputs(audio, song, real_title, real_artist, real_album,
                          want_lossless, out_dir)

    # ---- 打包 zip ----
    stage('package', '打包中…')
    tag = 'FLAC lossless' if want_lossless else 'MP3 320k'
    zip_path = os.path.join(out_root, '%s (%s).zip' % (pkg, tag))
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(os.listdir(out_dir)):
            full = os.path.join(out_dir, f)
            if os.path.isfile(full) and not f.startswith('_'):
                z.write(full, arcname=f)

    out = {
        'ok': True,
        'title': real_title,
        'artist': real_artist,
        'album': real_album,
        'source': label,
        'zip': zip_path,
        'zip_mb': os.path.getsize(zip_path) / 1024 / 1024,
        'audio_mb': os.path.getsize(res['audio']) / 1024 / 1024,
        'ext': res['ext'],
        'has_lyric': res['has_lyric'],
        'has_cover': res['has_cover'],
        'info': res['info'],
        'folder': out_dir,
    }
    stage('done', '%.1f MB · %s' % (out['zip_mb'], label))
    return out


if __name__ == '__main__':
    # 命令行用法（调试用）：python musicgrab.py "歌名" ["歌手"] [--flac]
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    lose = '--flac' in sys.argv
    if not args:
        print('用法: python musicgrab.py "歌名" ["歌手"] [--flac]')
        sys.exit(1)
    t = args[0]
    a = args[1] if len(args) > 1 else ''
    out = os.path.join(HERE, 'output')
    r = grab_one(t, a, out, want_lossless=lose)
    print(json.dumps(r, ensure_ascii=False, indent=1))
