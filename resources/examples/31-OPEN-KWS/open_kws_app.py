# Open-vocabulary keyword spotting, Chinese and English (开放词汇关键词唤醒)
#
# Register your own wake words by voice and detect them continuously:
#   注册新词 / New word -> 录第N段 / Record take N (x3, each recording stops by
#   itself when you finish speaking) -> 开始检测 / Start detect. Up to 8 words
#   per language. A chime plays on every wake-up.
#
# The language button in the header switches between Chinese and English wake
# words. Chinese runs on a 59 initial/final model, English on a 42 ARPAbet
# phoneme model; they are separate models with separate enroll directories and
# separate calibration, so switching reloads the engine. Only one model is
# resident at a time: the old one is released before the new one is loaded.
#
# A trigger must pass two stages: the CTC-forward score over the word's
# threshold, then the weakest syllable of the word (forced alignment), which
# rejects words that differ in a single syllable ("你好小楠" vs "你好小智",
# "Hey Ken" vs "Hey Kendryte").
#
# All signal processing (log-Mel frontend, KPU inference, scoring, VAD,
# verification, enrollment) runs in the native open_kws / open_kws_en modules;
# openkws.py gives them one common interface and this script drives the UI,
# the microphone / speaker and the enroll files.
#
# Display: the IDE virtual screen by default; set DISPLAY_MODE to "AUTO",
# "LCD" or "HDMI" for a physical screen. The layout adapts to the resolution.
# All settings are in the configuration block below the imports.
import sys

# Where this example lives on the SD card. Everything below derives its model,
# asset and enroll paths from it.
#
# It also has to go on sys.path before importing openkws: the IDE runs a script
# by piping it into the REPL, so the code arrives as <stdin> and MicroPython
# has no script directory to add for us. Without this, the sibling module
# openkws.py is not found and the app dies with
#     ImportError: no module named 'openkws'
ROOT = "/sdcard/examples/31-OPEN-KWS/"
if ROOT[:-1] not in sys.path:        # idempotent: the IDE may re-run the script
    sys.path.insert(0, ROOT[:-1])

import array
import gc
import json
import math
import os
import time

import lvgl as lv
import openkws
import uctypes
import media.wave as wave
from machine import TOUCH
from media.display import *
from media.media import *
from media.pyaudio import *

# media.pyaudio does "from mpp import *", which re-exports mpp's own `sys`
# submodule; a plain "import sys" above would therefore be shadowed by it and
# sys.print_exception would not exist. Bind the real module after the star
# imports, under a name they cannot overwrite.
import sys as _sys

# =============================================================================
# 可配置参数 / Configuration
# =============================================================================

# ---- 语言 Language -----------------------------------------------------------
# 启动时的唤醒词语言："zh" 中文 / "en" English；固件里没有的语言会自动跳过。
# 界面文案跟随该语言切换。
LANG_DEFAULT = "zh"

# ---- 屏幕 Screen -------------------------------------------------------------
#   "VIRT"  IDE 虚拟屏（默认），在 CanMV VS Code 插件的预览中用鼠标点击
#   "AUTO"  能打开触摸屏就用开发板 LCD，否则用 IDE 虚拟屏
#   "LCD"   开发板 MIPI LCD 与其触摸屏
#   "HDMI"  HDMI 显示器，在 IDE 预览中点击
DISPLAY_MODE = "VIRT"
DISPLAY_SIZE = None               # 如 (480, 800) 竖屏；None 为自动或默认
TOUCH_ROTATE = None               # LCD 触摸旋转；None 为驱动默认
TOUCH_HOLD_MS = 120               # 触摸读不到点时保持按下的时长（ms）
TOUCH_DEBUG = False
MIN_TOUCH_PX = 40                 # 按钮最小高度（像素）
VIRT_SIZE = (800, 480)
VIRT_FPS = 30
UI_MAX = (1280, 720)              # 大屏上界面最大尺寸，居中显示
LCD_TYPES = ("ST7701", "HX8399", "ILI9806", "NT35516", "NT35532")

# ---- 音频 Audio --------------------------------------------------------------
MIC_VOLUME = 100
AUTO_MIC_GAIN = True              # 录音削波时自动调低麦克风音量并保存
MIC_VOLUME_STEP, MIC_VOLUME_MIN = 10, 40
SPEAKER_VOLUME = 85
WAKE_SOUND = "chime"              # "chime" / 16 kHz 单声道 wav 路径 / None
CHIME_TONES = ((880, 0.09), (1320, 0.15))
CHIME_AMPLITUDE = 9000

# ---- 检测 Detection ----------------------------------------------------------
# 灵敏度档位按语言取自 openkws.PROFILES[lang]["tiers"]，中英各自标定，不共用。
# 没有验证阈值字段的旧注册文件加载时补上该语言的默认值。
WAKE_SHOW_MS = 1500

# ---- 注册与录音 Enrollment ----------------------------------------------------
N_CLIPS = 3                       # 每个词的注册录音段数
REC_END_SILENCE = 5               # 说完后连续静音块数即结束（0.8 s）
REC_ONSET_CHUNKS = 2              # 连续超过语音门限才算开始说话（0.32 s）
REC_MIN_VOICED = 4                # 至少录到这么多块人声才允许结束（0.64 s）
REC_MAX_CHUNKS = 25               # 最长录音（4 s），注册要求裁剪后不超过 2.5 s
REC_WAIT_CHUNKS = 44              # 等待说话的超时（7 s）
REC_PREROLL = 3                   # 说话开始前保留的块数
NOISE_WINDOW = 19                 # 底噪窗口（约 3 s）
SPEECH_RATIO, SPEECH_MIN = 2.5, 0.004
SPEECH_ABS = 0.03
SILENCE_RATIO, SILENCE_MIN = 1.8, 0.003
LEVEL_CLIP_PEAK = 0.98
SAVE_CLIPS = True                 # 保存注册录音（反向相似度检查需要）
CONFUSION_MARGIN = -0.15          # 注册相似度检查余量，越小越严格
VERIFY_CONFUSION_MARGIN = -0.5

# ---- 界面 UI -----------------------------------------------------------------
CONFIRM_MS = 5000                 # 二次确认的有效时间（要够手指重新对准按钮）
CHART_POINTS = 100                # 得分曲线点数（约 16 s）
CHART_MIN, CHART_MAX = -8.0, 2.0  # 纵轴范围（得分 − 阈值）
LEVEL_DB_RANGE = 70.0
FONT_FILES = ("/sdcard/res/font/SourceHanSansSC-Normal-Min.ttf",)
C_BG, C_CARD, C_ROW = 0x0F1318, 0x1A2029, 0x232B36
C_LINE, C_TEXT, C_MUTED = 0x2C3644, 0xE6EDF3, 0x8B98A5
C_ACCENT, C_DANGER, C_OK, C_WARN = 0x2F81F7, 0xD9534F, 0x3FB950, 0xFFD60A
KW_COLORS = (0x4FC3F7, 0xFFB74D, 0x81C784, 0xF06292, 0xBA68C8, 0xFFF176, 0x4DB6AC, 0xE57373)

# ---- 路径 Paths --------------------------------------------------------------
# ROOT 在文件最上面定义（import openkws 之前就要用它设置 sys.path）
SETTINGS_JSON = ROOT + "settings.json"   # 自动调整后的麦克风音量与上次语言

# =============================================================================
# 内部常量
# =============================================================================
SAMPLE_RATE = openkws.SAMPLE_RATE
CHUNK = openkws.CHUNK             # 2560 采样 = 160 ms
MAX_KEYWORDS = openkws.MAX_KEYWORDS

IDLE, READY, RECORDING, COMPUTING, DETECTING = range(5)

