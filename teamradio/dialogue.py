"""Timed, seekable dialogue viewport below the unchanged 329 x 176 radio card.

Times are relative to the audio. Geometry and font_size use source-card pixels;
width scales the complete panel. frame() always returns (width, max_height) RGBA,
with transparent pixels below its current animated height. The caller owns fade.
Only line layout is retained: even a very long transcript uses a viewport-sized
raster. No state depends on the order in which frames are requested.
"""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import math
import numbers
import os
from pathlib import Path
import re
import unicodedata

from PIL import Image, ImageColor, ImageDraw, ImageFont


__all__ = ['DialoguePanel', 'validate_messages', 'split_quoted_text']
_SOURCE_WIDTH = 329
_SOURCE_MAX_HEIGHT = 276
_BACKGROUND = (16, 17, 22, 255)


def _seconds(value, label):
    if (isinstance(value, bool) or not isinstance(value, numbers.Real)
            or not math.isfinite(value) or value < 0):
        raise ValueError(label + '须为不小于 0 的有限秒数')
    return float(value)


def _quoted(text):
    if not isinstance(text, str):
        raise ValueError('对白文字须为字符串')
    text = text.strip().replace('\r\n', '\n').replace('\r', '\n')
    if len(text) < 3 or not text.startswith('"') or not text.endswith('"') or text.count('"') != 2:
        raise ValueError('每条对白须且只能包含一对英文双引号，内部不可再含双引号')
    if not text[1:-1].strip():
        raise ValueError('对白引号内不可为空')
    return text


def validate_messages(messages):
    """Return fresh normalized dictionaries; reject unsorted or overlapping input.

    Adjacent intervals may touch. Explicit newlines inside the single ASCII quote
    pair are retained as hard line breaks; outside whitespace is removed.
    """
    if not isinstance(messages, list):
        raise ValueError('对白须为列表')
    result = []
    previous_end = 0.0
    for index, message in enumerate(messages):
        label = f'第 {index + 1} 条对白：'
        if not isinstance(message, dict):
            raise ValueError(label + '须为包含 start、end、speaker、text 的对象')
        if not {'start', 'end', 'speaker', 'text'} <= message.keys():
            raise ValueError(label + '缺少 start、end、speaker 或 text')
        start = _seconds(message['start'], label + '开始时间')
        end = _seconds(message['end'], label + '结束时间')
        if end <= start:
            raise ValueError(label + '结束时间须大于开始时间')
        if result and start < previous_end:
            raise ValueError(label + '须按开始时间排列，且不可与前一条重叠')
        speaker = message['speaker']
        if speaker not in ('driver', 'other'):
            raise ValueError(label + '说话人须为 driver 或 other')
        try:
            text = _quoted(message['text'])
        except ValueError as exc:
            raise ValueError(label + str(exc)) from exc
        result.append(dict(start=start, end=end, speaker=speaker, text=text))
        previous_end = end
    return result


def split_quoted_text(text):
    """Split GUI text into complete quoted messages, including their quotes.

    Only whitespace may separate quotes. Unbalanced quotes and any unquoted
    prefix, suffix, or intervening content are errors instead of silent loss.
    """
    if not isinstance(text, str):
        raise ValueError('对白文字须为字符串')
    result = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        if text[position] != '"':
            raise ValueError('对白引号外仅可有空白，不可包含未加引号的文字')
        end = text.find('"', position + 1)
        if end < 0:
            raise ValueError('对白英文双引号未成对闭合')
        result.append(_quoted(text[position:end + 1]))
        position = end + 1
    return result


def _clusters(text):
    """Keep combining marks and basic emoji ZWJ sequences with their base."""
    result = []
    for char in text:
        if result and (unicodedata.combining(char) or char in ('\u200d', '\ufe0f')
                       or result[-1].endswith('\u200d')):
            result[-1] += char
        else:
            result.append(char)
    return result


def _wrap(text, font, width):
    """Proportional, word-aware wrapping with long-word/CJK character fallback."""
    lines = []
    for hard_line in text.split('\n'):
        line = ''
        for word in re.findall(r'\S+', hard_line):
            candidate = (line + ' ' + word) if line else word
            if font.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            if font.getlength(word) <= width:
                line = word
                continue
            for cluster in _clusters(word):
                if line and font.getlength(line + cluster) > width:
                    lines.append(line)
                    line = ''
                line += cluster
        lines.append(line)
    return lines


