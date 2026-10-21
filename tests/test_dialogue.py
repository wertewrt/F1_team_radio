import math
import random
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from teamradio.dialogue import DialoguePanel, split_quoted_text, validate_messages


def message(text='"OK"', start=0, end=3, speaker='driver'):
    return dict(start=start, end=end, speaker=speaker, text=text)


class DialogueValidationTests(unittest.TestCase):
    def assertChineseError(self, call):
        with self.assertRaisesRegex(ValueError, '[\u4e00-\u9fff]'):
            call()

    def test_normalizes_without_mutating_and_allows_touching_intervals(self):
        original = [message('  "FIRST\r\nSECOND"  ', end=1),
                    message('"COPY"', start=1, end=2, speaker='other')]
        normalized = validate_messages(original)
        self.assertEqual(normalized[0]['text'], '"FIRST\nSECOND"')
        self.assertEqual(normalized[0]['start'], 0.0)
        self.assertIsInstance(normalized[0]['start'], float)
        self.assertEqual(original[0]['text'], '  "FIRST\r\nSECOND"  ')
        normalized[0]['speaker'] = 'other'
        self.assertEqual(original[0]['speaker'], 'driver')
        self.assertEqual(validate_messages([]), [])

    def test_rejects_nonfinite_negative_boolean_or_nonnumeric_times(self):
        for field in ('start', 'end'):
            for value in (float('nan'), float('inf'), -float('inf'), -1, True, '1', None):
                with self.subTest(field=field, value=value):
                    data = message()
                    data[field] = value
                    self.assertChineseError(lambda: validate_messages([data]))
        for data in (message(start=1, end=1), message(start=2, end=1)):
            self.assertChineseError(lambda: validate_messages([data]))

    def test_rejects_unsorted_or_overlapping_messages(self):
        for data in ([message(start=2, end=4), message(start=0, end=1)],
                     [message(end=3), message(start=2.9, end=5)],
                     [message(end=1), message(end=2)]):
            self.assertChineseError(lambda: validate_messages(data))

    def test_schema_and_single_ascii_quote_pair_are_strict(self):
        invalid = (None, {}, (), [None], [{}], [message(speaker='engineer')])
        for data in invalid:
            self.assertChineseError(lambda: validate_messages(data))
        for text in ('NO QUOTES', '"OPEN', 'CLOSE"', '""', '" \n "',
                     '"ONE" "TWO"', '"OUTER "INNER""', '“CURLY”', 42):
            with self.subTest(text=text):
                self.assertChineseError(lambda: validate_messages([message(text)]))

    def test_split_quotes_preserves_messages_and_multiline_text(self):
        self.assertEqual(split_quoted_text(' \n "ONE"\n\n"TWO\nLINES"  '),
                         ['"ONE"', '"TWO\nLINES"'])
        self.assertEqual(split_quoted_text('"ONE""TWO"'), ['"ONE"', '"TWO"'])
        self.assertEqual(split_quoted_text(' \n\t'), [])
        for text in ('prefix "ONE"', '"ONE" trailing', '"ONE" and "TWO"',
                     '"UNCLOSED', '"ONE" "TWO', '""', '"A "B""', None):
            with self.subTest(text=text):
                self.assertChineseError(lambda: split_quoted_text(text))