# 界面文案。两种语言的键完全相同，切换语言时整块替换。
TEXT = {
    "zh": {
        "title": "开放词汇唤醒  Open-KWS",
        "chart": "唤醒得分（得分 − 阈值，红线为触发线）",
        "level": "音量",
        "kw_count": "已注册 %d / %d 个唤醒词",
        "no_kw": "还没有唤醒词\n点击「注册新词」开始",
        "new": "注册新词", "cancel": "取消注册",
        "rec_n": "录第%d段", "recording": "录音中…", "rec": "录音",
        "detect": "开始检测", "stop": "停止检测",
        "clear": "清空全部", "clear_q": "确认清空?",
        "del": "删除", "del_q": "确认删除",
        "verify": "  含验证", "th": "%s   阈值 %.2f%s",
        "wake": "唤醒！%s",
        "loaded": "已加载 %d 个唤醒词%s，点击「开始检测」",
        "bad_files": "（%d 个文件无效）",
        "start_hint": "点击「注册新词」开始注册",
        "lang_switched": "已切换到中文唤醒词",
        "enroll_start": "注册 %s：点击「录第1段」，然后说出唤醒词（4 字以上）",
        "enroll_full": "最多注册 %d 个唤醒词，请先删除",
        "say_now": "请说出唤醒词…（说完会自动结束）",
        "recording_now": "正在录音…",
        "take_ok": "第%d段 OK（%.2fs, SNR %.1fdB）。请录第%d段",
        "take_ok_noisy": "第%d段已收下（%.2fs, SNR %.1fdB，环境偏吵，唤醒率可能偏低）。请录第%d段",
        "take_bad": "第%d段不合格：%s（%.2fs，峰值 %.2f，削波 %.1f%%，SNR %.1fdB），请重录",
        "take_loud": "第%d段音量过大，已自动将麦克风音量调到 %d，请重录%s",
        "take_loud_note": "；已注册的词是在原音量下录的，唤醒变差可重新注册",
        "take_noisy": "第%d段几乎听不到人声（只比底噪高 %.1f dB，至少要 %.0f dB），请靠近麦克风、说话大声一些",
        "no_speech_take": "第%d段：没有检测到说话声，请靠近麦克风、说话大声一些",
        "computing": "正在计算唤醒词模型…",
        "computing_n": "正在计算唤醒词模型… %d/%d",
        "sim_check": "正在检查与已注册唤醒词的相似度…",
        "sim_check_n": "正在检查与已注册唤醒词的相似度… %d/%d",
        "enrolled": "%s 注册成功！%s   阈值 %.3f，共 %d 个唤醒词",
        "fail": "注册失败：%s",
        "too_similar": "注册失败：与已注册的 %s 太相似（%.2f），请换一个词",
        "reverse_similar": "注册失败：说 %s 时也会唤醒新词（%.2f），请换一个词",
        "cancelled": "已取消注册",
        "detecting": "检测中（%d 个唤醒词）… 请说出任一唤醒词",
        "det_stopped": "检测已停止",
        "woke": "唤醒 %s：%s  score=%.3f（阈值 %.3f%s）",
        "woke_weak": "，最弱音节 %.2f",
        "deleted": "已删除 %s（%d 个文件），剩余 %d 个唤醒词",
        "del_hint": "再次点击「确认删除」删除 %s",
        "clear_hint": "再次点击「确认清空?」删除全部唤醒词和录音",
        "cleared": "已清空全部唤醒词（删除 %d 个文件）",
        "del_cancel": "已取消删除", "clear_cancel": "已取消清空",
        "sens": "灵敏度：%s",
        "timing": "每块 %.1f ms（前端 %.1f / KPU %.1f / 打分 %.1f）· 验证拦截 %d",
        "det_err": "检测出错，已停止：%s",
        "enroll_err": "注册出错，已取消：%s",
        "reason": {
            "too short": "录音太短，请说完整的唤醒词",
            "too long": "录音太长，请只说唤醒词",
            "too quiet": "音量过低，请靠近麦克风",
            "clipped": "音量过大（削波），请离远一点或小声一些",
            "too noisy": "几乎听不到人声，请靠近麦克风",
            "no speech": "没有检测到说话声，请靠近麦克风、说话大声一些",
            "model error": "模型推理出错，请重试",
        },
        "err": {
            "need at least 2 recordings": "至少需要 2 段录音",
            "no unit sequence decoded": "未能识别出声韵母，请重录",
            "no phoneme sequence decoded": "未能识别出音素，请重录",
            "keyword too short": "唤醒词太短，请换一个 4 字以上的词",
            "wake word too short": "唤醒词太短，请换一个更长的词",
            "recordings inconsistent": "几段录音差异太大，请保持一致重录",
            "model error": "模型推理出错，请重试",
        },
    },
    "en": {
        "title": "Open-KWS  English",
        "chart": "Wake score (score - threshold; red line = trigger)",
        "level": "Level",
        "kw_count": "Keywords  %d / %d",
        "no_kw": "No wake words yet\nTap \"New word\" to start",
        "new": "New word", "cancel": "Cancel",
        "rec_n": "Record take %d", "recording": "Recording...", "rec": "Record",
        "detect": "Start detect", "stop": "Stop detect",
        "clear": "Clear all", "clear_q": "Confirm clear?",
        "del": "Delete", "del_q": "Confirm",
        "verify": "  verify", "th": "%s   th %.2f%s",
        "wake": "WAKE  %s",
        "loaded": "Loaded %d wake word(s)%s. Tap \"Start detect\"",
        "bad_files": " (%d file(s) invalid)",
        "start_hint": "Tap \"New word\" to register an English wake word",
        "lang_switched": "Switched to English wake words",
        "enroll_start": "Enrolling %s: tap \"Record take 1\", then say the wake word "
                        "(3+ syllables, e.g. \"Hey Kendryte\")",
        "enroll_full": "At most %d wake words; delete one first",
        "say_now": "Say the wake word... (recording stops by itself)",
        "recording_now": "Recording...",
        "take_ok": "Take %d OK (%.2fs, SNR %.1fdB). Now record take %d",
        "take_ok_noisy": "Take %d kept (%.2fs, SNR %.1fdB -- noisy, wake-up may "
                         "be less reliable). Now record take %d",
        "take_bad": "Take %d rejected: %s (%.2fs, peak %.2f, clip %.1f%%, SNR %.1fdB)",
        "take_loud": "Take %d was too loud; mic volume lowered to %d, record it again%s",
        "take_loud_note": "; words enrolled at the old gain may wake less well",
        "take_noisy": "Take %d has almost no speech in it (only %.1f dB above the noise "
                      "floor, %.0f dB needed). Move closer and speak up",
        "no_speech_take": "Take %d: no speech detected, speak louder or move closer",
        "computing": "Building the wake word model...",
        "computing_n": "Building the wake word model... %d/%d",
        "sim_check": "Checking similarity with the existing wake words...",
        "sim_check_n": "Checking similarity with the existing wake words... %d/%d",
        "enrolled": "%s enrolled: %s   (threshold %.3f, %d word(s) total)",
        "fail": "Enrollment failed: %s",
        "too_similar": "Enrollment failed: too similar to %s (%.2f), pick another word",
        "reverse_similar": "Enrollment failed: saying %s would also wake the new word "
                           "(%.2f), pick another word",
        "cancelled": "Enrollment cancelled",
        "detecting": "Listening (%d wake word(s))... say any of them",
        "det_stopped": "Detection stopped",
        "woke": "Woke on %s: %s  score %.3f (th %.3f%s)",
        "woke_weak": ", weakest syllable %.2f",
        "deleted": "Deleted %s (%d file(s)); %d wake word(s) left",
        "del_hint": "Tap \"Confirm\" again to delete %s",
        "clear_hint": "Tap \"Confirm clear?\" again to delete every wake word",
        "cleared": "Cleared all wake words (%d file(s) removed)",
        "del_cancel": "Delete cancelled", "clear_cancel": "Clear cancelled",
        "sens": "Sensitivity: %s",
        "timing": "%.1f ms per chunk (frontend %.1f / KPU %.1f / decode %.1f) - %d vetoed",
        "det_err": "Detection error, stopped: %s",
        "enroll_err": "Enrollment error, cancelled: %s",
        "reason": {
            "too short": "recording too short, say the whole wake word",
            "too long": "recording too long, say only the wake word",
            "too quiet": "too quiet, move closer to the microphone",
            "clipped": "too loud (clipping), move back or speak more softly",
            "too noisy": "almost no speech, move closer to the mic",
            "no speech": "no speech detected, speak louder or move closer",
            "model error": "model inference failed, please try again",
        },
        "err": {
            "need at least 2 recordings": "at least 2 takes are needed",
            "no unit sequence decoded": "could not decode any units, record again",
            "no phoneme sequence decoded": "could not decode any phonemes, record again",
            "keyword too short": "wake word too short, pick a longer one",
            "wake word too short": "wake word too short: 3+ syllables and 6+ phonemes, "
                                   "e.g. \"Hey Kendryte\"",
            "recordings inconsistent": "the takes differ too much, say it the same way",
            "model error": "model inference failed, please try again",
        },
    },
}

