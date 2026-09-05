"""Check installation without downloading models or processing private media."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-models', action='store_true')
    args = parser.parse_args()
    config = load_config()
    checks = {'python_3_10_to_3_12': (3,10) <= sys.version_info[:2] <= (3,12),
              'ffmpeg': bool(shutil.which('ffmpeg')), 'ffprobe': bool(shutil.which('ffprobe'))}
    for name in ('fastapi', 'uvicorn', 'numpy', 'cv2', 'sherpa_onnx', 'faster_whisper', 'pypinyin'):
        checks[name] = importlib.util.find_spec(name) is not None
    if not args.skip_models:
        for key in ('sensevoice_model', 'sensevoice_tokens', 'silero_vad', 'punctuation_model',
                    'face_model', 'qwen_model', 'llama_cli'):
            checks[key] = Path(config[key]).is_file()
        checks['faster_whisper_model'] = all((Path(config['faster_whisper_model']) / name).is_file()
                                            for name in ('model.bin', 'config.json', 'tokenizer.json'))
    print(json.dumps({'checks': checks, 'ready': all(checks.values()),
                      'exports_dir': config['exports_dir']}, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
