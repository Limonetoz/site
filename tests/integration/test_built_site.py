"""Serve an isolated build at its production prefix and run HTTP checks."""

import argparse
import functools
import http.server
import mimetypes
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from verify_jekyll_http import check_local_asset

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('build_dir', type=Path)
parser.add_argument('--base-path', default='/site')
args = parser.parse_args()
build_dir = args.build_dir.resolve()
if not (build_dir / 'index.html').is_file():
    parser.error('Build ausente: execute o Jekyll antes dos testes.')
public_roots = {'assets', 'posts', 'sobre', 'en'}
public_documents = {Path('index.html'), Path('feed.xml'), Path('en/feed.xml')}
asset_types = {'css': '.css', 'js': '.js', 'images': {'.svg', '.png'},
               'fonts': '.woff2'}
for path in build_dir.rglob('*'):
    relative = path.relative_to(build_dir)
    parts = relative.parts
    allowed = False
    if not path.is_symlink() and not any(part.startswith('.') for part in parts):
        if path.is_dir():
            allowed = parts[0] in public_roots
        elif relative in public_documents:
            allowed = True
        elif parts[0] in {'posts', 'sobre', 'en'}:
            allowed = relative.name == 'index.html'
        elif len(parts) == 3 and parts[:1] == ('assets',):
            kind = asset_types.get(parts[1])
            allowed = (relative.suffix in kind if isinstance(kind, set)
                       else relative.suffix == kind) if kind else False
            allowed |= relative == Path('assets/fonts/OFL.txt')
    if not allowed:
        parser.error(f'Arquivo privado no build: {relative}')
    if path.is_file() and parts[0] == 'assets':
        content_type = mimetypes.guess_type(path.name)[0]
        try:
            check_local_asset(path.as_uri(), content_type, path.read_bytes())
        except (OSError, ValueError) as error:
            parser.error(str(error))
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
    sys.exit(result.returncode)
