"""Independent runtime helpers adapted from video-skill; no media dependencies."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / '.runtime/packages'
if PACKAGES.exists():
    sys.path.insert(0, str(PACKAGES))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def emit(event, **data):
    print(json.dumps({'event': event, **data}, ensure_ascii=False), flush=True)


def read_json(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, *, timeout=120, check=True, **kwargs):
    options = dict(capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NO_WINDOW
    options.update(kwargs)
    result = subprocess.run([str(a) for a in args], **options)
    if check and result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {(result.stderr or result.stdout)[-1800:]}')
    return result


def node():
    configured = os.environ.get('BLOG_SKILL_NODE')
    saved = ROOT/'.runtime/runtime.json'
    candidates = [configured]
    if saved.is_file():
        candidates.append(read_json(saved).get('node'))
    candidates += [shutil.which('node'), str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')]
    for found in filter(None, candidates):
        if not Path(found).is_file():
            continue
        version = run([found, '--version']).stdout.strip().lstrip('v').split('.')
        if tuple(map(int, version[:3])) >= (20, 18, 1):
            return found
    raise RuntimeError('Node.js >=20.18.1 is required for HTML rendering. Install it or set BLOG_SKILL_NODE.')


def font_path(bold=False):
    for path in (
        Path('C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold else '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/System/Library/Fonts/PingFang.ttc'),
    ):
        if path.exists():
            return str(path)
    raise RuntimeError('Install Microsoft YaHei, PingFang or Noto Sans CJK before making Chinese images.')
