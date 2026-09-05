from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import product_name_from_filename, sound_marker_target, split_subtitle, suggest_sound_markers, validate_project, write_ass


class CoreTests(unittest.TestCase):
    def test_filename_product(self):
        path = Path("2026.8.27绽家香水油五腔香氛洗衣凝珠-1.mp4")
        self.assertEqual(product_name_from_filename(path), "绽家香水油五腔香氛洗衣凝珠")

    def test_subtitle_times(self):
        rows = split_subtitle(2.0, 8.0, "这款能够持久留香，而且清洁效果也很好。")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["start"], 2.0)
        self.assertEqual(rows[-1]["end"], 8.0)

    def test_rules_and_ass(self):
        project = {
            "settings": {"hook_end": 6, "font_size": 52, "subtitle_x": 25, "subtitle_y": 75},
            "subtitles": [{"start": 0, "end": 6, "text": "持久留香", "label": "benefit", "highlight_words": ["留香"], "selected": True}],
            "visual": {"samples": [{"time": 1, "host_visible": True}]},
        }
        issues = validate_project(project, {"duration": 70})
        self.assertFalse(any(x["level"] == "error" for x in issues))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sub.ass"
            write_ass(project, target, 1080, 1920)
            text = target.read_text(encoding="utf-8-sig")
            self.assertIn("持久", text)
            self.assertIn("\\c&H", text)
            self.assertIn("\\pos(270,1440)", text)

    def test_sound_markers_are_spaced_and_after_hook(self):
        rows = [
            {"start": 5, "label": "selling_point", "selected": True},
            {"start": 12, "label": "benefit", "selected": True, "highlight_words": ["留香"]},
            {"start": 14, "label": "selling_point", "selected": True},
            {"start": 21, "end": 26, "label": "selling_point", "selected": True},
        ]
        markers = suggest_sound_markers(rows, 8)
        self.assertEqual([item["time"] for item in markers], [12.0, 21.0])
        self.assertEqual([item["type"] for item in markers], ["ding", "chime"])
        self.assertEqual([item["volume"] for item in markers], [1.0, 1.0])

    def test_sound_marker_density_follows_video_length(self):
        def rows(duration):
            return [
                {"start": second, "end": min(second + 2, duration), "text": f"这款产品真的很好用{second}",
                 "label": "benefit", "selected": True}
                for second in range(10, duration, 4)
            ]

        self.assertEqual(len(suggest_sound_markers(rows(70), 8)), 10)
        self.assertEqual(len(suggest_sound_markers(rows(90), 8)), 12)
        self.assertEqual(len(suggest_sound_markers(rows(115), 8)), 14)

    def test_sound_targets_extend_to_long_videos(self):
        for duration, expected in [(0, 0), (30, 5), (60, 10), (75, 10), (75.1, 12),
                                   (100, 12), (100.1, 14), (120, 14), (121, 15),
                                   (180, 21), (300, 35), (600, 70), (1800, 210), (3600, 420)]:
            with self.subTest(duration=duration):
                self.assertEqual(sound_marker_target(duration), expected)

    def test_long_video_markers_reach_the_end_and_stay_spaced(self):
        rows = [{"start": t, "end": t + 2, "text": "产品功效非常好", "label": "benefit"}
                for t in range(10, 1800, 3)]
        markers = suggest_sound_markers(rows, 8, video_duration=1800)
        self.assertEqual(len(markers), 210)
        self.assertLess(markers[0]["time"], 20)
        self.assertGreater(markers[-1]["time"], 1790)
        self.assertTrue(all(b["time"] - a["time"] >= 4 for a, b in zip(markers, markers[1:])))
        for start in range(0, 1800, 300):
            self.assertGreaterEqual(sum(start <= m["time"] < start + 300 for m in markers), 30)

    def test_sparse_video_does_not_invent_sound_positions(self):
        rows = [{"start": 10, "end": 14, "text": "产品真的非常好用", "label": "benefit"},
                {"start": 30, "end": 34, "text": "这段内容不使用", "label": "remove"}]
        self.assertEqual(len(suggest_sound_markers(rows, 8, video_duration=1800)), 1)
        self.assertEqual(suggest_sound_markers(rows, 8, max_markers=0), [])

    def test_long_video_can_pass_export_validation(self):
        project = {"settings": {"hook_end": 8}, "subtitles": [
            {"start": 0, "end": 8, "text": "产品能够持久留香", "label": "benefit"},
            {"start": 1795, "end": 1799, "text": "介绍到这里结束。", "label": "other"},
        ]}
        self.assertFalse(any(item["level"] == "error" for item in validate_project(project, {"duration": 1800})))


if __name__ == "__main__":
    unittest.main()
