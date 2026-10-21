"""Local Chinese Tk desktop studio. Importing this module opens no windows."""
from __future__ import annotations

from dataclasses import asdict, fields
import json
import math
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import wave

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageTk
from . import media, presets, renderer

BG = "#0c1018"
PANEL = "#141b27"
INPUT = "#1c2635"
TEXT = "#edf3fb"
MUTED = "#8f9db2"
ACCENT = "#57ddbe"
RESOLUTIONS = ("960 × 540", "1920 × 1080", "3840 × 2160", "540 × 960")
POSITIONS = {"居中": "center", "左上": "top-left", "右上": "top-right",
             "左下": "bottom-left", "右下": "bottom-right", "自定义": "custom"}
FORMATS = ("MP4", "MOV", "WEBM", "MKV", "AVI", "GIF", "ZIP")
NUMERIC = ("entrance", "fade_out", "hold", "start_delay", "gain", "card_scale")


class TeamRadioApp(ttk.Frame):
    """All Tk access stays on the main thread; workers only enqueue results."""

    def __init__(self, master):
        super().__init__(master, style="Root.TFrame")
        self.root = master
        self.root.title("F1 TEAM RADIO · 无线电动画工作室")
        self._fit_window()
        self.root.configure(bg=BG)
        self.pack(fill="both", expand=True)
        self.events = queue.Queue()
        self._workers = set()
        self._closing = self._closed = False
        self._loading = True
        self._render_after = self._poll_after = self._play_after = self._resize_after = None
        self._analyze_cancel = threading.Event()
        self._export_cancel = threading.Event()
        self._analysis_generation = self._play_generation = 0
        self._temp_dir = Path(tempfile.mkdtemp(prefix="teamradio-preview-"))
        self._wav_path = self.audio_path = self.analyzer = None
        self.audio_duration = 0.0
        self._analyzer_settings = None
        self._card = self.config = self._photo = None
        self._playing = self._audio_started = False
        self._clock_origin = 0.0
        self._exporting = self._analyzing = False
        self._last_error = ""
        try:
            import winsound
            self._winsound = winsound
        except ImportError:
            self._winsound = None
        self._style()
        self._make_vars()
        self._build()
        self._protect_settings_mousewheel()
        self._driver_changed()
        self._loading = False
        self._refresh_config()
        self.timeline.set(self.audio_start + .25)
        self._render_preview()
        self._set_busy()
        self._poll_after = self.root.after(50, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<space>", self._space)

    def _fit_window(self):
        left, top = 0, 0
        right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes
            area = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
                left, top, right, bottom = area.left, area.top, area.right, area.bottom
        except (AttributeError, OSError):
            pass
        width, height = min(1280, right - left - 40), min(860, bottom - top - 64)
        self.root.geometry(f"{width}x{height}{left + (right-left-width)//2:+d}{top + (bottom-top-height)//2:+d}")
        self.root.minsize(min(980, width), min(680, height))

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT,
                        font=("Microsoft YaHei UI", 10), borderwidth=0)
        style.configure("Root.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Header.TLabel", background=BG, foreground=TEXT,
                        font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Kicker.TLabel", background=BG, foreground=ACCENT,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Section.TLabel", foreground=ACCENT,
                        font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TButton", background=INPUT, foreground=TEXT,
                        padding=(12, 8), focusthickness=1, focuscolor=ACCENT)
        style.map("TButton", background=[("active", "#29394c"), ("disabled", "#18202c")],
                  foreground=[("disabled", "#69768a")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#08231d",
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#85ead4"), ("disabled", "#23483f")])
        style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT, padding=7)
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT,
                        foreground=TEXT, arrowcolor=ACCENT, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT)],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", INPUT)],
                  selectforeground=[("readonly", TEXT)])
        style.configure("TSpinbox", fieldbackground=INPUT, background=INPUT,
                        foreground=TEXT, arrowcolor=ACCENT, padding=6)
        style.configure("Horizontal.TScale", background=PANEL, troughcolor=INPUT)
        style.configure("TProgressbar", background=ACCENT, troughcolor=INPUT, borderwidth=0, thickness=6)
        style.configure("Vertical.TScrollbar", background=INPUT, troughcolor=PANEL, arrowcolor=MUTED)
        self.root.option_add("*TCombobox*Listbox.background", INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#314457")

    def _make_vars(self):
        self.driver_labels = {key: f"{str(value['number']):>2}  ·  {value['name']}"
                              for key, value in presets.DRIVERS.items()}
        self.team_labels = {key: value["name"] for key, value in presets.TEAMS.items()}
        driver = "albon" if "albon" in presets.DRIVERS else next(iter(presets.DRIVERS))
        render_defaults = renderer.RenderConfig()
        defaults = dict(driver=self.driver_labels[driver], name="", number="", team="",
                        color=ACCENT, logo_variant="白色队标", logo_path="",
                        resolution=RESOLUTIONS[0], fps="30", entrance=str(render_defaults.entrance), fade_out="0.3",
                        hold="0.25", start_delay="0", gain="1", card_scale="0.90",
                        position="居中", custom_x="0", custom_y="0",
                        background="透明", background_color="#10121a", format="MP4")
        self.vars = {key: tk.StringVar(self.root, value=value) for key, value in defaults.items()}
        self.status = tk.StringVar(self.root, value="选择一段音频，开始制作。")
        self.audio_label = tk.StringVar(self.root, value="尚未选择音频")
        self.audio_detail = tk.StringVar(self.root, value="支持 WAV / MP3 / M4A / FLAC 等；保留完整时长")
        self.playback_label = tk.StringVar(self.root, value="静音预览 · 请先选择音频")
        self.time_label = tk.StringVar(self.root, value="00:00.00 / 00:00.00")
        self.format_note = tk.StringVar(self.root)
        self.timeline = tk.DoubleVar(self.root, value=0)
        self.progress = tk.DoubleVar(self.root, value=0)
        for key, var in self.vars.items():
            var.trace_add("write", lambda *_args, k=key: self._value_changed(k))

    def _build(self):
        top = ttk.Frame(self, style="Root.TFrame", padding=(24, 19, 24, 16))
        top.pack(fill="x")
        titles = ttk.Frame(top, style="Root.TFrame")
        titles.pack(side="left")
        ttk.Label(titles, text="F1  /  TEAM RADIO STUDIO", style="Kicker.TLabel").pack(anchor="w")
        ttk.Label(titles, text="把无线电，变成赛道瞬间。", style="Header.TLabel").pack(anchor="w", pady=(4, 0))
        actions = ttk.Frame(top, style="Root.TFrame")
        actions.pack(side="right", anchor="s")
        ttk.Button(actions, text="载入配置", command=self.load_config).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="保存配置", command=self.save_config).pack(side="left")
        body = ttk.Frame(self, style="Root.TFrame", padding=(20, 0, 20, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body, style="Panel.TFrame", width=370)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        left.grid_propagate(False)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.settings_canvas = tk.Canvas(left, bg=PANEL, width=350, highlightthickness=0)
        self.settings_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.settings_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)
        self.controls = ttk.Frame(self.settings_canvas, padding=(18, 16, 18, 20))
        self._controls_window = self.settings_canvas.create_window((0, 0), window=self.controls, anchor="nw")
        self.controls.bind("<Configure>", lambda _e: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self.settings_canvas.bind("<Configure>", lambda e: self.settings_canvas.itemconfigure(self._controls_window, width=e.width))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(sequence, self._mousewheel, add="+")
        c = self.controls
        self._section(c, "01  音频素材")
        self.audio_button = ttk.Button(c, text="＋  选择音频文件", command=self.select_audio, style="Accent.TButton")
        self.audio_button.pack(fill="x", pady=(8, 9))
        ttk.Label(c, textvariable=self.audio_label, wraplength=290).pack(anchor="w")
        ttk.Label(c, textvariable=self.audio_detail, style="Muted.TLabel", wraplength=290).pack(anchor="w", pady=(4, 0))
        self._section(c, "02  车手与视觉")
        self.driver_combo = self._combo(c, "车手预设", "driver", list(self.driver_labels.values()))
        self.driver_combo.bind("<<ComboboxSelected>>", lambda _e: self._driver_changed())
        row = ttk.Frame(c)
        row.pack(fill="x", pady=5)
        row.columnconfigure((0, 1), weight=1)
        self._grid_entry(row, "显示姓名", "name", 0)
        self._grid_entry(row, "号码", "number", 1)
        self.team_combo = self._combo(c, "独立选择车队", "team", list(self.team_labels.values()))
        self.team_combo.bind("<<ComboboxSelected>>", lambda _e: self._team_changed())
        self._label(c, "统一强调色 · 姓名 / 号码 / 声波")
        colors = ttk.Frame(c)
        colors.pack(fill="x", pady=(2, 5))
        self.color_swatch = tk.Canvas(colors, width=28, height=28, bg=ACCENT, highlightthickness=0, cursor="hand2")
        self.color_swatch.pack(side="left", padx=(0, 8))
        self.color_swatch.bind("<Button-1>", lambda _e: self._choose_color("color"))
        ttk.Entry(colors, textvariable=self.vars["color"], width=12).pack(side="left", fill="x", expand=True)
        ttk.Button(colors, text="选色", command=lambda: self._choose_color("color")).pack(side="left", padx=(7, 0))
        ttk.Button(c, text="恢复当前车队颜色", command=self._restore_team_color).pack(fill="x", pady=(0, 5))
        self._combo(c, "队标样式", "logo_variant", ("白色队标", "彩色队标", "上传图片"))
        logos = ttk.Frame(c)
        logos.pack(fill="x", pady=4)
        ttk.Entry(logos, textvariable=self.vars["logo_path"], width=18).pack(side="left", fill="x", expand=True)
        ttk.Button(logos, text="上传…", command=self._upload_logo).pack(side="left", padx=(7, 0))
        self._section(c, "03  画布与背景")
        self._combo(c, "输出分辨率", "resolution", RESOLUTIONS)
        self._combo(c, "帧率 FPS", "fps", ("24", "25", "30", "50", "60"))
        self._combo(c, "背景", "background", ("透明", "纯色"))
        backgrounds = ttk.Frame(c)
        backgrounds.pack(fill="x", pady=4)
        ttk.Entry(backgrounds, textvariable=self.vars["background_color"]).pack(side="left", fill="x", expand=True)
        ttk.Button(backgrounds, text="背景色", command=lambda: self._choose_color("background_color")).pack(side="left", padx=(7, 0))
        self._section(c, "04  动画与布局")
        for label, key, low, high, step in (
            ("入场时长（秒）", "entrance", 0, 60, .05),
            ("淡出时长（秒）", "fade_out", 0, 60, .05),
            ("尾部停留（秒）", "hold", 0, 3600, .05),
            ("开始延迟（秒）", "start_delay", 0, 3600, .1),
            ("声波增益", "gain", .01, 20, .1),
            ("卡片缩放", "card_scale", .1, 1, .05),
        ):
            row = ttk.Frame(c)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label).pack(side="left")
            ttk.Spinbox(row, textvariable=self.vars[key], from_=low, to=high, increment=step, width=9).pack(side="right")
        self._combo(c, "卡片位置", "position", tuple(POSITIONS))
        custom = ttk.Frame(c)
        custom.pack(fill="x", pady=5)
        custom.columnconfigure((0, 1), weight=1)
        self._grid_entry(custom, "自定义 X（像素）", "custom_x", 0)
        self._grid_entry(custom, "自定义 Y（像素）", "custom_y", 1)
        self._section(c, "05  导出成片")
        self._combo(c, "文件格式", "format", FORMATS)
        ttk.Label(c, textvariable=self.format_note, style="Muted.TLabel", wraplength=290).pack(anchor="w", pady=(5, 10))
        self.export_button = ttk.Button(c, text="导出视频 / 序列帧  →", command=self.start_export, style="Accent.TButton")
        self.export_button.pack(fill="x")
        right = ttk.Frame(body, style="Panel.TFrame", padding=18)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        title = ttk.Frame(right)
        title.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(title, text="实时预览", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Label(title, text="棋盘格表示透明区域", style="Muted.TLabel").pack(side="right")
        self.preview_canvas = tk.Canvas(right, bg="#090d14", highlightthickness=0, width=640, height=360)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._preview_resized)
        transport = ttk.Frame(right)
        transport.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        self.play_button = ttk.Button(transport, text="▶  播放", command=self.toggle_play)
        self.play_button.pack(side="left")
        ttk.Button(transport, text="↺", width=3, command=self._rewind).pack(side="left", padx=(7, 12))
        ttk.Label(transport, textvariable=self.time_label, style="Muted.TLabel").pack(side="right")
        self.scrubber = ttk.Scale(right, from_=0, to=1, variable=self.timeline, command=self._scrub)
        self.scrubber.grid(row=3, column=0, sticky="ew", pady=(9, 7))
        self.scrubber.bind("<ButtonPress-1>", lambda _e: self._pause())
        ttk.Label(right, textvariable=self.playback_label, style="Muted.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Label(right, text="空格播放 / 暂停  ·  拖动时间轴检查每一帧", style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(6, 0))
        bottom = ttk.Frame(self, style="Root.TFrame", padding=(24, 12, 24, 16))
        bottom.pack(fill="x")
        ttk.Progressbar(bottom, variable=self.progress, maximum=1).pack(fill="x", pady=(0, 9))
        self.cancel_button = ttk.Button(bottom, text="取消", command=self.cancel_operation, state="disabled")
        self.cancel_button.pack(side="right")
        self.quick_export_button = ttk.Button(bottom, text="导出成片  →", command=self.start_export, style="Accent.TButton")
        self.quick_export_button.pack(side="right", padx=(8, 8))
        ttk.Label(bottom, textvariable=self.status, background=BG, foreground=MUTED, wraplength=650).pack(side="left")
        self._update_format_note()

    @staticmethod
    def _section(parent, text):
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", pady=(17, 4))

    @staticmethod
    def _label(parent, text):
        ttk.Label(parent, text=text, style="Muted.TLabel").pack(anchor="w", pady=(6, 3))

    def _combo(self, parent, label, key, values):
        self._label(parent, label)
        widget = ttk.Combobox(parent, textvariable=self.vars[key], values=values, state="readonly")
        widget.pack(fill="x", pady=(0, 4))
        return widget

    def _grid_entry(self, parent, label, key, column):
        cell = ttk.Frame(parent)
        cell.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 5 if column == 0 else 0))
        self._label(cell, label)
        ttk.Entry(cell, textvariable=self.vars[key], width=12).pack(fill="x")

    def _protect_settings_mousewheel(self):
        # Widget/class defaults run before bind_all: stop the wheel BEFORE
        # Combobox/Spinbox bindings can change the selected value.
        tag = f"SettingsWheel:{self.controls}"
        for sequence in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_class(tag, sequence, self._settings_mousewheel)
        pending = [self.settings_canvas]
        while pending:
            widget = pending.pop()
            widget.bindtags((tag,) + widget.bindtags())
            pending.extend(widget.winfo_children())

    def _settings_mousewheel(self, event):
        if not self._closing:
            button = getattr(event, "num", None)
            delta = getattr(event, "delta", 0)
            if button in (4, 5):
                units = -1 if button == 4 else 1
            elif delta:
                units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            else:
                units = 0
            if units:
                self.settings_canvas.yview_scroll(units, "units")
        return "break"

    def _mousewheel(self, event):
        if self._closing:
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == self.settings_canvas:
                return self._settings_mousewheel(event)
            widget = getattr(widget, "master", None)

    def _key_for(self, key, labels):
        for item, label in labels.items():
            if label == self.vars[key].get():
                return item
        raise ValueError("请选择有效的车手 / 车队预设。")

    def _driver_changed(self):
        driver = presets.DRIVERS[self._key_for("driver", self.driver_labels)]
        self._loading = True
        self.vars["name"].set(str(driver["name"]))
        self.vars["number"].set(str(driver["number"]))
        self.vars["team"].set(self.team_labels[driver["team"]])
        self._set_team_defaults()
        self._loading = False
        self._schedule_refresh()

    def _set_team_defaults(self):
        team = presets.TEAMS[self._key_for("team", self.team_labels)]
        self.vars["color"].set(str(team["color"]))
        self.vars["logo_variant"].set("彩色队标" if team.get("logo_variant") == "color" else "白色队标")

    def _team_changed(self):
        self._loading = True
        self._set_team_defaults()
        self._loading = False
        self._schedule_refresh()

    def _restore_team_color(self):
        self.vars["color"].set(str(presets.TEAMS[self._key_for("team", self.team_labels)]["color"]))

    def _choose_color(self, key):
        initial = self.vars[key].get()
        try:
            ImageColor.getrgb(initial)
        except ValueError:
            initial = "#10121a"
        chosen = colorchooser.askcolor(initialcolor=initial, parent=self.root, title="选择颜色")[1]
        if chosen:
            self.vars[key].set(chosen)

    def _upload_logo(self):
        path = filedialog.askopenfilename(parent=self.root, title="选择队标图片", filetypes=[("图片", "*.png *.webp *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*")])
        if path:
            try:
                with Image.open(path) as image:
                    image.verify()
                self.vars["logo_path"].set(path)
                self.vars["logo_variant"].set("上传图片")
            except Exception as exc:
                self._error("无法读取图片", exc)

    def _value_changed(self, key):
        if self._loading or self._closing:
            return
        if key == "format":
            self._update_format_note()
        else:
            if self._playing:
                self._pause()
            self._schedule_refresh()

    def _update_format_note(self):
        fmt = self.vars["format"].get()
        if fmt in ("MOV", "WEBM", "ZIP"):
            text = "支持 Alpha 透明通道。选择透明背景可用于剪辑叠加。"
            if fmt == "ZIP":
                text += " ZIP 内为逐帧 PNG，并附带音轨。"
        elif fmt == "GIF":
            text = "GIF 支持二值透明（无平滑淡出），最多 256 色，不含音轨。"
        else:
            text = "此格式以背景色合成画面；透明背景将使用所选背景色。"
        self.format_note.set(text)

    def _schedule_refresh(self):
        if self._closing:
            return
        if self._render_after:
            self.root.after_cancel(self._render_after)
        self._render_after = self.root.after(140, self._refresh_config)

    def build_config(self):
        values = {key: value.get() for key, value in self.vars.items()}
        width, height = (int(x.strip()) for x in values["resolution"].replace("×", "x").split("x"))
        logo = None
        if values["logo_variant"] == "上传图片":
            if not values["logo_path"].strip():
                raise ValueError("请上传队标图片，或选择车队队标。")
            logo = str(Path(values["logo_path"]).expanduser().resolve())
            if not Path(logo).is_file():
                raise ValueError("队标图片不存在，请重新选择。")
        numeric = {key: float(values[key]) for key in NUMERIC}
        if not all(math.isfinite(value) for value in numeric.values()):
            raise ValueError("动画参数必须是有限数字。")
        config = renderer.RenderConfig(
            driver=self._key_for("driver", self.driver_labels), name=values["name"], number=values["number"],
            team=self._key_for("team", self.team_labels), color=values["color"], logo_path=logo,
            logo_variant="color" if values["logo_variant"] == "彩色队标" else "white",
            width=width, height=height, fps=int(values["fps"]),
            background="transparent" if values["background"] == "透明" else "color",
            background_color=values["background_color"], position=POSITIONS[values["position"]],
            custom_x=int(values["custom_x"]), custom_y=int(values["custom_y"]), **numeric)
        config.validate()
        return config

    def _refresh_config(self):
        if self._render_after:
            self.root.after_cancel(self._render_after)
        self._render_after = None
        if self._closing:
            return
        try:
            config = self.build_config()
            card = renderer.CardRenderer(config)
            self.config, self._card = config, card
            self.color_swatch.configure(bg=self.vars["color"].get())
            self._last_error = ""
            self.scrubber.configure(to=max(self.total_duration, .01))
            self.timeline.set(min(self.timeline.get(), self.total_duration))
            self._render_preview()
            if (self.analyzer is not None and not self._analyzing and not self._exporting
                    and self._analyzer_settings != (config.fps, config.gain)):
                self.load_audio(self.audio_path, analysis_only=True)
        except Exception as exc:
            self._last_error = str(exc)
            self.status.set(f"请检查设置：{exc}")

    @property
    def audio_start(self):
        return self.config.start_delay + self.config.entrance if self.config else renderer.RenderConfig().entrance

    @property
    def total_duration(self):
        if not self.config:
            return 1.2
        duration = self.audio_duration if self.analyzer is not None else 3.0
        return self.audio_start + duration + self.config.hold + self.config.fade_out

    @staticmethod
    def _time_text(seconds):
        minutes, seconds = divmod(max(0, seconds), 60)
        hours, minutes = divmod(int(minutes), 60)
        return (f"{hours:02}:" if hours else "") + f"{minutes:02}:{seconds:05.2f}"

    def _render_preview(self):
        if self._closing or self._card is None:
            return
        t = float(self.timeline.get())
        self.time_label.set(f"{self._time_text(t)} / {self._time_text(self.total_duration)}")
        try:
            relative = t - self.audio_start
            if self.analyzer is not None and 0 <= relative < self.audio_duration:
                levels = np.asarray(self.analyzer.levels_at(relative))
            else:
                levels = np.zeros(9, dtype=np.float32)
            duration = self.audio_duration if self.analyzer is not None else 3.0
            frame = self._card.frame(t, self.audio_start, duration, levels).convert("RGBA")
            cw, ch = max(30, self.preview_canvas.winfo_width()), max(30, self.preview_canvas.winfo_height())
            scale = min((cw - 20) / frame.width, (ch - 20) / frame.height)
            size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
            frame = frame.resize(size, Image.Resampling.LANCZOS)
            checker = Image.new("RGBA", size, "#242b37")
            draw = ImageDraw.Draw(checker)
            for y in range(0, size[1], 16):
                for x in range(0, size[0], 16):
                    if (x // 16 + y // 16) % 2:
                        draw.rectangle((x, y, x + 15, y + 15), fill="#303947")
            self._photo = ImageTk.PhotoImage(Image.alpha_composite(checker, frame), master=self.root)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(cw / 2, ch / 2, image=self._photo)
        except Exception as exc:
            self.status.set(f"预览失败：{exc}")
            self._pause()

    def _preview_resized(self, _event):
        if self._resize_after:
            self.root.after_cancel(self._resize_after)
        self._resize_after = self.root.after(100, self._resize_preview)

    def _resize_preview(self):
        self._resize_after = None
        self._render_preview()

    def _scrub(self, value):
        if not self._playing:
            self.timeline.set(float(value))
            self._render_preview()

    def _space(self, event):
        if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox, ttk.Spinbox, tk.Text)):
            return
        self.toggle_play()
        return "break"

    def toggle_play(self):
        if self._playing:
            self._pause()
            return
        self._refresh_config()
        if self._last_error:
            return
        if self.timeline.get() >= self.total_duration - .02:
            self.timeline.set(0)
        self._playing, self._audio_started = True, False
        self._play_generation += 1
        self._clock_origin = time.monotonic() - self.timeline.get()
        self.play_button.configure(text="Ⅱ  暂停")
        self._tick()

    def _tick(self):
        self._play_after = None
        if self._closing or not self._playing:
            return
        t = min(time.monotonic() - self._clock_origin, self.total_duration)
        self.timeline.set(t)
        if t >= self.audio_start and not self._audio_started:
            self._audio_started = True
            self._begin_audio(max(0, t - self.audio_start))
        if t >= self.audio_start + self.audio_duration and self.analyzer is not None:
            self._stop_sound()
        self._render_preview()
        if t >= self.total_duration:
            self._pause()
        elif self._playing:
            self._play_after = self.root.after(max(15, round(1000 / min(self.config.fps, 30))), self._tick)

    def _pause(self):
        self._playing = False
        self._play_generation += 1
        if self._play_after:
            self.root.after_cancel(self._play_after)
            self._play_after = None
        self._stop_sound()
        if hasattr(self, "play_button"):
            self.play_button.configure(text="▶  播放")

    def _rewind(self):
        self._pause()
        self.timeline.set(0)
        self._render_preview()

    def _stop_sound(self):
        if self._winsound:
            try:
                self._winsound.PlaySound(None, 0)
            except RuntimeError:
                pass

    def _begin_audio(self, seconds):
        if not self._winsound or not self._wav_path or seconds >= self.audio_duration:
            return
        generation, source = self._play_generation, self._wav_path
        target = self._temp_dir / f"seek-{generation}.wav"
        def work():
            try:
                with wave.open(str(source), "rb") as wav:
                    wav.setpos(min(wav.getnframes(), int(seconds * wav.getframerate())))
                    with wave.open(str(target), "wb") as output:
                        output.setparams(wav.getparams())
                        while not self._closing and generation == self._play_generation:
                            chunk = wav.readframes(65536)
                            if not chunk:
                                break
                            output.writeframes(chunk)
                self.events.put(("sound_ready", generation, target, seconds))
            except Exception as exc:
                self.events.put(("sound_failed", generation, str(exc)))
        self._spawn(work)

    def _spawn(self, function):
        def run():
            try:
                function()
            finally:
                self.events.put(("worker_done", threading.current_thread()))
        thread = threading.Thread(target=run, daemon=True, name="teamradio-worker")
        self._workers.add(thread)
        thread.start()

    def select_audio(self):
        path = filedialog.askopenfilename(parent=self.root, title="选择音频文件", filetypes=[("音频文件", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.aif *.aiff *.wma *.mp4 *.mkv *.webm"), ("所有文件", "*.*")])
        if path:
            self.load_audio(path)

    def load_audio(self, path, analysis_only=False):
        """Asynchronously load arbitrary-duration audio without changing Tk in workers."""
        if self._exporting or self._closing:
            return
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            self._error("音频不存在", FileNotFoundError(str(path)))
            return
        try:
            config = self.build_config()
        except Exception as exc:
            self._error("请先修正设置", exc)
            return
        settings = (config.fps, config.gain)
        existing_wav = self._wav_path if self.audio_path == path else None
        self._pause()
        self._analyze_cancel.set()
        self._analyze_cancel = threading.Event()
        cancel = self._analyze_cancel
        self._analysis_generation += 1
        generation = self._analysis_generation
        self._analyzing = True
        self.audio_label.set(path.name)
        self.audio_detail.set("正在分析完整音频，请稍候…")
        self.status.set("正在分析音频并准备预览…")
        self.progress.set(0)
        self._set_busy()
        def work():
            analyzer = None
            try:
                analyzer = media.AudioAnalyzer(path, fps=settings[0], gain=settings[1], cancel=cancel)
                if cancel.is_set():
                    raise media.CancelledError()
                wav = existing_wav if existing_wav and existing_wav.is_file() else self._decode_preview_wav(path, generation, cancel)
                if cancel.is_set():
                    raise media.CancelledError()
                if self._closing:
                    return
                self.events.put(("audio_ready", generation, path, analyzer, wav, settings, analysis_only))
                analyzer = None
            except media.CancelledError:
                self.events.put(("audio_cancelled", generation))
            except Exception as exc:
                self.events.put(("audio_failed", generation, str(exc)))
            finally:
                if analyzer is not None:
                    analyzer.close()
        self._spawn(work)

    def _decode_preview_wav(self, path, generation, cancel):
        if not self._winsound:
            return None
        target = self._temp_dir / f"audio-{generation}.wav"
        try:
            executable = getattr(media, "ffmpeg_exe", None)
            executable = executable() if callable(executable) else executable
            executable = executable or shutil.which("ffmpeg")
            if not executable:
                return None
            command = [str(executable), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(path),
                       "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(target)]
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=errors, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                while process.poll() is None:
                    if cancel.wait(.08) or self._closing:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        return None
                if process.returncode == 0 and target.is_file():
                    return target
        except Exception:
            pass
        return None

    def _set_busy(self):
        busy = self._exporting or self._analyzing
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.audio_button.configure(state="disabled" if self._exporting else "normal")
        state = "disabled" if busy or self.analyzer is None else "normal"
        self.export_button.configure(state=state)
        self.quick_export_button.configure(state=state)

    def start_export(self):
        if self._exporting or self._analyzing:
            return
        if self.audio_path is None or self.analyzer is None:
            messagebox.showinfo("请先选择音频", "选择音频并等待分析完成后即可导出。", parent=self.root)
            return
        try:
            config = self.build_config()
            fmt = self.vars["format"].get().lower()
            path = filedialog.asksaveasfilename(parent=self.root, title="导出动画", defaultextension=f".{fmt}",
                                              initialfile=f"{self.audio_path.stem}_teamradio.{fmt}",
                                              filetypes=[(f"{fmt.upper()} 文件", f"*.{fmt}")])
            if path:
                self.export_to(path, config)
        except Exception as exc:
            self._error("无法开始导出", exc)

    def export_to(self, path, config=None):
        """Export a settings snapshot; also usable from scripted lifecycle tests."""
        if self._exporting or self._analyzing or self._closing:
            return
        if self.audio_path is None:
            raise ValueError("请先选择音频。")
        config = config or self.build_config()
        config.validate()
        destination = Path(path).expanduser().resolve()
        if destination.suffix.lower().lstrip(".") not in {f.lower() for f in FORMATS}:
            raise ValueError("不支持的导出格式。")
        self._pause()
        self._export_cancel = threading.Event()
        cancel, audio_path = self._export_cancel, self.audio_path
        self._exporting = True
        self.progress.set(0)
        self.status.set("正在准备导出…")
        self._set_busy()
        def progress(fraction, message):
            self.events.put(("export_progress", float(fraction), str(message)))
        def work():
            try:
                result = media.export_video(audio_path, destination, config, progress=progress, cancel=cancel)
                self.events.put(("export_ready", Path(result)))
            except media.CancelledError:
                self.events.put(("export_cancelled",))
            except Exception as exc:
                self.events.put(("export_failed", str(exc)))
        self._spawn(work)

    def cancel_operation(self):
        self._analyze_cancel.set()
        self._export_cancel.set()
        self.status.set("正在取消，请稍候…")
        self.cancel_button.configure(state="disabled")

    def save_config(self):
        try:
            config = self.build_config()
            path = filedialog.asksaveasfilename(parent=self.root, title="保存配置", defaultextension=".json",
                                              initialfile="teamradio_config.json", filetypes=[("JSON 配置", "*.json")])
            if path:
                self.write_config(path, config)
                self.status.set(f"配置已保存：{Path(path).name}")
        except Exception as exc:
            self._error("无法保存配置", exc)

    def write_config(self, path, config=None):
        data = asdict(config or self.build_config())
        data["_gui"] = {"format": self.vars["format"].get(), "audio_path": str(self.audio_path) if self.audio_path else None}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_config(self):
        path = filedialog.askopenfilename(parent=self.root, title="载入配置", filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")])
        if path:
            try:
                self.read_config(path)
                self.status.set(f"配置已载入：{Path(path).name}")
            except Exception as exc:
                self._error("无法载入配置", exc)

    def read_config(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("JSON 配置必须是一个对象。")
        allowed = {field.name for field in fields(renderer.RenderConfig)}
        if data.get("logo_path") and not Path(data["logo_path"]).is_absolute():
            data["logo_path"] = str((Path(path).resolve().parent / data["logo_path"]).resolve())
        config = renderer.RenderConfig(**{key: value for key, value in data.items() if key in allowed})
        config.validate()
        team = config.team or presets.DRIVERS[config.driver]["team"]
        resolution = f"{config.width} × {config.height}"
        if resolution not in RESOLUTIONS:
            raise ValueError("请选择界面支持的四种分辨率之一。")
        if config.fps not in (24, 25, 30, 50, 60):
            raise ValueError("请选择界面支持的帧率：24 / 25 / 30 / 50 / 60。")
        updates = {"driver": self.driver_labels[config.driver], "team": self.team_labels[team],
                   "name": config.name if config.name is not None else presets.DRIVERS[config.driver]["name"],
                   "number": config.number if config.number is not None else presets.DRIVERS[config.driver]["number"],
                   "color": config.color or presets.TEAMS[team]["color"], "logo_path": str(config.logo_path or ""),
                   "logo_variant": "上传图片" if config.logo_path else ("彩色队标" if (config.logo_variant or presets.TEAMS[team].get("logo_variant")) == "color" else "白色队标"),
                   "resolution": resolution, "background": "透明" if config.background == "transparent" else "纯色",
                   "position": next(key for key, value in POSITIONS.items() if value == config.position)}
        for key in NUMERIC + ("fps", "custom_x", "custom_y", "background_color"):
            updates[key] = getattr(config, key)
        gui = data.get("_gui", {})
        if not isinstance(gui, dict):
            gui = {}
        if gui.get("format") in FORMATS:
            updates["format"] = gui["format"]
        self._pause()
        self._loading = True
        try:
            for key, value in updates.items():
                self.vars[key].set(str(value))
        finally:
            self._loading = False
        self._update_format_note()
        self._refresh_config()
        if self._last_error:
            raise ValueError(self._last_error)
        audio = gui.get("audio_path")
        if audio and Path(audio).is_file() and not self._exporting:
            self.load_audio(audio)

    def _poll(self):
        self._poll_after = None
        if self._closed:
            return
        for _ in range(200):
            try:
                kind, *args = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "worker_done":
                self._workers.discard(args[0])
                continue
            if self._closing:
                if kind == "audio_ready":
                    args[2].close()
                continue
            if kind.startswith("audio_"):
                if args[0] != self._analysis_generation:
                    if kind == "audio_ready":
                        args[2].close()
                    continue
                self._analyzing = False
                if kind == "audio_ready":
                    _, path, analyzer, wav, settings, analysis_only = args
                    self._analyzer_settings = settings
                    if self.analyzer is not None:
                        self.analyzer.close()
                    self.analyzer, self.audio_path = analyzer, path
                    self.audio_duration, self._wav_path = float(analyzer.duration), wav
                    self.audio_label.set(path.name)
                    self.audio_detail.set(f"完整时长 {self._time_text(self.audio_duration)} · 已完成音频分析")
                    self.playback_label.set("有声预览 · Windows 音频播放" if wav and self._winsound else "静音预览 · 当前环境无法播放音频；导出保留音轨")
                    self.status.set("音频就绪。可编辑样式、拖动预览或导出。")
                    self.progress.set(0)
                    if not analysis_only:
                        self.timeline.set(min(self.audio_start + .25, self.total_duration))
                    self._refresh_config()
                elif kind == "audio_cancelled":
                    self.audio_label.set(self.audio_path.name if self.audio_path else "尚未选择音频")
                    self.audio_detail.set("已取消本次分析。")
                    self.status.set("音频分析已取消。")
                elif kind == "audio_failed":
                    self.audio_label.set(self.audio_path.name if self.audio_path else "尚未选择音频")
                    self.audio_detail.set("音频读取失败，请重新选择。")
                    self._error("音频分析失败", args[1])
                self._set_busy()
            elif kind == "export_progress":
                self.progress.set(max(0, min(1, args[0])))
                message = args[1]
                translations = {"Analyzing audio": "正在分析音频…", "Rendering frames": "正在渲染画面…",
                                "Preparing delayed lossless soundtrack": "正在准备完整音轨…",
                                "Building GIF palette": "正在生成 GIF 调色板…", "Encoding GIF": "正在编码 GIF…",
                                "Finalizing export": "正在完成导出…"}
                if message.startswith("Rendering frame "):
                    message = "正在渲染帧 " + message[len("Rendering frame "):]
                self.status.set(translations.get(message, message) or "正在导出…")
            elif kind in ("export_ready", "export_cancelled", "export_failed"):
                self._exporting = False
                self._set_busy()
                if kind == "export_ready":
                    self.progress.set(1)
                    self.status.set(f"导出完成：{args[0]}")
                    messagebox.showinfo("导出完成", f"文件已保存：\n{args[0]}", parent=self.root)
                elif kind == "export_cancelled":
                    self.progress.set(0)
                    self.status.set("导出已取消。")
                else:
                    self.progress.set(0)
                    self._error("导出失败", args[0])
            elif kind == "sound_ready":
                generation, target, seconds = args
                if self._playing and generation == self._play_generation:
                    try:
                        self._clock_origin = time.monotonic() - self.audio_start - seconds
                        self._winsound.PlaySound(str(target), self._winsound.SND_FILENAME | self._winsound.SND_ASYNC | self._winsound.SND_NODEFAULT)
                        self.playback_label.set("有声预览 · Windows 音频播放")
                    except Exception:
                        self.playback_label.set("静音预览 · 音频播放不可用；导出保留音轨")
            elif kind == "sound_failed" and args[0] == self._play_generation:
                self.playback_label.set("静音预览 · 音频播放不可用；导出保留音轨")
        if self._closing and not self._workers:
            self._finish_close()
        else:
            self._poll_after = self.root.after(50, self._poll)

    def _error(self, title, error):
        self.status.set(f"{title}：{error}")
        messagebox.showerror(title, str(error), parent=self.root)

    def close(self):
        """Cancel workers and drain their results before releasing audio and Tk."""
        if self._closing:
            return
        self._pause()
        self._closing = True
        self._analyze_cancel.set()
        self._export_cancel.set()
        for attr in ("_render_after", "_resize_after"):
            job = getattr(self, attr)
            if job:
                self.root.after_cancel(job)
                setattr(self, attr, None)
        self.status.set("正在释放音频与导出资源…")
        if not self._workers:
            self._finish_close()

    def _finish_close(self):
        if self._closed:
            return
        self._closed = True
        if self._poll_after:
            self.root.after_cancel(self._poll_after)
            self._poll_after = None
        if self.analyzer is not None:
            self.analyzer.close()
            self.analyzer = None
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self.root.destroy()


App = TeamRadioApp


def _enable_high_dpi():
    # Opt in only at explicit launch, never at import time.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    _enable_high_dpi()
    root = tk.Tk()
    try:
        TeamRadioApp(root)
    except Exception as exc:
        messagebox.showerror("无法启动 Team Radio Studio", str(exc), parent=root)
        root.destroy()
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
