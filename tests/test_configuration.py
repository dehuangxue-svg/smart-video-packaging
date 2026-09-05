import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core


class ConfigurationTests(unittest.TestCase):
    def test_clean_checkout_uses_relative_defaults_and_partial_local_overrides(self):
        defaults = (core.ROOT / 'config.example.json').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory(dir=core.ROOT / 'data' / 'temp') as directory:
            root = Path(directory)
            (root / 'config.example.json').write_text(defaults, encoding='utf-8')
            with patch.object(core, 'ROOT', root), patch.object(core, 'CONFIG_FILE', root / 'config.json'):
                config = core.load_config()
                self.assertEqual(Path(config['exports_dir']), root / 'outputs')
                self.assertEqual(Path(config['sensevoice_model']), root / 'models/sensevoice/model.int8.onnx')
                self.assertTrue(Path(config['temp_dir']).is_dir())
                (root / 'config.json').write_text(json.dumps({'exports_dir': 'my exports', 'threads': 1}), encoding='utf-8')
                changed = core.load_config()
                self.assertEqual(Path(changed['exports_dir']), root / 'my exports')
                self.assertEqual(changed['threads'], 1)
                self.assertEqual(changed['sensevoice_model'], config['sensevoice_model'])


if __name__ == '__main__':
    unittest.main()
