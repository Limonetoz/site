"""Serve an isolated build at its production prefix and run HTTP checks."""

import argparse
import functools
import http.server
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('build_dir', type=Path)
parser.add_argument('--base-path', default='/site')
args = parser.parse_args()
build_dir = args.build_dir.resolve()
if not (build_dir / 'index.html').is_file():
    parser.error('Build ausente: execute o Jekyll antes dos testes.')
parts = args.base_path.strip('/').split('/') if args.base_path.strip('/') else []
if any(part in ('.', '..', '') for part in parts):
    parser.error('Prefixo inválido.')

with tempfile.TemporaryDirectory(prefix='jekyll-http-') as temporary:
    root = Path(temporary)
    if parts:
        mount = root.joinpath(*parts)
        mount.parent.mkdir(parents=True, exist_ok=True)
        mount.symlink_to(build_dir, target_is_directory=True)
    else:
        root = build_dir
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        prefix = '/' + '/'.join(parts) if parts else ''
        base = f'http://127.0.0.1:{server.server_port}{prefix}'
        result = subprocess.run([
            sys.executable,
            str(Path(__file__).with_name('verify_jekyll_http.py')),
            base,
        ], check=False)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    palette = subprocess.run([
        sys.executable,
        str(Path(__file__).with_name('test_crimson_accents.py')),
        str(build_dir),
    ], check=False)
    sys.exit(result.returncode or palette.returncode)
