"""Install this skill's own small runtime, without modifying other skills."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
from runtime import ROOT, PACKAGES, emit, node, run, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-url', help='Per-run pip mirror; existing pip configuration stays unchanged.')
    parser.add_argument('--npm-registry', default='https://registry.npmjs.org')
    args = parser.parse_args()
    PACKAGES.mkdir(parents=True, exist_ok=True)
    if str(PACKAGES) not in sys.path:
        sys.path.insert(0, str(PACKAGES))
    requirements = {'PIL': 'Pillow>=10,<13', 'playwright': 'playwright>=1.50,<2',
                    'bs4': 'beautifulsoup4>=4.12,<5', 'yaml': 'PyYAML>=6,<7'}
    missing = [value for key, value in requirements.items() if importlib.util.find_spec(key) is None]
    if missing:
        command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--target', PACKAGES]
        if args.index_url:
            command += ['--index-url', args.index_url]
        run(command + missing, timeout=240)
    node_exe = node()
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise RuntimeError('npm is missing from the Node installation.')
    resolved_npm = Path(npm).resolve()
    candidates = ([resolved_npm] if resolved_npm.name == 'npm-cli.js' else []) + [resolved_npm.parent/'node_modules/npm/bin/npm-cli.js',
                  Path(node_exe).resolve().parent/'node_modules/npm/bin/npm-cli.js',
                  Path(npm).resolve().parent.parent/'lib/node_modules/npm/bin/npm-cli.js']
    npm_cli = next((path for path in candidates if path.is_file()), None)
    if not npm_cli:
        raise RuntimeError('Could not locate npm-cli.js next to Node/npm.')
    folder = ROOT/'.runtime/node'
    folder.mkdir(parents=True, exist_ok=True)
    for filename in ('package.json', 'package-lock.json'):
        shutil.copy2(ROOT/'assets/node'/filename, folder/filename)
    run([node_exe, npm_cli, 'ci', '--prefix', folder, '--ignore-scripts', '--no-audit', '--no-fund',
         '--registry', args.npm_registry], timeout=240)
    env = dict(os.environ, PYTHONPATH=str(PACKAGES), PYTHONUTF8='1')
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        run([sys.executable, '-m', 'playwright', 'install', 'chromium', '--only-shell'], env=env, timeout=240)
    save_json(ROOT/'.runtime/runtime.json', {'python': sys.executable, 'packages': str(PACKAGES), 'node': node_exe})
    emit('bootstrap', status='ready', python=sys.executable, node=node_exe, paid_apis_enabled=False)


if __name__ == '__main__':
    main()