def _font_path(cjk=False, override=None):
    if override is not None:
        if not Path(override).is_file():
            raise ValueError('对白字体文件不存在：' + str(override))
        return str(override)
    assets = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'
    windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    choices = []
    if cjk:
        choices.extend([windows_fonts / 'msyh.ttc', windows_fonts / 'msyh.ttf',
                        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
                        Path('/System/Library/Fonts/PingFang.ttc')])
    choices.extend([assets / 'DejaVuSans.ttf', windows_fonts / 'arial.ttf',
                    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')])
    for path in choices:
        if path.is_file():
            return str(path)
    raise ValueError('找不到常规无衬线对白字体，请提供 font_path')


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _progress(t, start, duration):
    if t < start:
        return 0.0
    return 1.0 if duration == 0 else _smooth((t - start) / duration)


@dataclass(frozen=True)
class _Paragraph:
    top: float
    height: float
    line_end: int


@dataclass(frozen=True)
class _Event:
    start: float
    end: float
    previous_height: float
    height: float
    previous_scroll: float
    anchor: float
    final_scroll: float
    expand_duration: float
    anchor_duration: float
    anchor_start: float
    own_start: float
    own_end: float


class DialoguePanel:
    """Append paragraphs while they fit; scroll each overflowing message from top.

    color accepts an RGB tuple or a Pillow color string. max_height optionally
    lowers the natural round(width * 276 / 329) cap. font_size is in source pixels.
    Overflow waits scroll_delay seconds before moving. Short intervals retain
    that delay up to end time and compress the animation into the remaining time.
    After the last end, the last viewport persists for the caller's fade-out.
    """

    def __init__(self, messages, color, width, expand=.35, scroll=.45, font_size=26,
                 *, max_height=None, font_path=None, scroll_delay=1.0):
        self.messages = validate_messages(messages)
        if isinstance(width, bool) or not isinstance(width, int) or width < 32:
            raise ValueError('对白面板宽度须为不小于 32 的整数像素')
        self.width = width
        self.scale = width / _SOURCE_WIDTH
        natural_height = max(1, round(width * _SOURCE_MAX_HEIGHT / _SOURCE_WIDTH))
        if max_height is None:
            self.max_height = natural_height
        elif isinstance(max_height, bool) or not isinstance(max_height, int) or max_height < 1:
            raise ValueError('对白面板最大高度须为正整数像素')
        else:
            self.max_height = min(max_height, natural_height)
        self.expand = _seconds(expand, '对白展开时间')
        self.scroll = _seconds(scroll, '对白滚动时间')
        self.scroll_delay = _seconds(scroll_delay, '对白滚动前停留时间')
        if (isinstance(font_size, bool) or not isinstance(font_size, numbers.Real)
                or not math.isfinite(font_size) or not 1 <= font_size <= 128):
            raise ValueError('对白字号须为 1–128 内的有限数值')
        self.font_size = float(font_size)
        try:
            rgb = ImageColor.getrgb(color) if isinstance(color, str) else tuple(color)
            if (len(rgb) != 3 or any(isinstance(v, bool) or not isinstance(v, int)
                                    or not 0 <= v <= 255 for v in rgb)):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError('对白车队颜色须为有效 RGB 颜色') from exc
        self.color = rgb
        self.duration = self.messages[-1]['end'] if self.messages else 0.0
        self.padding_x = 12 * self.scale
        self.padding_top = 28 * self.scale
        self.padding_bottom = 28 * self.scale
        self.line_height = self.font_size * (32 / 26) * self.scale
        self.paragraph_gap = 16 * self.scale
        self._paragraphs = []
        self._lines = []
        self._events = []
        self._starts = [m['start'] for m in self.messages]
        fonts = {}
        previous_bottom = self.padding_top - self.paragraph_gap
        previous_height = previous_scroll = 0.0
        for message in self.messages:
            cjk = bool(re.search('[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff]', message['text']))
            path = _font_path(cjk, font_path)
            if path not in fonts:
                fonts[path] = ImageFont.truetype(path, max(1, round(self.font_size * self.scale * 2)))
            font = fonts[path]
            lines = _wrap(message['text'], font, (width - 2 * self.padding_x) * 2)
            top = previous_bottom + self.paragraph_gap
            height = len(lines) * self.line_height
            for index, line in enumerate(lines):
                self._lines.append((top + index * self.line_height, line, font, message['speaker']))
            paragraph = _Paragraph(top, height, len(self._lines))
            self._paragraphs.append(paragraph)
            required_height = top + height + self.padding_bottom
            # Compare the whole quoted paragraph against the *current* viewport,
            # not the cumulative transcript height after an earlier overflow.
            visible_height = required_height - previous_scroll
            target_height = min(self.max_height, max(previous_height, visible_height))
            anchor = (max(previous_scroll, top - self.padding_top)
                      if visible_height > self.max_height else previous_scroll)
            final_scroll = max(anchor, required_height - target_height)
            span = message['end'] - message['start']
            delay = min(self.scroll_delay, span) if final_scroll > previous_scroll else 0.0
            remaining = span - delay
            anchor_start = message['start'] + delay
            expand_duration = min(self.expand, span / 4) if target_height != previous_height else 0.0
            anchor_duration = min(self.scroll, remaining / 4) if anchor != previous_scroll else 0.0
            hold = min(.35, remaining * .15)
            own_start = max(message['start'] + expand_duration,
                            anchor_start + anchor_duration) + hold
            own_end = message['end'] - hold
            self._events.append(_Event(message['start'], message['end'], previous_height,
                                       target_height, previous_scroll, anchor, final_scroll,
                                       expand_duration, anchor_duration, anchor_start, own_start, own_end))
            previous_bottom = top + height
            previous_height = target_height
            previous_scroll = final_scroll
        self._line_tops = [line[0] for line in self._lines]
        self._blank = Image.new('RGBA', (width, self.max_height))

    def state_at(self, audio_t):
        """Return viewport geometry in output pixels, without changing state.

        paragraph_top is the active paragraph's top *in the viewport* (normally
        padding_top after its entry scroll). paragraph_y is its virtual-page top.
        fully_read means its full reveal/automatic scroll has completed, rather
        than that a viewer has necessarily read it. Before the first start,
        active_index is None and panel_height is zero.
        """
        if (isinstance(audio_t, bool) or not isinstance(audio_t, numbers.Real)
                or not math.isfinite(audio_t)):
            raise ValueError('对白采样时间须为有限秒数')
        index = bisect_right(self._starts, audio_t) - 1
        if index < 0:
            return dict(active_index=None, panel_height=0.0, scroll_y=0.0,
                        paragraph_top=0.0, paragraph_y=0.0, paragraph_height=0.0,
                        fully_read=False)
        event = self._events[index]
        paragraph = self._paragraphs[index]
        growth = _progress(audio_t, event.start, event.expand_duration)
        panel_height = event.previous_height + (event.height - event.previous_height) * growth
        entry = _progress(audio_t, event.anchor_start, event.anchor_duration)
        scroll_y = event.previous_scroll + (event.anchor - event.previous_scroll) * entry
        own = _progress(audio_t, event.own_start, event.own_end - event.own_start)
        scroll_y += (event.final_scroll - event.anchor) * own
        fully_read = (growth >= 1 and entry >= 1 and
                      (event.final_scroll <= event.anchor or own >= 1))
        return dict(active_index=index, panel_height=panel_height, scroll_y=scroll_y,
                    paragraph_top=paragraph.top - scroll_y, paragraph_y=paragraph.top,
                    paragraph_height=paragraph.height, fully_read=fully_read)

    def frame(self, audio_t):
        """Render visible lines only, at 2x resolution, with transparency below."""
        state = self.state_at(audio_t)
        index = state['active_index']
        height = min(self.max_height, max(0, round(state['panel_height'])))
        result = self._blank.copy()
        if index is None or height == 0:
            return result
        viewport = Image.new('RGBA', (self.width * 2, height * 2), _BACKGROUND)
        draw = ImageDraw.Draw(viewport)
        offset = state['scroll_y']
        first = bisect_left(self._line_tops, offset - self.line_height)
        last = min(self._paragraphs[index].line_end,
                   bisect_right(self._line_tops, offset + height))
        for top, text, font, speaker in self._lines[first:last]:
            driver = speaker == 'driver'
            x = ((self.width - self.padding_x) * 2 - font.getlength(text)
                 if driver else self.padding_x * 2)
            draw.text((x, (top - offset) * 2), text, font=font,
                      fill=(*self.color, 255) if driver else (255, 255, 255, 255), anchor='lt')
        viewport = viewport.resize((self.width, height), Image.Resampling.LANCZOS)
        if offset > 0:
            # Clip after downsampling so old descenders and antialias fringes
            # cannot leak into the fixed top reading margin while scrolling.
            clip_bottom = min(height, math.ceil(self.padding_top))
            ImageDraw.Draw(viewport).rectangle((0, 0, self.width - 1, clip_bottom - 1), fill=_BACKGROUND)
        result.paste(viewport, (0, 0))
        return result
