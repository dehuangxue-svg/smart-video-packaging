from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "workers"))

from asr_worker import (clean_text, subtitles_from_timed_chars, timed_characters_from_sensevoice,
                        timed_characters_from_whisper, whisper_language)
from core import split_subtitle


class TimestampTests(unittest.TestCase):
    def test_real_token_gap_splits_caption(self):
        result = SimpleNamespace(tokens=list("你好世界"), timestamps=[0.0, 0.18, 1.5, 1.68])
        _, chars = timed_characters_from_sensevoice(result, 4.0, 6.0)
        rows = subtitles_from_timed_chars(chars, "你好，世界。", 4.0, 6.0)
        self.assertEqual([row["text"] for row in rows], ["你好，", "世界。"])
        self.assertLess(rows[0]["end"], rows[1]["start"])
        self.assertAlmostEqual(rows[1]["start"], 5.47, places=2)

    def test_timestamp_source_is_recorded(self):
        result = SimpleNamespace(tokens=list("真实时间"), timestamps=[0.1, 0.3, 0.5, 0.7])
        _, chars = timed_characters_from_sensevoice(result, 10.0, 11.0)
        rows = subtitles_from_timed_chars(chars, "真实时间。", 10.0, 11.0)
        self.assertTrue(rows)
        self.assertTrue(all(row["timestamp_source"] == "sensevoice_token" for row in rows))

    def test_english_and_mixed_text_keep_word_spaces(self):
        self.assertEqual(clean_text('<|en|>  Easy  to\nuse. '), 'Easy to use.')
        self.assertEqual(clean_text('这 款产品 contains organic ingredients。'), '这款产品 contains organic ingredients。')

    def test_english_bpe_fragments_never_split_a_word(self):
        tokens = [' This', ' moist', 'ur', 'izer', ' keeps', ' your', ' skin', ' soft', ' and', ' smooth', ' every', ' day']
        result = SimpleNamespace(tokens=tokens, timestamps=[index * 0.45 for index in range(len(tokens))])
        _, chars = timed_characters_from_sensevoice(result, 10, 16)
        rows = subtitles_from_timed_chars(chars, 'This moisturizer keeps your skin soft and smooth every day.', 10, 16)
        combined = ' '.join(row['text'] for row in rows)
        self.assertEqual(combined, 'This moisturizer keeps your skin soft and smooth every day.')
        self.assertGreater(len(rows), 1)
        self.assertTrue(any('moisturizer' in row['text'] for row in rows))
        self.assertTrue(all(10 <= row['start'] < row['end'] <= 16 for row in rows))
        self.assertTrue(all(a['end'] <= b['start'] for a,b in zip(rows,rows[1:])))

    def test_contractions_and_decimals_remain_intact(self):
        result=SimpleNamespace(tokens=[' We', "'re", ' saving', ' 12', '.', '50', ' dollars'], timestamps=[0, .2, .4, 1, 1.1, 1.2, 1.5])
        _, chars=timed_characters_from_sensevoice(result, 0, 2)
        rows=subtitles_from_timed_chars(chars, "We're saving 12.50 dollars.", 0, 2)
        self.assertEqual(' '.join(row['text'] for row in rows), "We're saving 12.50 dollars.")

    def test_auto_fallback_does_not_force_chinese(self):
        self.assertIsNone(whisper_language('auto', 'yue'))
        self.assertIsNone(whisper_language('auto', 'en'))
        self.assertEqual(whisper_language('en'), 'en')
        self.assertEqual(whisper_language('zh'), 'zh')
        self.assertEqual(whisper_language('yue'), 'zh')

    def test_whisper_word_timestamps_keep_spaces_and_source(self):
        segment=SimpleNamespace(text=' It is easy to use.', words=[
            SimpleNamespace(word=word,start=index*.2,end=index*.2+.15)
            for index,word in enumerate([' It',' is',' easy',' to',' use.'])])
        text,tokens,chars=timed_characters_from_whisper([segment],30,32)
        rows=subtitles_from_timed_chars(chars,text,30,32,timestamp_source='whisper_word')
        self.assertEqual(rows[0]['text'],'It is easy to use.')
        self.assertEqual(rows[0]['timestamp_source'],'whisper_word')
        self.assertTrue(30<=rows[0]['start']<rows[0]['end']<=32)

    def test_estimated_fallback_is_labeled_and_does_not_split_words(self):
        rows=subtitles_from_timed_chars([], 'This moisturizer keeps your skin comfortable throughout the morning.',0,1)
        self.assertTrue(all(row['timestamp_source']=='estimated_segment' for row in rows))
        self.assertTrue(all(0<=row['start']<row['end']<=1 for row in rows))
        self.assertEqual(' '.join(row['text'] for row in rows),
                         'This moisturizer keeps your skin comfortable throughout the morning')

    def test_estimated_fallback_keeps_decimals_and_contractions(self):
        text = "This product is easy to use daily and we're saving 12.50 dollars."
        rows = split_subtitle(0, 8, text)
        self.assertEqual(' '.join(row['text'] for row in rows), text.rstrip('.'))
        self.assertTrue(any("we're" in row['text'] for row in rows))
        self.assertTrue(any('12.50' in row['text'] for row in rows))


if __name__ == "__main__":
    unittest.main()