LANG_LABEL = {"zh": "中文", "en": "English"}


def save_wav(path, pcm):
    wf = wave.open(path, "wb")
    wf.set_channels(1)
    wf.set_sampwidth(2)
    wf.set_framerate(SAMPLE_RATE)
    wf.write_frames(pcm)
    wf.close()


def read_wav(path):
    wf = wave.open(path, "rb")
    pcm = wf.read_frames(wf.get_frames())
    wf.close()
    return pcm


def would_wake(margin, score, cut):
    """Both stages of a keyword would pass on some audio (with headroom)."""
    if margin <= CONFUSION_MARGIN:
        return False
    return cut is None or (score is not None and score > cut + VERIFY_CONFUSION_MARGIN)


def kw_index(name):
    """'kw_3.json' -> 3, anything else -> None."""
    if not (name.startswith("kw_") and name.endswith(".json")):
        return None
    num = name[3:-5]
    return int(num) if num.isdigit() else None


def is_enroll_file(name):
    # keyword files and clips, plus the clip_N.wav names of the first version
    return kw_index(name) is not None or (name.endswith(".wav") and
                                          (name.startswith("kw_") or name.startswith("clip_")))


def kw_files(kw_id, names):
    """Files of one keyword: kw_n.json and kw_n_clip_k.wav."""
    return [n for n in names if n == kw_id + ".json" or
            (n.startswith(kw_id + "_clip_") and n.endswith(".wav"))]


# ---------------------------------------------------------------- devices

def display_modes():
    """{type name: [(w, h), ...]} of the panels compiled into the firmware."""
    modes = {}
    try:
        for m in Display.list_modes():
            name = m["type"].split(".")[-1]
            size = (m["width"], m["height"])
            if size not in modes.setdefault(name, []):
                modes[name].append(size)
    except Exception as e:
        print("list_modes failed:", e)
    return modes


def touch_range(touch):
    """Native (w, h) the touch driver reports, parsed from repr(); None if absent."""
    text = repr(touch)
    i = text.find("range=")
    if i < 0:
        return None
    try:
        w, h = text[i + 6:].split(",")[0].split(")")[0].split("x")
        w, h = int(w), int(h)
        return (w, h) if w > 0 and h > 0 else None
    except ValueError:
        return None


def pick_size(sizes, want, exact=False):
    """Supported size equal to want (exact) or matching it in either
    orientation, landscape first."""
    if not want:
        return None
    if exact:
        return tuple(want) if tuple(want) in sizes else None
    hits = [z for z in sizes if z == want or z == (want[1], want[0])]
    hits.sort(key=lambda z: z[0] < z[1])
    return hits[0] if hits else None


def detect_display():
    """-> (mode, panel type name or None, (w, h) or None, probed TOUCH or None)."""
    modes = display_modes()
    print("display modes:", modes)
    lcds = [t for t in LCD_TYPES if t in modes] + \
           [t for t in modes if t not in LCD_TYPES and t not in ("VIRT", "LT9611", "DEBUGGER")]
    mode = DISPLAY_MODE
    touch = None
    if mode in ("AUTO", "LCD") and lcds:
        try:
            touch = TOUCH(0)
        except Exception as e:
            print("no touch panel:", e)
        if touch is None and mode == "AUTO":
            mode = "VIRT"
        else:
            mode = "LCD"
    elif mode in ("AUTO", "LCD"):
        mode = "VIRT"
    if mode == "LCD":
        want = DISPLAY_SIZE or (touch_range(touch) if touch else None)
        panel, size = lcds[0], None
        for t in lcds:                       # the panel type that has this resolution
            hit = pick_size(modes[t], want, exact=bool(DISPLAY_SIZE))
            if hit:
                panel, size = t, hit
                break
        if DISPLAY_SIZE and size is None:
            print("DISPLAY_SIZE %s not supported by %s, using default" % (DISPLAY_SIZE, panel))
        return mode, panel, size, touch
    if mode == "HDMI":
        size = pick_size(modes.get("LT9611", []), DISPLAY_SIZE, exact=True)
        if DISPLAY_SIZE and size is None:
            print("DISPLAY_SIZE %s not supported by HDMI, using default" % (DISPLAY_SIZE,))
        return mode, "LT9611", size, None
    return "VIRT", "VIRT", DISPLAY_SIZE or VIRT_SIZE, None


class Screen:
    """Display + LVGL double buffer; the UI is centred on large screens."""

    def __init__(self):
        self.mode, panel, size, self.touch = detect_display()
        dtype = getattr(Display, panel)
        if self.mode == "VIRT":
            Display.init(dtype, width=ALIGN_UP(size[0], 16), height=size[1], fps=VIRT_FPS,
                         to_ide=True)
        elif size:
            Display.init(dtype, width=size[0], height=size[1], to_ide=True)
        else:
            Display.init(dtype, to_ide=True)
        self.sw, self.sh = Display.width(), Display.height()
        print("display: %s (%s) %dx%d" % (self.mode, panel, self.sw, self.sh))
        cap_w, cap_h = UI_MAX if self.sw >= self.sh else (UI_MAX[1], UI_MAX[0])
        self.w = min(self.sw, cap_w) // 16 * 16
        self.h = min(self.sh, cap_h)
        self.x = (self.sw - self.w) // 2
        self.y = (self.sh - self.h) // 2
        lv.init()
        self.imgs = [image.Image(self.w, self.h, image.BGRA8888),
                     image.Image(self.w, self.h, image.BGRA8888)]
        disp = lv.disp_create(self.w, self.h)
        disp.set_color_format(lv.COLOR_FORMAT.ARGB8888)
        disp.set_draw_buffers(self.imgs[0].bytearray(), self.imgs[1].bytearray(),
                              self.imgs[0].size(), lv.DISP_RENDER_MODE.FULL)
        disp.set_flush_cb(self.flush)
        print("screen %dx%d, UI %dx%d at (%d, %d)" % (self.sw, self.sh, self.w, self.h,
                                                     self.x, self.y))

    def flush(self, disp_drv, area, color):
        if disp_drv.flush_is_last():
            ptr = uctypes.addressof(color.__dereference__())
            img = self.imgs[0] if self.imgs[0].virtaddr() == ptr else self.imgs[1]
            Display.show_image(img, x=self.x, y=self.y, layer=Display.LAYER_OSD0)
        disp_drv.flush_ready()


class Touch:
    """LCD touch panel, or the IDE preview for the virtual screen / HDMI."""

    def open_lcd_touch(self, screen):
        """The panel's own touch controller, or None when it cannot be opened.
        A board can have a supported LCD but no (or a different) touch chip, so
        this must not be fatal: the display itself still works."""
        t = screen.touch
        try:
            if TOUCH_ROTATE is not None:
                if t is not None:
                    t.deinit()
                t = TOUCH(0, rotate=TOUCH_ROTATE)
            elif t is None:
                t = TOUCH(0)
        except Exception as e:
            print("LCD touch panel cannot be opened:", e)
            return None
        rng = touch_range(t)
        # same orientation, different scale: map touch units to pixels
        if TOUCH_ROTATE is None and rng and (rng[0] >= rng[1]) == (screen.sw >= screen.sh):
            self.sx, self.sy = screen.sw / rng[0], screen.sh / rng[1]
        return t

    def __init__(self, screen):
        self.screen = screen
        self.sx = self.sy = 1.0
        self.touch = self.open_lcd_touch(screen) if screen.mode == "LCD" else None
        if self.touch is None:
            # No panel touch (DISPLAY_MODE="VIRT"/"HDMI", or an LCD whose touch
            # controller cannot be opened): take input from the IDE preview, so
            # the UI stays usable on the LCD by clicking in the preview window.
            if screen.mode == "LCD":
                print("LCD touch unavailable, using the IDE preview for input")
            self.touch = TOUCH(TOUCH.DEV_IDE, range_x=screen.sw, range_y=screen.sh)
        self.pressed = False
        self.contact = False                  # a DOWN/MOVE of the current contact was read
        self.release_next = False
        self.last_seen = 0
        self.last_xy = (0, 0)
        print("touch: %s -> scale %.3f x %.3f" % (repr(self.touch), self.sx, self.sy))
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)
        self.indev.set_read_cb(self.callback)

    def callback(self, driver, data):
        """Touch -> LVGL pointer state.

        LVGL samples this every ~10-20 ms; a touch controller may report only
        changes, or a tap may start and end between two samples. So:
          * an empty read keeps the press for TOUCH_HOLD_MS (no early release),
          * an UP whose press LVGL never saw (no DOWN/MOVE read for this contact)
            is replayed as press, then release, so short taps still become clicks."""
        if self.release_next:                 # second half of a replayed tap; leave
            self.release_next = False         # new touch events for the next sample
            self.pressed = False
            data.point.x, data.point.y = self.last_xy
            data.state = lv.INDEV_STATE.RELEASED
            return
        now = time.ticks_ms()
        try:
            points = self.touch.read(1)
        except Exception:
            points = None
        if points:
            p = points[0]
            s = self.screen
            x = min(max(int(p.x * self.sx) - s.x, 0), s.w - 1)
            y = min(max(int(p.y * self.sy) - s.y, 0), s.h - 1)
            self.last_xy = (x, y)
            if TOUCH_DEBUG:
                print("touch raw (%d, %d) event %d -> ui (%d, %d)" % (p.x, p.y, p.event, x, y))
            if p.event in (TOUCH.EVENT_DOWN, TOUCH.EVENT_MOVE):
                self.pressed = True
                self.contact = True
                self.last_seen = now
            elif self.contact:                # end of a contact LVGL has seen
                self.contact = False
                self.pressed = False
            else:                             # tap shorter than one sample
                self.pressed = True
                self.release_next = True
        elif self.pressed and time.ticks_diff(now, self.last_seen) > TOUCH_HOLD_MS:
            self.pressed = False
        data.point.x, data.point.y = self.last_xy
        data.state = lv.INDEV_STATE.PRESSED if self.pressed else lv.INDEV_STATE.RELEASED

    def deinit(self):
        try:
            self.touch.deinit()
        except Exception:
            pass


