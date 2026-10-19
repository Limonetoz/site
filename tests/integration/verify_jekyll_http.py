import sys
from urllib.request import urlopen

base = sys.argv[1].rstrip('/')
paths = [
    '/',
    '/posts/2026/10/19/mudanca/',
    '/assets/css/style.css',
    '/assets/images/icon.svg',
]
errors = []
for path in paths:
    try:
        with urlopen(base + path, timeout=10) as response:
            data = response.read()
            assert response.status == 200
        if path.endswith('/'):
            html = data.decode()
            assert '{%' not in html and '{{' not in html, 'Liquid não processado'
            assert not html.startswith('---'), 'Front matter vazou para o HTML'
            assert 'Mudança de opinião sobre uso de agentes' in html, 'Post ausente'
            if path != '/':
                assert 'class="post-entry"' in html, 'Layout ausente'
                assert 'Posso resumir' in html, 'Conteúdo ausente'
        print('PASS', path)
    except Exception as exc:
        errors.append((path, str(exc)))
for path, error in errors:
    print('FAIL', path, error)
sys.exit(bool(errors))
