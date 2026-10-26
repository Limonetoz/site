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
from urllib.parse import unquote, urljoin, urlsplit

from verify_jekyll_http import Page, check_local_asset, one

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('build_dir', type=Path)
parser.add_argument('--base-path', default='/site')
args = parser.parse_args()
build_dir = args.build_dir.resolve()
if not (build_dir / 'index.html').is_file():
    parser.error('Build ausente: execute o Jekyll antes dos testes.')
base_parts = args.base_path.strip('/').split('/') if args.base_path.strip('/') else []
if any(part in ('.', '..', '') for part in base_parts):
    parser.error('Prefixo inválido.')
prefix = '/' + '/'.join(base_parts) if base_parts else ''

public_documents = {Path('index.html'), Path('feed.xml'), Path('en/feed.xml'),
                    Path('search.json'), Path('sobre/index.html'), Path('en/index.html'),
                    Path('en/sobre/index.html')}
for language, home_file in (('pt', Path('index.html')),
                            ('en', Path('en/index.html'))):
    if not (build_dir / home_file).is_file():
        parser.error(f'Página inicial ausente: {home_file}')
    home = Page()
    home.feed((build_dir / home_file).read_text(encoding='utf-8'))
    section = [node for node in home.root.find('section') if node.attrs.get('id') == 'posts']
    if len(section) != 1:
        parser.error(f'Listagem de posts ausente: {home_file}')
    base = f'https://example.test{prefix}' + ('/en/' if language == 'en' else '/')
    post_prefix = prefix + ('/en/posts/' if language == 'en' else '/posts/')
    for card in section[0].find('article'):
        headings = [node for node in card.find() if node.tag in ('h2', 'h3', 'h4')]
        if len(headings) != 1:
            parser.error(f'Card de post inválido: {home_file}')
        href = one(headings[0], 'a').attrs.get('href', '')
        url = urlsplit(urljoin(base, href))
        if (url.netloc != 'example.test' or not url.path.startswith(post_prefix)
                or not url.path.endswith('/') or url.query or url.fragment):
            parser.error(f'URL de post inválida: {href}')
        local = unquote(url.path[len(prefix):].lstrip('/'))
        if '..' in Path(local).parts or '\\' in local:
            parser.error(f'URL de post inválida: {href}')
        public_documents.add(Path(local) / 'index.html')

public_documents.update(Path(name) for name in (
    'posts/off-topic/index.html', 'posts/tutorial/index.html',
    'en/posts/off-topic/index.html', 'en/posts/tutorial/index.html'))
asset_types = {'css': '.css', 'js': '.js', 'images': {'.svg', '.png'},
               'fonts': '.woff2'}
public_dirs = {Path('assets')} | {Path('assets') / kind for kind in asset_types}
for document in public_documents:
    public_dirs.update(parent for parent in document.parents if parent != Path('.'))
for path in build_dir.rglob('*'):
    relative = path.relative_to(build_dir)
    path_parts = relative.parts
    allowed = False
    if not path.is_symlink() and not any(part.startswith('.') for part in path_parts):
        if path.is_dir():
            allowed = relative in public_dirs
        elif relative in public_documents:
            allowed = True
        elif len(path_parts) == 3 and path_parts[:1] == ('assets',):
            kind = asset_types.get(path_parts[1])
            allowed = (relative.suffix in kind if isinstance(kind, set)
                       else relative.suffix == kind) if kind else False
            allowed |= relative == Path('assets/fonts/OFL.txt')
    if not allowed:
        parser.error(f'Arquivo privado no build: {relative}')
    if path.is_file() and path_parts[0] == 'assets':
        content_type = mimetypes.guess_type(path.name)[0]
        try:
            check_local_asset(path.as_uri(), content_type, path.read_bytes())
        except (OSError, ValueError) as error:
            parser.error(str(error))
with tempfile.TemporaryDirectory(prefix='jekyll-http-') as temporary:
    root = Path(temporary)
    if base_parts:
        mount = root.joinpath(*base_parts)
        mount.parent.mkdir(parents=True, exist_ok=True)
        mount.symlink_to(build_dir, target_is_directory=True)
    else:
        root = build_dir
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
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