def make_chime():
    """Two short rising tones, zero-padded to whole CHUNK frames."""
    buf = array.array("h")
    for freq, dur in CHIME_TONES:
        n = int(SAMPLE_RATE * dur)
        k = 2.0 * math.pi * freq / SAMPLE_RATE
        for i in range(n):
            env = min(1.0, i / 160.0, (n - i) / 480.0)
            buf.append(int(CHIME_AMPLITUDE * env * math.sin(k * i)))
    return bytes(buf)


class Speaker:
    """Wake-up prompt on the audio output, written one CHUNK frame at a time."""

    def __init__(self, p):
        self.frames = []
        self.stream = None
        if WAKE_SOUND is None:
            return
        try:
            pcm = make_chime() if WAKE_SOUND == "chime" else read_wav(WAKE_SOUND)
            size = CHUNK * 2
            pcm = pcm + bytes((-len(pcm)) % size)
            self.frames = [pcm[i:i + size] for i in range(0, len(pcm), size)]
            self.stream = p.open(format=paInt16, channels=1, rate=SAMPLE_RATE, output=True,
                                 frames_per_buffer=CHUNK)
            self.stream.volume(vol=SPEAKER_VOLUME)
        except Exception as e:
            print("wake sound disabled:", e)
            self.stream = None

    def play(self):
        if self.stream is None:
            return
        try:
            for f in self.frames:
                self.stream.write(f)
        except Exception as e:
            print("wake sound failed:", e)

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                print("speaker close failed:", e)
            self.stream = None


# ---------------------------------------------------------------- application

