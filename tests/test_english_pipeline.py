import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'workers'))

from app import BatchRequest, VideoRequest, video_cache_dir
from analyze_worker import classify, rule_analyze
from core import suggest_sound_markers


class EnglishPipelineTests(unittest.TestCase):
    def test_english_keywords_preserve_original_case(self):
        label, _, words, _ = classify('Keeps your skin SOFT with a Long-Lasting scent.')
        self.assertEqual(label, 'benefit')
        self.assertIn('SOFT', words)
        self.assertIn('Long-Lasting', words)
        self.assertEqual(classify('A certified organic formula.')[0], 'selling_point')
        self.assertEqual(classify('Please subscribe and follow me.')[0], 'remove')
        self.assertEqual(classify('The software makes a descent.')[0], 'other')

    def test_english_analysis_keeps_timestamps_and_sound_cues(self):
        source = [{'start': 10, 'end': 15, 'text': 'The price is twelve dollars.'},
                  {'start': 20, 'end': 24, 'text': 'Organic ingredients in every bottle.'},
                  {'start': 30, 'end': 35, 'text': 'Keeps your skin soft and smooth.'}]
        analyzed = rule_analyze({'subtitles': source})['subtitles']
        self.assertEqual([(row['start'],row['end']) for row in analyzed],[(10,15),(20,24),(30,35)])
        markers = suggest_sound_markers(analyzed, 8, video_duration=70)
        self.assertEqual([marker['type'] for marker in markers], ['coin','chime','shine'])

    def test_single_and_batch_default_to_auto_and_cache_by_language(self):
        self.assertEqual(VideoRequest(video='test.mp4').language, 'auto')
        self.assertEqual(BatchRequest(folder='test').language, 'auto')
        with tempfile.NamedTemporaryFile(dir=ROOT/'data/temp', suffix='.mp4') as source:
            video=Path(source.name)
            self.assertNotEqual(video_cache_dir(video,'en'),video_cache_dir(video,'zh'))
            self.assertNotEqual(video_cache_dir(video,'en'),video_cache_dir(video,'auto'))


if __name__=='__main__':
    unittest.main()
