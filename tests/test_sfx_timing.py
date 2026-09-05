from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from app import ROOT, atempo_filters, sfx_source_duration, write_sfx_track


class SfxTimingTests(unittest.TestCase):
    def test_catalog_duration_is_available(self):
        self.assertAlmostEqual(sfx_source_duration("chime"), 0.54)
        self.assertAlmostEqual(sfx_source_duration("unknown"), 0.30)

    def test_long_stretch_uses_legal_atempo_chain(self):
        source, target = 0.18, 4.0
        chain = atempo_filters(source, target)
        values = [float(item.split("=")[1]) for item in chain]
        self.assertTrue(all(0.5 <= value <= 2.0 for value in values))
        self.assertTrue(math.isclose(math.prod(values), source / target, rel_tol=1e-5))

    def test_shortening_uses_legal_atempo_chain(self):
        source, target = 0.85, 0.08
        values = [float(item.split("=")[1]) for item in atempo_filters(source, target)]
        self.assertTrue(all(0.5 <= value <= 2.0 for value in values))
        self.assertTrue(math.isclose(math.prod(values), source / target, rel_tol=1e-5))

    def test_streamed_track_preserves_time_stretch_and_volume(self):
        sources = {"pop": ROOT / "assets" / "sfx" / "pop.wav"}
        with tempfile.TemporaryDirectory(dir=ROOT / "data" / "temp") as directory:
            root = Path(directory)
            markers = [{"time": 0.75, "type": "pop", "duration": 1.2, "volume": 1.0},
                       {"time": 2.25, "type": "pop", "duration": 1.2, "volume": 0.5},
                       {"time": 0.0, "type": "pop", "enabled": False}]
            output = write_sfx_track(root / "track.f32", 4, markers, sources, 0.5)
            audio = np.fromfile(output, dtype="<f4")
            sr = 44100
            self.assertEqual(len(audio), 4 * sr)
            self.assertEqual(np.max(np.abs(audio[:int(0.75 * sr)])), 0)
            first = audio[int(0.75 * sr):int(0.75 * sr) + sr]
            second = audio[int(2.25 * sr):int(2.25 * sr) + sr]
            self.assertGreater(float(np.max(np.abs(first))), 0.01)
            np.testing.assert_allclose(second, first * 0.5, atol=1e-6)
            self.assertGreater(float(np.max(np.abs(audio[sr:int(1.2 * sr)]))), 0.001)

    def test_streamed_track_sums_overlaps_before_final_limiter(self):
        sources = {"pop": ROOT / "assets" / "sfx" / "pop.wav"}
        with tempfile.TemporaryDirectory(dir=ROOT / "data" / "temp") as directory:
            root = Path(directory)
            marker = {"time": 0.1, "type": "pop", "volume": 2.0}
            one = np.fromfile(write_sfx_track(root / "one.f32", 1, [marker], sources, 1.0), dtype="<f4")
            two = np.fromfile(write_sfx_track(root / "two.f32", 1, [marker, marker], sources, 1.0), dtype="<f4")
            np.testing.assert_allclose(two, one * 2, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