class OpenKwsApp:
    def __init__(self, screen, stream, speaker, lang):
        self.screen = screen
        self.stream = stream
        self.speaker = speaker
        self.langs = openkws.available()
        self.lang = lang
        self.eng = None
        self.state = IDLE
        self.recs = []              # registered enroll dicts, same order as the engine
        self.clips = []             # accepted clips of the running enrollment (bytes)
        self.rec_chunks = []
        self.rec_n = 0              # chunks read since the recording started
        self.rec_speech = False
        self.rec_silence = 0
        self.rec_onset = 0          # consecutive chunks above the speech gate
        self.rec_voiced = 0         # non-silent chunks since speech started
        self.noise = None           # noise floor (rms), frozen while recording
        self.noise_hist = []        # recent chunk levels while not recording
        self.finalizer = None       # generator finishing an enrollment step by step
        self.pending = None         # action set by UI callbacks, run in the main loop
        self.clear_armed = 0        # deadline of the clear-all confirmation
        self.del_armed = None       # (kw_id, deadline) of a delete confirmation
        self.wake_until = 0
        self.n_push = 0
        self.sens_idx = 0
        self._text = {}
        self._layout(screen)
        settings = self.load_settings()
        self.mic_volume = settings.get("mic_volume", MIC_VOLUME)
        self.stream.volume(vol=self.mic_volume)
        self.open_language(lang, first=True)

    # ------------------------------------------------------------ language
    def t(self, key):
        """A piece of UI text in the current language."""
        return TEXT[self.lang][key]

    def open_language(self, lang, first=False):
        """Load one language's engine and rebuild the UI around it. The old
        engine is closed first so only a single kmodel is ever resident."""
        if self.eng is not None:
            self.eng.close()
            self.eng = None
            gc.collect()            # let the old model's buffers go before the new load
        self.lang = lang
        self.eng = openkws.Engine(lang, ROOT)
        self.sens_idx = self.eng.profile["default_tier"]
        self.recs = []
        self.state = IDLE
        self.clips = []
        self.rec_chunks = []
        self.finalizer = None
        self.del_armed = None
        self.clear_armed = 0
        self._text = {}
        self.build_ui()
        self.apply_sensitivity()
        self.load_keywords()
        if not first:
            self.set_status(self.t("lang_switched"))
        self.rebuild_list()
        self.refresh()

    def switch_language(self, lang):
        if lang == self.lang or lang not in self.langs:
            return
        self.abort_enroll()
        self.hide_wake()
        self.save_settings()
        self.open_language(lang)

    # ------------------------------------------------------------ layout helpers
    def _layout(self, screen):
        self.w, self.h = screen.w, screen.h
        self.landscape = self.w >= self.h
        base = (800, 480) if self.landscape else (480, 800)
        self.s = min(self.w / base[0], self.h / base[1])
        self.fonts = {}

    def px(self, v):
        return max(1, int(v * self.s + 0.5))

    def font(self, size):
        """A freetype font at this size, or None to keep the LVGL built-in one.
        Chinese needs the CJK face; English falls back readably without it."""
        size = max(11, self.px(size))
        if size not in self.fonts:
            f = None
            for path in FONT_FILES:
                try:
                    f = lv.freetype_font_create(path, size, 0)
                    break
                except Exception as e:
                    print("font load failed:", path, e)
            self.fonts[size] = f
        return self.fonts[size]

    def box(self, parent, flow=None, bg=None, radius=0, pad=0, gap=0):
        o = lv.obj(parent)
        o.set_style_border_width(0, 0)
        o.set_style_radius(self.px(radius), 0)
        o.set_style_pad_all(self.px(pad), 0)
        o.set_style_pad_gap(self.px(gap), 0)
        if bg is None:
            o.set_style_bg_opa(lv.OPA.TRANSP, 0)
        else:
            o.set_style_bg_color(lv.color_hex(bg), 0)
            o.set_style_bg_opa(lv.OPA.COVER, 0)
        if flow is not None:
            o.set_flex_flow(flow)
        o.clear_flag(lv.obj.FLAG.SCROLLABLE)
        return o

    def label(self, parent, text="", size=17, color=C_TEXT):
        l = lv.label(parent)
        l.set_text(text)
        f = self.font(size)
        if f:
            l.set_style_text_font(f, 0)
        l.set_style_text_color(lv.color_hex(color), 0)
        return l

    def button(self, parent, text, action, color=C_ACCENT):
        b = lv.btn(parent)
        b.set_height(max(MIN_TOUCH_PX, self.px(48)))
        b.set_flex_grow(1)
        b.set_style_min_width(self.px(90), 0)
        b.set_style_radius(self.px(10), 0)
        b.set_style_shadow_width(0, 0)
        b.set_style_bg_color(lv.color_hex(color), 0)
        b.set_style_bg_color(lv.color_hex(0x3A4250), lv.STATE.DISABLED)
        b.add_event(lambda e: self.request(action), lv.EVENT.CLICKED, None)
        l = self.label(b, text, 17, 0xFFFFFF)
        l.center()
        return b, l

    def set_text(self, label, text):
        """Only touch LVGL (and trigger a redraw) when the text changes."""
        key = id(label)
        if self._text.get(key) != text:
            self._text[key] = text
            label.set_text(text)

    # ------------------------------------------------------------ UI
    def build_ui(self):
        """(Re)build the whole screen. Called again on a language switch, which
        is the simplest way to retranslate every static label."""
        scr = lv.scr_act()
        scr.clean()
        scr.set_style_bg_color(lv.color_hex(C_BG), 0)
        scr.set_style_pad_all(self.px(10), 0)
        scr.set_style_pad_gap(self.px(8), 0)
        scr.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        scr.clear_flag(lv.obj.FLAG.SCROLLABLE)

        # header: title + language + sensitivity, status line below
        head = self.box(scr, lv.FLEX_FLOW.ROW_WRAP, gap=10)
        head.set_size(lv.pct(100), lv.SIZE_CONTENT)
        head.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER,
                            lv.FLEX_ALIGN.CENTER)
        title = self.label(head, self.t("title"), 22)
        title.set_flex_grow(1)
        self.build_language(head)
        self.build_sensitivity(head)

        self.status = self.label(scr, "", 16, 0x9FD3FF)
        self.status.set_width(lv.pct(100))
        self.status.set_long_mode(lv.label.LONG.DOT)

        # body: score card + keyword card, side by side or stacked
        body = self.box(scr, lv.FLEX_FLOW.ROW if self.landscape else lv.FLEX_FLOW.COLUMN, gap=8)
        body.set_width(lv.pct(100))
        body.set_flex_grow(1)

        left = self.box(body, lv.FLEX_FLOW.COLUMN, bg=C_CARD, radius=12, pad=10, gap=6)
        right = self.box(body, lv.FLEX_FLOW.COLUMN, bg=C_CARD, radius=12, pad=10, gap=6)
        if self.landscape:
            left.set_height(lv.pct(100))
            right.set_height(lv.pct(100))
            left.set_flex_grow(3)
            right.set_flex_grow(2)
        else:
            left.set_width(lv.pct(100))
            right.set_width(lv.pct(100))
            left.set_flex_grow(1)
            right.set_flex_grow(1)

        self.label(left, self.t("chart"), 14, C_MUTED)
        self.chart = lv.chart(left)
        self.chart.set_width(lv.pct(100))
        self.chart.set_flex_grow(1)
        self.chart.set_type(lv.chart.TYPE.LINE)
        self.chart.set_point_count(CHART_POINTS)
        self.chart.set_update_mode(lv.chart.UPDATE_MODE.SHIFT)
        self.chart.set_range(lv.chart.AXIS.PRIMARY_Y, int(CHART_MIN * 100), int(CHART_MAX * 100))
        self.chart.set_div_line_count(5, 0)
        self.chart.set_style_bg_color(lv.color_hex(C_BG), 0)
        self.chart.set_style_border_width(0, 0)
        self.chart.set_style_radius(self.px(8), 0)
        self.chart.set_style_line_color(lv.color_hex(C_LINE), lv.PART.MAIN)
        self.chart.set_style_line_width(self.px(2), lv.PART.ITEMS)
        self.chart.set_style_size(0, 0, lv.PART.INDICATOR)
        self.ser_score = self.chart.add_series(lv.color_hex(0x39C5E8), lv.chart.AXIS.PRIMARY_Y)
        self.ser_th = self.chart.add_series(lv.color_hex(C_DANGER), lv.chart.AXIS.PRIMARY_Y)
        self.chart.set_all_value(self.ser_score, int(CHART_MIN * 100))

        meter = self.box(left, lv.FLEX_FLOW.ROW, gap=8)
        meter.set_size(lv.pct(100), lv.SIZE_CONTENT)
        meter.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.label(meter, self.t("level"), 14, C_MUTED)
        self.level = lv.bar(meter)
        self.level.set_height(self.px(10))
        self.level.set_flex_grow(1)
        self.level.set_range(0, 100)
        self.level.set_style_bg_color(lv.color_hex(C_ROW), lv.PART.MAIN)
        self.level.set_style_bg_color(lv.color_hex(C_OK), lv.PART.INDICATOR)
        self.vad = self.box(meter, bg=C_ROW, radius=6)
        self.vad.set_size(self.px(12), self.px(12))
        self.timing = self.label(left, "", 13, C_MUTED)
        self._level_clip = None
        self._vad_on = None

        self.wake = self.label(left, "", 40, C_WARN)
        self.wake.add_flag(lv.obj.FLAG.FLOATING)
        self.wake.set_style_bg_color(lv.color_hex(C_BG), 0)
        self.wake.set_style_bg_opa(200, 0)
        self.wake.set_style_radius(self.px(12), 0)
        self.wake.set_style_pad_all(self.px(14), 0)
        self.wake.align(lv.ALIGN.CENTER, 0, -self.px(10))
        self.wake.add_flag(lv.obj.FLAG.HIDDEN)

        self.list_title = self.label(right, "", 15, C_MUTED)
        self.kw_list = self.box(right, lv.FLEX_FLOW.COLUMN, gap=6)
        self.kw_list.set_width(lv.pct(100))
        self.kw_list.set_flex_grow(1)
        self.kw_list.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.kw_list.set_scroll_dir(lv.DIR.VER)

        # footer buttons
        foot = self.box(scr, lv.FLEX_FLOW.ROW_WRAP, gap=8)
        foot.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.btn_enroll, self.btn_enroll_lbl = self.button(foot, self.t("new"), "enroll")
        self.btn_rec, self.btn_rec_lbl = self.button(foot, self.t("rec"), "record", C_OK)
        self.btn_det, self.btn_det_lbl = self.button(foot, self.t("detect"), "detect", 0x8957E5)
        self.btn_clear, self.btn_clear_lbl = self.button(foot, self.t("clear"), "clear", C_DANGER)

    def build_language(self, parent):
        """中文 | English segmented control; only languages this firmware has."""
        bar = self.box(parent, lv.FLEX_FLOW.ROW, bg=C_CARD, radius=10, gap=4)
        bar.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        self.lang_btns = []
        for lang in self.langs:
            b = lv.btn(bar)
            b.set_size(max(74, self.px(80)), max(MIN_TOUCH_PX, self.px(40)))
            b.set_style_radius(self.px(8), 0)
            b.set_style_shadow_width(0, 0)
            b.add_event(lambda e, k=lang: self.request(("lang", k)), lv.EVENT.CLICKED, None)
            l = self.label(b, LANG_LABEL[lang], 15)
            l.center()
            on = lang == self.lang
            b.set_style_bg_color(lv.color_hex(C_OK if on else C_CARD), 0)
            l.set_style_text_color(lv.color_hex(0xFFFFFF if on else C_MUTED), 0)
            self.lang_btns.append((lang, b, l))

    def build_sensitivity(self, parent):
        """Sensitivity segmented control; its labels come from the profile."""
        bar = self.box(parent, lv.FLEX_FLOW.ROW, bg=C_CARD, radius=10, gap=4)
        bar.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        self.sens_btns = []
        tiers = self.eng.profile["tiers"]
        wide = self.lang == "en"
        for i, tier in enumerate(tiers):
            b = lv.btn(bar)
            b.set_size(max(84 if wide else 52, self.px(92 if wide else 56)),
                       max(MIN_TOUCH_PX, self.px(40)))
            b.set_style_radius(self.px(8), 0)
            b.set_style_shadow_width(0, 0)
            b.add_event(lambda e, k=i: self.request(("sens", k)), lv.EVENT.CLICKED, None)
            l = self.label(b, tier[0], 14 if wide else 16)
            l.center()
            self.sens_btns.append((b, l))
        self.style_sensitivity()

    def style_sensitivity(self):
        for i, (b, l) in enumerate(self.sens_btns):
            on = i == self.sens_idx
            b.set_style_bg_color(lv.color_hex(C_ACCENT if on else C_CARD), 0)
            l.set_style_text_color(lv.color_hex(0xFFFFFF if on else C_MUTED), 0)

    def rebuild_list(self):
        """Keyword rows: colour dot, id + threshold, units, delete button.

        clean() drops the scroll offset back to zero, and arming a delete
        confirmation rebuilds the list. With the list full the lower rows only
        exist below the fold, so the first tap on a row's "delete" used to
        scroll that row's own "confirm" button off the screen. Remember where
        the user was and put them back.
        """
        scroll_y = self.kw_list.get_scroll_y()
        self.kw_list.clean()
        armed = self.del_armed[0] if self.del_armed else None
        armed_row = None
        busy = self.state in (RECORDING, COMPUTING)
        for i, rec in enumerate(self.recs):
            row = self.box(self.kw_list, lv.FLEX_FLOW.ROW, bg=C_ROW, radius=8, pad=8, gap=8)
            row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            dot = self.box(row, bg=self.kw_color(i), radius=6)
            dot.set_size(self.px(12), self.px(12))
            col = self.box(row, lv.FLEX_FLOW.COLUMN, gap=2)
            col.set_height(lv.SIZE_CONTENT)
            col.set_flex_grow(1)
            verify = "" if openkws.verify_threshold(rec) is None else self.t("verify")
            self.label(col, self.t("th") % (rec["kw_id"], rec["threshold"], verify), 15)
            ph = self.label(col, self.eng.unit_text(rec), 13, C_MUTED)
            ph.set_width(lv.pct(100))
            ph.set_long_mode(lv.label.LONG.DOT)
            confirm = rec["kw_id"] == armed
            if confirm:
                armed_row = row
            b = lv.btn(row)
            b.set_size(lv.SIZE_CONTENT, max(MIN_TOUCH_PX - 6, self.px(34)))
            b.set_ext_click_area(self.px(8))
            b.set_style_radius(self.px(8), 0)
            b.set_style_shadow_width(0, 0)
            b.set_style_bg_color(lv.color_hex(C_DANGER if confirm else 0x3A4250), 0)
            b.add_event(lambda e, k=rec["kw_id"]: self.request(("delete", k)),
                        lv.EVENT.CLICKED, None)
            bl = self.label(b, self.t("del_q") if confirm else self.t("del"), 14, 0xFFFFFF)
            bl.center()
            if busy:
                b.add_state(lv.STATE.DISABLED)
        if not self.recs:
            hint = self.label(self.kw_list, self.t("no_kw"), 15, C_MUTED)
            hint.set_width(lv.pct(100))
        self.set_text(self.list_title, self.t("kw_count") % (len(self.recs), MAX_KEYWORDS))
        # The rows were just created, so their geometry is still stale; both
        # calls below need it. scroll_to_y() is bounded, so a stale offset
        # after a deletion shortened the list simply lands at the new bottom.
        self.kw_list.update_layout()
        self.kw_list.scroll_to_y(scroll_y, lv.ANIM.OFF)
        if armed_row is not None:
            armed_row.scroll_to_view(lv.ANIM.OFF)   # also covers a half-row

    def request(self, action):
        self.pending = action

    def apply_sensitivity(self):
        self.eng.set_tier(self.sens_idx)
        bias = self.eng.tier_bias(self.sens_idx)
        th = int(max(CHART_MIN, min(CHART_MAX, bias)) * 100)
        self.chart.set_all_value(self.ser_th, th)

    def set_status(self, text):
        self.set_text(self.status, text)
        print("[open_kws:%s]" % self.lang, text)

    def enable(self, btn, on):
        if on:
            btn.clear_state(lv.STATE.DISABLED)
        else:
            btn.add_state(lv.STATE.DISABLED)

    def refresh(self):
        s = self.state
        enrolling = s in (READY, RECORDING, COMPUTING)
        self.set_text(self.btn_enroll_lbl, self.t("cancel") if enrolling else self.t("new"))
        self.enable(self.btn_enroll, enrolling or (s == IDLE and len(self.recs) < MAX_KEYWORDS))
        self.enable(self.btn_rec, s == READY)
        if s == RECORDING:
            self.set_text(self.btn_rec_lbl, self.t("recording"))
        elif s == READY:
            self.set_text(self.btn_rec_lbl, self.t("rec_n") % (len(self.clips) + 1))
        else:
            self.set_text(self.btn_rec_lbl, self.t("rec"))
        self.enable(self.btn_det, s in (IDLE, DETECTING) and len(self.recs) > 0)
        self.set_text(self.btn_det_lbl, self.t("stop") if s == DETECTING else self.t("detect"))
        self.enable(self.btn_clear, s not in (RECORDING, COMPUTING))
        self.set_text(self.btn_clear_lbl,
                      self.t("clear_q") if self.clear_armed else self.t("clear"))
        # the language buttons must not change the engine mid-enrollment
        for lang, b, l in self.lang_btns:
            self.enable(b, not enrolling or lang == self.lang)

    def kw_color(self, idx):
        return KW_COLORS[idx % len(KW_COLORS)]

    # ------------------------------------------------------------ keyword files
    def enroll_dir(self):
        return self.eng.enroll_dir

    def list_enroll_dir(self):
        try:
            return os.listdir(self.enroll_dir()[:-1])
        except OSError:
            return []

    def next_kw_id(self):
        used = [kw_index(r["kw_id"] + ".json") for r in self.recs]
        used = [u for u in used if u is not None]
        return "kw_%d" % (max(used) + 1 if used else 0)

    def load_keywords(self):
        names = self.list_enroll_dir()
        files = sorted((kw_index(n), n) for n in names if kw_index(n) is not None)
        bad = 0
        for _, name in files[:MAX_KEYWORDS]:
            try:
                with open(self.enroll_dir() + name) as f:
                    rec = json.load(f)
                # A record made for the other language decodes to nonsense: all
                # of the English unit ids are valid Chinese ones too, so the
                # engine would accept it silently.
                if not self.eng.accepts(rec):
                    raise ValueError("record is not for %s" % self.lang)
                rec["kw_id"] = name[:-5]           # the file name is the identity
                if openkws.verify_threshold(rec) is None:
                    rec["verify_threshold"] = self.eng.profile["verify_threshold"]
                self.eng.add_keyword(rec)
                self.recs.append(rec)
            except Exception as e:
                bad += 1
                print("skip %s: %s" % (name, e))
        if self.recs:
            self.set_status(self.t("loaded") % (
                len(self.recs), self.t("bad_files") % bad if bad else ""))
        else:
            self.set_status(self.t("start_hint"))

    def load_settings(self):
        try:
            with open(SETTINGS_JSON) as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        try:
            with open(SETTINGS_JSON, "w") as f:
                json.dump({"mic_volume": self.mic_volume, "lang": self.lang}, f)
        except OSError as e:
            print("save settings failed:", e)

    def lower_mic_gain(self):
        """Clipped take: one step down, persisted. False when already at the floor."""
        if not AUTO_MIC_GAIN or self.mic_volume <= MIC_VOLUME_MIN:
            return False
        self.mic_volume = max(MIC_VOLUME_MIN, self.mic_volume - MIC_VOLUME_STEP)
        self.stream.volume(vol=self.mic_volume)
        self.save_settings()
        self.noise_hist = []        # the floor changes with the gain
        self.noise = None
        print("mic volume ->", self.mic_volume)
        return True

    def save_keyword(self, rec):
        openkws.ensure_dir(self.enroll_dir())   # enroll/<lang>/, parent included
        with open(self.enroll_dir() + rec["kw_id"] + ".json", "w") as f:
            json.dump(rec, f)

    def remove_files(self, names):
        removed = 0
        for name in names:
            try:
                os.remove(self.enroll_dir() + name)
                removed += 1
            except OSError as e:
                print("remove %s failed: %s" % (name, e))
        return removed

    def delete_keyword(self, kw_id):
        self.recs = [r for r in self.recs if r["kw_id"] != kw_id]
        if self.recs:
            self.eng.set_keywords(self.recs)
        else:
            self.eng.clear_keywords()
        removed = self.remove_files(kw_files(kw_id, self.list_enroll_dir()))
        if self.state == DETECTING and not self.recs:
            self.state = IDLE
            self.hide_wake()
        self.set_status(self.t("deleted") % (kw_id, removed, len(self.recs)))

    def clear_all(self):
        """One-key clear: engine keywords, enroll files and recordings of the
        current language only; the other language's words are untouched."""
        self.abort_enroll()
        self.state = IDLE
        self.eng.clear_keywords()
        self.recs = []
        removed = self.remove_files([n for n in self.list_enroll_dir() if is_enroll_file(n)])
        self.hide_wake()
        self.chart.set_all_value(self.ser_score, int(CHART_MIN * 100))
        self.set_status(self.t("cleared") % removed)

    # ------------------------------------------------------------ actions
    def handle_action(self, action):
        kind = action[0] if isinstance(action, tuple) else action
        if kind != "clear":
            self.clear_armed = 0
        if kind != "delete":
            self.del_armed = None
        list_dirty = kind in ("delete", "clear")
        busy = self.state in (RECORDING, COMPUTING)

        if kind == "lang":
            if action[1] != self.lang and not busy:
                self.switch_language(action[1])
                return                      # open_language() already refreshed
        elif kind == "sens":
            if action[1] != self.sens_idx:
                self.sens_idx = action[1]
                self.style_sensitivity()
                self.apply_sensitivity()
                self.set_status(self.t("sens") % self.eng.profile["tiers"][self.sens_idx][0])
        elif kind == "delete" and not busy:
            kw_id = action[1]
            if self.del_armed and self.del_armed[0] == kw_id:
                self.del_armed = None
                self.delete_keyword(kw_id)
            else:
                self.del_armed = (kw_id, time.ticks_add(time.ticks_ms(), CONFIRM_MS))
                self.set_status(self.t("del_hint") % kw_id)
        elif kind == "clear" and not busy:
            if self.clear_armed:
                self.clear_armed = 0
                self.clear_all()
            else:
                self.clear_armed = time.ticks_add(time.ticks_ms(), CONFIRM_MS)
                self.set_status(self.t("clear_hint"))
        elif kind == "enroll":
            if self.state in (READY, RECORDING, COMPUTING):
                self.abort_enroll()
                self.state = IDLE
                self.set_status(self.t("cancelled"))
                list_dirty = True
            elif self.state == IDLE:
                if len(self.recs) >= MAX_KEYWORDS:
                    self.set_status(self.t("enroll_full") % MAX_KEYWORDS)
                else:
                    self.eng.enroll_begin()
                    self.clips = []
                    self.state = READY
                    self.set_status(self.t("enroll_start") % self.next_kw_id())
        elif kind == "record" and self.state == READY:
            self.rec_chunks = []
            self.rec_n = 0
            self.rec_speech = False
            self.rec_silence = 0
            self.rec_onset = 0
            self.rec_voiced = 0
            self.state = RECORDING
            self.set_status(self.t("say_now"))
            list_dirty = True
        elif kind == "detect" and self.recs:
            if self.state == DETECTING:
                self.state = IDLE
                self.hide_wake()
                self.set_status(self.t("det_stopped"))
            elif self.state == IDLE:
                self.eng.reset()
                self.n_push = 0
                self.state = DETECTING
                self.set_status(self.t("detecting") % len(self.recs))
        if list_dirty:
            self.rebuild_list()
        self.refresh()

    def abort_enroll(self):
        if self.state in (READY, RECORDING, COMPUTING):
            try:
                self.eng.enroll_end()
            except Exception as e:
                print("enroll_end failed:", e)
        self.clips = []
        self.rec_chunks = []
        self.finalizer = None

    def fail_enroll(self, text):
        self.set_status(text)
        self.abort_enroll()
        self.state = IDLE
        self.rebuild_list()

    # ------------------------------------------------------------ recording
    def track_noise(self, rms):
        """Noise floor = lowest chunk level of the last ~3 s (speech has gaps,
        so a short burst of talking does not raise it)."""
        self.noise_hist.append(max(rms, 1e-4))
        if len(self.noise_hist) > NOISE_WINDOW:
            self.noise_hist.pop(0)
        self.noise = min(self.noise_hist)

    def is_speech(self, rms):
        noise = self.noise if self.noise is not None else SILENCE_MIN
        return rms > max(noise * SPEECH_RATIO, SPEECH_MIN) or rms > SPEECH_ABS

    def on_record_chunk(self, pcm, rms):
        """Endpointing: wait for speech, stop after trailing silence. The noise
        floor stays frozen at its pre-recording value."""
        noise = self.noise if self.noise is not None else SILENCE_MIN
        quiet = rms < max(noise * SILENCE_RATIO, SILENCE_MIN)
        self.rec_n += 1
        self.rec_chunks.append(pcm)
        if not self.rec_speech:
            if self.is_speech(rms):
                # One loud chunk is a door, a chair or a keystroke. Require the
                # level to hold, or the take starts on a transient and the
                # trailing-silence counter ends it before the user has said
                # anything -- which is what "recording too short" really was.
                self.rec_onset += 1
                if self.rec_onset < REC_ONSET_CHUNKS:
                    return
                self.rec_speech = True
                self.rec_voiced = self.rec_onset - 1   # this chunk counts below
                self.set_status(self.t("recording_now"))
            else:
                self.rec_onset = 0
                # while, not if: an onset that failed to hold left its chunks
                # behind, so a single pop per quiet chunk lets the preroll
                # creep up until it alone reaches REC_MAX_CHUNKS and ends the
                # take the moment the user finally speaks.
                while len(self.rec_chunks) > REC_PREROLL:
                    self.rec_chunks.pop(0)
                if self.rec_n >= REC_WAIT_CHUNKS:
                    self.state = READY
                    self.rec_chunks = []
                    self.set_status(self.t("no_speech_take") % (len(self.clips) + 1))
                    self.rebuild_list()
                    self.refresh()
                return
        if quiet:
            self.rec_silence += 1
        else:
            self.rec_silence = 0
            self.rec_voiced += 1
        # Trailing silence may only end the take once enough speech is actually
        # in it. A transient long enough to pass the onset guard -- a truck
        # going by, a cough -- would otherwise yield a take of two chunks, far
        # below the 0.5-0.6 s the enroller needs; instead the recorder keeps
        # listening for the word.
        done = self.rec_silence >= REC_END_SILENCE and self.rec_voiced >= REC_MIN_VOICED
        if done or len(self.rec_chunks) >= REC_MAX_CHUNKS:
            self.finish_recording()
            self.rebuild_list()
            self.refresh()

    def finish_recording(self):
        pcm = b"".join(self.rec_chunks)
        self.rec_chunks = []
        self.state = READY
        n = len(self.clips) + 1
        span = openkws.trim(pcm, self.lang)
        # the endpointer already heard speech: keep its segment if trimming fails
        seg = pcm[span[0] * 2:span[1] * 2] if span else pcm
        # SNR reference: the ambient level measured while idle (DC removed)
        ok, reason, m = self.eng.enroll_add(seg, self.noise)
        print("take %d: %s dur %.2fs peak %.3f clip %.2f%% snr %.1fdB "
              "ambient %.4f mic %d voiced %d/%d" % (
                  n, reason, m["dur"], m["peak"], m["clip_ratio"] * 100, m["snr_db"],
                  self.noise or 0.0, self.mic_volume, self.rec_voiced, self.rec_n))
        if not ok:
            if reason == "clipped" and self.lower_mic_gain():
                note = self.t("take_loud_note") if self.recs else ""
                self.set_status(self.t("take_loud") % (n, self.mic_volume, note))
            elif reason == "too noisy":
                self.set_status(self.t("take_noisy") % (n, m["snr_db"], openkws.MIN_SNR_DB))
            else:
                self.set_status(self.t("take_bad") % (
                    n, self.t("reason").get(reason, reason), m["dur"], m["peak"],
                    m["clip_ratio"] * 100, m["snr_db"]))
            return
        self.clips.append(seg)
        if len(self.clips) < N_CLIPS:
            # Accepted above MIN_SNR_DB but below the comfortable level: say so
            # rather than reject, so the user can still enrol in a noisy room
            # and knows why the word may wake less reliably.
            key = "take_ok" if m["snr_db"] >= openkws.WARN_SNR_DB else "take_ok_noisy"
            self.set_status(self.t(key) % (
                len(self.clips), m["dur"], m["snr_db"], len(self.clips) + 1))
        else:
            self.state = COMPUTING
            self.set_status(self.t("computing"))

    # ------------------------------------------------------------ enrollment
    def compute_step(self):
        if self.finalizer is not None:
            try:
                next(self.finalizer)
            except StopIteration:
                self.finalizer = None
                self.rebuild_list()
                self.refresh()
            return
        done, progress, total = self.eng.enroll_step()
        self.set_status(self.t("computing_n") % (progress, total))
        if done:
            self.finalizer = self.finalize()

    def finalize(self):
        """Result + similarity checks, one unit of work per main-loop tick."""
        kw_id = self.next_kw_id()
        try:
            rec = self.eng.enroll_result(kw_id)
        except ValueError as e:
            msg = str(e)
            self.fail_enroll(self.t("fail") % self.t("err").get(msg, msg))
            return
        self.set_status(self.t("sim_check"))
        yield
        # a registered word must not wake on the new word (both stages) ...
        worst = None
        for other, margin, score, cut in self.eng.enroll_confusion():
            print("confusion %s on new clips: margin %.2f score %s cut %s" % (
                other, margin, score, cut))
            if would_wake(margin, score, cut) and (worst is None or margin > worst[1]):
                worst = (other, margin)
        if worst is not None:
            self.fail_enroll(self.t("too_similar") % worst)
            return
        # ... nor the new word on a registered one: replay its saved clips
        # (catches e.g. a new word that is the tail of a registered one)
        names = self.list_enroll_dir()
        jobs = []
        for old in self.recs:
            for n in kw_files(old["kw_id"], names):
                if n.endswith(".wav"):
                    jobs.append((old["kw_id"], n))
        for i, (old_id, name) in enumerate(jobs):
            self.set_status(self.t("sim_check_n") % (i + 1, len(jobs)))
            yield
            try:
                pcm = read_wav(self.enroll_dir() + name)
            except OSError:
                continue
            margin, score, cut = self.eng.probe(rec, pcm)
            print("probe new word on %s: margin %.2f score %s cut %s" % (name, margin, score, cut))
            if would_wake(margin, score, cut):
                self.fail_enroll(self.t("reverse_similar") % (old_id, margin))
                return
        self.eng.enroll_end()
        try:
            rec["created"] = "%04d-%02d-%02dT%02d:%02d:%02d" % time.localtime()[:6]
        except Exception:
            pass
        self.save_keyword(rec)
        if SAVE_CLIPS:
            for i, seg in enumerate(self.clips):
                try:
                    save_wav(self.enroll_dir() + "%s_clip_%d.wav" % (kw_id, i + 1), seg)
                except Exception as e:
                    print("save clip failed:", e)
        self.eng.add_keyword(rec)
        self.recs.append(rec)
        self.clips = []
        self.state = IDLE
        self.set_status(self.t("enrolled") % (
            kw_id, self.eng.unit_text(rec), rec["threshold"], len(self.recs)))
        print(json.dumps(rec))

    # ------------------------------------------------------------ detection
    def hide_wake(self):
        self.wake.add_flag(lv.obj.FLAG.HIDDEN)
        self.wake_until = 0

    def show_level(self, rms, peak=0.0):
        clip = peak >= LEVEL_CLIP_PEAK
        if clip != self._level_clip:
            self._level_clip = clip
            self.level.set_style_bg_color(lv.color_hex(C_DANGER if clip else C_OK),
                                          lv.PART.INDICATOR)
        db = 20.0 * math.log10(rms) if rms > 1e-9 else -100.0
        self.level.set_value(
            int(max(0.0, min(100.0, (db + LEVEL_DB_RANGE) * 100.0 / LEVEL_DB_RANGE))), lv.ANIM.OFF)

    def on_wake(self, events):
        # several words may fire in the same chunk: report the clearest one
        best = None
        for kw_id, score, th, start_ms, end_ms, weak in events:
            print(">>> WAKE %s score=%.3f th=%.3f weakest=%s @%.2fs" % (
                kw_id, score, th, "n/a" if weak is None else "%.2f" % weak, end_ms / 1000))
            if best is None or score - th > best[1] - best[2]:
                best = (kw_id, score, th, weak)
        kw_id, score, th, weak = best
        idx = 0
        for i, r in enumerate(self.recs):
            if r["kw_id"] == kw_id:
                idx = i
        self.wake.set_text(self.t("wake") % kw_id)
        self.wake.set_style_text_color(lv.color_hex(self.kw_color(idx)), 0)
        self.wake.clear_flag(lv.obj.FLAG.HIDDEN)
        self.wake_until = time.ticks_add(time.ticks_ms(), WAKE_SHOW_MS)
        self.set_status(self.t("woke") % (
            kw_id, self.eng.unit_text(self.recs[idx]), score, th,
            "" if weak is None else self.t("woke_weak") % weak))
        self.speaker.play()

    def on_detect_chunk(self, pcm):
        events = self.eng.push(pcm)
        st = self.eng.stats()
        self.n_push += 1
        margin = CHART_MIN
        for k in st["keywords"]:
            margin = max(margin, k["chunk_max"] - k["threshold"])
        self.chart.set_next_value(self.ser_score, int(min(CHART_MAX, margin) * 100))
        self.show_level(st["level"])
        self.set_vad(st["speech"])
        if self.n_push % 6 == 0:
            n = self.n_push
            vetoed = 0
            for k in st["keywords"]:
                vetoed += k["n_rejected"]
            self.set_text(self.timing, self.t("timing") % (
                (st["fe_ms"] + st["kpu_ms"] + st["dec_ms"]) / n, st["fe_ms"] / n,
                st["kpu_ms"] / n, st["dec_ms"] / n, vetoed))
        if events:
            self.on_wake(events)

    def set_vad(self, on):
        if on != self._vad_on:
            self._vad_on = on
            self.vad.set_style_bg_color(lv.color_hex(C_OK if on else C_ROW), 0)

    # ------------------------------------------------------------ main loop
    def tick(self):
        try:
            self._tick()
        except Exception as e:
            # model / file errors: recover instead of exiting (KeyboardInterrupt
            # is not an Exception and still stops the app)
            _sys.print_exception(e)
            if self.state == DETECTING:
                self.state = IDLE
                self.hide_wake()
                self.set_status(self.t("det_err") % e)
            elif self.state in (READY, RECORDING, COMPUTING):
                self.fail_enroll(self.t("enroll_err") % e)
            self.refresh()

    def _tick(self):
        if self.pending:
            action, self.pending = self.pending, None
            self.handle_action(action)
        if self.state == COMPUTING:
            self.stream.read(block=False)     # keep the capture queue drained
            self.compute_step()
            if self.state != COMPUTING:
                self.refresh()
        else:
            # non-blocking (<= 10 ms): LVGL runs between audio chunks, so touch is
            # sampled every ~10-20 ms instead of once per 160 ms chunk; frames
            # wait in the capture queue meanwhile
            pcm = self.stream.read(block=False)
            if pcm:
                if self.state == DETECTING:
                    self.on_detect_chunk(pcm)
                else:
                    rms, peak = openkws.level(pcm)
                    self.show_level(rms, peak)
                    if self.state == RECORDING:
                        self.on_record_chunk(pcm, rms)
                    else:
                        self.track_noise(rms)
        now = time.ticks_ms()
        if self.wake_until and time.ticks_diff(now, self.wake_until) > 0:
            self.hide_wake()
        if self.clear_armed and time.ticks_diff(now, self.clear_armed) > 0:
            self.clear_armed = 0
            self.set_status(self.t("clear_cancel"))
            self.refresh()
        if self.del_armed and time.ticks_diff(now, self.del_armed[1]) > 0:
            self.del_armed = None
            self.set_status(self.t("del_cancel"))
            self.rebuild_list()

    def close(self):
        if self.eng is not None:
            self.eng.close()
            self.eng = None