class DialogueRenderingTests(unittest.TestCase):
    COLOR = (12, 204, 156)

    def panel(self, messages=None, **kwargs):
        return DialoguePanel([message()] if messages is None else messages,
                             self.COLOR, 329, **kwargs)

    def test_empty_and_before_first_start_are_transparent(self):
        empty = self.panel([])
        self.assertEqual(empty.duration, 0)
        self.assertIsNone(empty.frame(100).getbbox())
        self.assertIsNone(empty.state_at(100)['active_index'])
        panel = self.panel([message(start=2, end=4)])
        for t in (-100, 0, 1.999):
            self.assertIsNone(panel.frame(t).getbbox())
            self.assertEqual(panel.state_at(t)['panel_height'], 0)
        self.assertEqual(panel.duration, 4)
        self.assertEqual(panel.state_at(2)['active_index'], 0)

    def test_short_panel_grows_monotonically_to_its_content_height(self):
        panel = self.panel()
        heights = [panel.state_at(t)['panel_height'] for t in (0, .08, .16, .24, .35, 1)]
        self.assertEqual(heights[0], 0)
        self.assertTrue(all(a <= b for a, b in zip(heights, heights[1:])))
        self.assertGreater(heights[1], 0)
        self.assertEqual(heights[-1], 88)
        self.assertLess(heights[-1], panel.max_height)
        frame = panel.frame(1)
        self.assertEqual(frame.mode, 'RGBA')
        self.assertEqual(frame.size, (329, 276))
        alpha = np.asarray(frame)[:, :, 3]
        self.assertTrue(np.all(alpha[:88] == 255))
        self.assertFalse(alpha[88:].any())

    def test_driver_is_team_colored_right_aligned_and_other_is_white_left(self):
        panel = self.panel([message(end=2), message(start=2, end=4, speaker='other')])
        pixels = np.asarray(panel.frame(3)).astype(int)
        driver_y, driver_x = np.where(np.max(np.abs(pixels[:, :, :3] - self.COLOR), axis=2) < 10)
        other_y, other_x = np.where(np.max(np.abs(pixels[:, :, :3] - (255, 255, 255)), axis=2) < 10)
        self.assertGreater(len(driver_x), 50)
        self.assertGreater(len(other_x), 50)
        self.assertGreater(driver_x.mean(), other_x.mean() + 200)
        # Thin quote marks need an ink/background test, not a solid-color test.
        ink = np.max(np.abs(pixels[:, :, :3] - (16, 17, 22)), axis=2) > 30
        self.assertAlmostEqual(np.where(ink[28:60])[1].max(), 316, delta=4)
        self.assertAlmostEqual(np.where(ink[76:108])[1].min(), 12, delta=4)
        self.assertGreater(other_y.min(), driver_y.max())

    def test_reference_alternating_quotes_fit_and_keep_previous_paragraph(self):
        panel = self.panel([
            message('"CHECK THE CAR, I HAD WEIRD BEHAVIOUR LAST CORNER"', end=3),
            message('"OK, COPY. WE\'LL HAVE A LOOK"', start=3, end=5, speaker='other'),
        ])
        first = panel.frame(2)
        second = panel.frame(4)
        self.assertEqual(panel.state_at(2)['paragraph_height'], 128)
        self.assertEqual(panel.state_at(4)['panel_height'], 264)
        self.assertEqual(panel.state_at(4)['scroll_y'], 0)
        self.assertEqual(first.crop((0, 0, 329, 156)).tobytes(),
                         second.crop((0, 0, 329, 156)).tobytes())
        self.assertTrue(panel.state_at(4)['fully_read'])

    def test_overflow_autoscroll_finishes_and_next_message_anchors_at_top(self):
        long_text = '"' + '\n'.join(f'LINE {i:02d}' for i in range(18)) + '"'
        panel = self.panel([message(long_text, start=8, end=17),
                            message('"COPY"', start=17.5, end=22, speaker='other'),
                            message('"THANKS"', start=22, end=25)])
        initial = panel.state_at(8.7)
        middle = panel.state_at(12)
        final = panel.state_at(16.7)
        self.assertEqual(initial['panel_height'], 276)
        self.assertAlmostEqual(initial['scroll_y'], 0)
        self.assertGreater(middle['scroll_y'], initial['scroll_y'])
        self.assertGreater(final['scroll_y'], middle['scroll_y'])
        self.assertTrue(final['fully_read'])
        self.assertAlmostEqual(final['paragraph_top'] + final['paragraph_height'], 248)
        # The last closing quote is actual visible ink, with bottom padding left.
        last_line_y = round(final['paragraph_top'] + final['paragraph_height'] - 32)
        quote_pixels = np.asarray(panel.frame(16.7).crop((305, last_line_y, 318, last_line_y + 32))).astype(int)
        self.assertTrue(np.any(np.max(np.abs(quote_pixels[:, :, :3] - (16, 17, 22)), axis=2) > 30))
        self.assertEqual(panel.state_at(18.49)['scroll_y'], final['scroll_y'])
        entering = panel.state_at(18.7)
        anchored = panel.state_at(19)
        self.assertGreater(entering['scroll_y'], final['scroll_y'])
        self.assertLess(entering['scroll_y'], anchored['scroll_y'])
        self.assertAlmostEqual(anchored['paragraph_top'], 28)
        self.assertEqual(anchored['active_index'], 1)
        # A short reply after the overflow still fits below COPY.
        self.assertAlmostEqual(panel.state_at(23)['paragraph_top'], 76)
        self.assertEqual(panel.state_at(23)['scroll_y'], anchored['scroll_y'])
        for t in (8, 8.1, 10, 16.9, 17.5, 18, 23, 100):
            self.assertLessEqual(panel.state_at(t)['panel_height'], 276)
        # The final viewport persists for the parent's fade-out.
        self.assertEqual(panel.frame(25).tobytes(), panel.frame(100).tobytes())

    def test_accumulated_short_quotes_overflow_to_new_paragraph_top(self):
        panel = self.panel([message(start=i * 2, end=i * 2 + 2,
                                    speaker='other' if i % 2 else 'driver')
                            for i in range(8)])
        self.assertEqual(panel.state_at(6.8)['scroll_y'], 0)
        self.assertEqual(panel.state_at(8.99)['scroll_y'], 0)
        self.assertAlmostEqual(panel.state_at(9.5)['paragraph_top'], 28)
        self.assertEqual(panel.state_at(10.8)['panel_height'], 276)
        for t, top in ((10.8, 76), (12.8, 124), (14.8, 172)):
            self.assertAlmostEqual(panel.state_at(t)['paragraph_top'], top)
            self.assertEqual(panel.state_at(t)['scroll_y'], panel.state_at(9.5)['scroll_y'])

    def test_exact_fit_stays_still_and_one_pixel_overflow_waits(self):
        messages = [message(start=i * 3, end=i * 3 + 3) for i in range(4)]
        for cap in (136, 135):
            with self.subTest(cap=cap):
                panel = self.panel(messages, max_height=cap)
                before = panel.state_at(2.9)['scroll_y']
                if cap == 136:
                    for t in (3, 3.5, 4.5, 5.9):
                        self.assertEqual(panel.state_at(t)['scroll_y'], before)
                    # The third quote overflows; the fourth fits after that scroll.
                    self.assertEqual(panel.state_at(6.99)['scroll_y'], before)
                    self.assertAlmostEqual(panel.state_at(7.5)['paragraph_top'], 28)
                    self.assertEqual(panel.state_at(10.5)['scroll_y'], panel.state_at(7.5)['scroll_y'])
                else:
                    self.assertEqual(panel.state_at(3.99)['scroll_y'], before)
                    self.assertGreater(panel.state_at(4.2)['scroll_y'], before)
                    self.assertAlmostEqual(panel.state_at(4.5)['paragraph_top'], 28)

    def test_configurable_delay_and_zero_duration_scroll(self):
        messages = [message(start=i * 4, end=i * 4 + 4) for i in range(2)]
        for delay in (0, .25, 1, 2):
            for duration in (0, .45):
                with self.subTest(delay=delay, duration=duration):
                    panel = self.panel(messages, max_height=100, scroll_delay=delay, scroll=duration)
                    if delay:
                        self.assertEqual(panel.state_at(4 + delay - .001)['scroll_y'], 0)
                    self.assertGreater(panel.state_at(4 + delay + .1)['scroll_y'], 0)
                    self.assertAlmostEqual(panel.state_at(7.99)['paragraph_top'], 28)
                    # Seeking backwards must restore the full delay, including with instant scroll.
                    self.assertEqual(panel.state_at(3.9)['scroll_y'], 0)
                    self.assertEqual(panel.state_at(4 + max(0, delay - .001))['scroll_y'],
                                     48 if delay == 0 and duration == 0 else 0)

    def test_quote_is_one_sentence_despite_punctuation_and_line_breaks(self):
        messages = [message('"First. Second?\nThird!"', end=4),
                    message('"COPY"', start=4, end=8),
                    message('"OK"', start=8, end=12)]
        panel = self.panel(messages, max_height=150)
        self.assertEqual(len(panel._paragraphs), 3)
        self.assertEqual(panel.state_at(3)['scroll_y'], 0)
        self.assertEqual(panel.state_at(4.99)['scroll_y'], 0)
        self.assertAlmostEqual(panel.state_at(5.5)['paragraph_top'], 28)
        self.assertAlmostEqual(panel.state_at(9.5)['paragraph_top'], 76)

    def test_scrolled_descenders_do_not_leak_into_top_margin(self):
        for width in (329, 486, 658):
            for ending in ('good.', 'happy.', 'gypqj'):
                with self.subTest(width=width, ending=ending):
                    quote = chr(34)
                    messages = [message(quote + ('ROW' + chr(10)) * 7 + ending + quote, end=4),
                                message(quote + 'NEXT MESSAGE' + quote, start=4, end=7, speaker='other')]
                    panel = DialoguePanel(messages, self.COLOR, width)
                    for t in (4.1, 4.25, 5):
                        state = panel.state_at(t)
                        self.assertGreater(state['scroll_y'], 0)
                        pixels = np.asarray(panel.frame(t))
                        margin = math.ceil(panel.padding_top)
                        expected = np.array([16, 17, 22, 255], dtype=np.uint8)
                        self.assertTrue(np.all(pixels[:margin] == expected))
                    # The active quote still starts at the original 28px inset.
                    self.assertAlmostEqual(panel.state_at(5.5)['paragraph_top'], panel.padding_top)
                    pixels = np.asarray(panel.frame(5.5))
                    body = pixels[margin:round(panel.state_at(5.5)['panel_height']), :, :3]
                    self.assertTrue(np.any(np.max(np.abs(body.astype(int) - (255, 255, 255)), axis=2) < 10))

    def test_random_seeking_is_identical_to_fresh_and_sequential_frames(self):
        panel = self.panel([message('"' + 'LONG MESSAGE ' * 50 + '"', end=6),
                            message('"COPY"', start=7, end=9, speaker='other')])
        times = [-1, 0, .05, .35, .9, 2.8, 5.8, 6.5, 7, 7.2, 7.6, 10]
        expected = {t: (panel.state_at(t), panel.frame(t).tobytes()) for t in times}
        shuffled = times[:]
        random.Random(1729).shuffle(shuffled)
        for t in shuffled:
            self.assertEqual(panel.state_at(t), expected[t][0])
            self.assertEqual(panel.frame(t).tobytes(), expected[t][1])
        copy = panel.frame(2.8)
        copy.putpixel((0, 0), (255, 0, 0, 255))
        self.assertEqual(panel.frame(2.8).tobytes(), expected[2.8][1])

    def test_unicode_long_words_hard_breaks_and_quotes_survive_wrapping(self):
        text = '"' + '这是中文无线电对白测试' * 10 + '\n' + 'ANTIDISESTABLISHMENTARIANISM' * 3 + '\nCAFE\u0301"'
        panel = self.panel([message(text, end=10)])
        lines = [line[1] for line in panel._lines]
        self.assertGreater(len(lines), 10)
        self.assertTrue(lines[0].startswith('"'))
        self.assertTrue(lines[-1].endswith('"'))
        self.assertEqual(''.join(lines), text.replace('\n', ''))
        for _, line, font, _ in panel._lines:
            self.assertLessEqual(font.getlength(line), (329 - 24) * 2)
            self.assertFalse(line.startswith('\u0301'))
        self.assertIsNotNone(panel.frame(5).getbbox())

    def test_long_transcripts_never_allocate_a_page_sized_image(self):
        original_new = Image.new
        with mock.patch('teamradio.dialogue.Image.new', wraps=original_new) as allocate:
            panel = self.panel([message('"' + 'A LONG MESSAGE ' * 2000 + '"', end=30)])
            panel.frame(.5)
            panel.frame(20)
            panel.frame(29.9)
        self.assertGreater(panel.state_at(29.9)['paragraph_height'], 10000)
        for call in allocate.call_args_list:
            width, height = call.args[1]
            self.assertLessEqual(width, 329 * 2)
            self.assertLessEqual(height, 276 * 2)

    def test_scaling_caps_and_zero_or_compressed_animation_durations(self):
        scaled = DialoguePanel([message()], '#0CCC9C', 658, max_height=10000)
        self.assertEqual(scaled.max_height, 552)
        self.assertEqual(scaled.frame(1).size, (658, 552))
        self.assertEqual(scaled.state_at(1)['panel_height'], 176)
        limited = self.panel(max_height=120)
        self.assertEqual(limited.max_height, 120)
        immediate = self.panel(expand=0, scroll=0)
        self.assertEqual(immediate.state_at(0)['panel_height'], 88)
        brief = self.panel([message('"' + 'LONG ' * 100 + '"', end=.02)])
        self.assertFalse(brief.state_at(.019)['fully_read'])
        self.assertEqual(brief.state_at(.019)['scroll_y'], 0)
        self.assertTrue(brief.state_at(.02)['fully_read'])
        self.assertEqual(brief.state_at(.019)['panel_height'], 276)
        compressed = self.panel([message('"' + 'LONG ' * 100 + '"', end=.02)], scroll_delay=0)
        self.assertTrue(compressed.state_at(.019)['fully_read'])

    def test_invalid_panel_options_and_sample_times_raise_value_error(self):
        for kwargs in (dict(expand=float('nan')), dict(scroll=-1), dict(font_size=True),
                       dict(font_size=0), dict(max_height=0), dict(font_size=math.inf),
                       dict(scroll_delay=-1), dict(scroll_delay=True), dict(scroll_delay=math.nan)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.panel(**kwargs)
        for width in (0, 31, True, 329.0):
            with self.assertRaises(ValueError):
                DialoguePanel([], self.COLOR, width)
        for color in ('invalid', (1, 2), (256, 0, 0), (True, 0, 0), None):
            with self.assertRaises(ValueError):
                DialoguePanel([], color, 329)
        panel = self.panel()
        for t in (math.nan, math.inf, -math.inf, True, '1'):
            with self.assertRaises(ValueError):
                panel.state_at(t)


if __name__ == '__main__':
    unittest.main()