def pick_start_language():
    """Last used language if the firmware still has it, else LANG_DEFAULT,
    else whatever is available."""
    langs = openkws.available()
    if not langs:
        raise RuntimeError("no keyword spotting module in this firmware")
    try:
        with open(SETTINGS_JSON) as f:
            want = json.load(f).get("lang")
    except Exception:
        want = None
    for cand in (want, LANG_DEFAULT):
        if cand in langs:
            return cand
    return langs[0]


def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    touch = None
    p = None
    stream = None
    speaker = None
    app = None
    try:
        lang = pick_start_language()
        print("languages available:", openkws.available(), "-> starting in", lang)
        screen = Screen()
        touch = Touch(screen)
        p = PyAudio()
        stream = p.open(format=paInt16, channels=1, rate=SAMPLE_RATE, input=True,
                        frames_per_buffer=CHUNK)
        speaker = Speaker(p)
        app = OpenKwsApp(screen, stream, speaker, lang)
        print("Open-KWS ready.")
        while True:
            os.exitpoint()
            app.tick()
            lv.task_handler()
    except KeyboardInterrupt as e:
        print("user stop:", e)
    except BaseException as e:
        _sys.print_exception(e)
    finally:
        if speaker:
            speaker.close()
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception as e:
                print("stream close failed:", e)
        if p:
            p.terminate()
        if app:
            app.close()
        if touch:
            touch.deinit()
        lv.deinit()
        Display.deinit()
        gc.collect()
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)


if __name__ == "__main__":
    main()
