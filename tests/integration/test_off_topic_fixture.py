"""Build isolated blog fixtures; assert category filtering and empty state at / and /site."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from verify_jekyll_http import Page, one, post_art_by_title

SITE = Path(__file__).resolve().parents[2]
TOPIC = 'Fixture off-topic exclusiva'
OTHER = 'Fixture fora da categoria exclusiva'
TUTORIAL = 'Fixture tutorial exclusiva'
ANOTHER_TUTORIAL = 'Fixture segundo tutorial'
EN_TOPIC = 'English off-topic fixture'
EN_OTHER = 'English uncategorized fixture'
EN_TUTORIAL = 'English tutorial fixture'
EN_ANOTHER_TUTORIAL = 'English second tutorial fixture'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def png_chunk(kind, payload):
    return (len(payload).to_bytes(4, 'big') + kind + payload
            + zlib.crc32(kind + payload).to_bytes(4, 'big'))


def parse(path):
    page = Page()
    page.feed(path.read_text(encoding='utf-8'))
    return page


def cards(page, section=None):
    container = one(page.root, 'main')
    if section:
        matches = [node for node in container.find('section') if node.attrs.get('id') == section]
        if len(matches) != 1:
            raise AssertionError(f'Seção #{section} ausente')
        container = matches[0]
    result = {}
    for card in container.find('article'):
        headings = [node for node in card.find() if node.tag in ('h2', 'h3', 'h4')]
        if not headings:
            continue
        link = one(headings[0], 'a')
        result[headings[0].text()] = link.attrs['href']
    return result


def generated_path(build, href, prefix):
    path = urlsplit(urljoin('https://example.test' + prefix + '/', href)).path
    if not path.startswith(prefix + '/'):
        raise AssertionError(f'Link fora do prefixo {prefix}: {href}')
    path = path[len(prefix):].lstrip('/')
    result = build / path
    return result / 'index.html' if result.is_dir() else result


def check_archive(output, prefix, language, category, home, expected, excluded, populated):
    locale = 'en/' if language == 'en' else ''
    path = output / locale / 'posts' / category / 'index.html'
    require(path.is_file(), f'Arquivo {language} {category} não foi gerado')
    page = parse(path)
    listed = cards(page)
    if populated:
        require(expected <= home.keys(), f'Fixtures {language} {category} ausentes da home')
        require(expected <= listed.keys(), f'Fixtures {language} {category} ausentes do arquivo')
        require(not excluded & listed.keys(), f'Posts indevidos no arquivo {language} {category}')
        require(listed.keys() <= home.keys(), f'Posts do arquivo {language} ausentes da home')
        for title, href in listed.items():
            require(href == home[title], f'Links {language} {category} divergem: {title}')
            require(generated_path(output, href, prefix).is_file(), f'Destino não existe: {href}')
    else:
        require(not listed, f'Arquivo {language} {category} deveria estar vazio')
        require(any(node.text() for node in one(page.root, 'main').find('p', 'posts-empty')),
                f'Estado vazio {language} {category} ausente')


def expect_rejected(build, path, replacement, error_text, message):
    original = path.read_bytes() if path.exists() else None
    try:
        path.write_bytes(replacement)
        result = subprocess.run(
            [sys.executable, str(SITE / 'tests/integration/test_built_site.py'),
             str(build), '--base-path', '/site'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        require(result.returncode != 0 and error_text in result.stdout, message)
    finally:
        if original is None:
            path.unlink()
        else:
            path.write_bytes(original)


def build_and_check(source, root, prefix, populated):
    output = root / ('site' if prefix else 'root') / ('populated' if populated else 'empty')
    subprocess.run(['jekyll', 'build', '--source', str(source), '--destination', str(output),
                    '--baseurl', prefix], check=True, cwd=source)
    home = cards(parse(output / 'index.html'), 'posts')
    english_home = output / 'en/index.html'
    require(english_home.is_file(), 'Página inicial EN não foi gerada')
    english_cards = cards(parse(english_home), 'posts')
    cases = (
        ('pt', 'off-topic', home, {TOPIC}, {OTHER, TUTORIAL, ANOTHER_TUTORIAL}),
        ('pt', 'tutorial', home, {TUTORIAL, ANOTHER_TUTORIAL}, {TOPIC, OTHER}),
        ('en', 'off-topic', english_cards, {EN_TOPIC}, {EN_OTHER, EN_TUTORIAL, EN_ANOTHER_TUTORIAL}),
        ('en', 'tutorial', english_cards, {EN_TUTORIAL, EN_ANOTHER_TUTORIAL}, {EN_TOPIC, EN_OTHER}),
    )
    for language, category, locale_home, expected, excluded in cases:
        check_archive(output, prefix, language, category, locale_home, expected,
                      excluded, populated)
    if populated:
        for language, title, labels, locale_home in (
                ('pt', ANOTHER_TUTORIAL, ['tutorial', 'estudos'], home),
                ('en', EN_ANOTHER_TUTORIAL, ['Tutorial', 'Studies'], english_cards)):
            card_url = locale_home[title]
            home_page = parse(output / ('en/index.html' if language == 'en' else 'index.html'))
            card = next(card for card in one(home_page.root, 'main').find('article')
                        if any(heading.text() == title for heading in card.find('h3')))
            require(one(card, 'span', 'post-category').text() == ' // '.join(labels),
                    f'Categorias do card {language} incorretas')
            detail = parse(generated_path(output, card_url, prefix))
            require(one(detail.root, 'span', 'post-category').text() == ' // '.join(labels),
                    f'Categorias do artigo {language} incorretas')
            feed_path = output / ('en/feed.xml' if language == 'en' else 'feed.xml')
            items = ET.parse(feed_path).findall('./channel/item')
            item = next(item for item in items if item.findtext('title') == title)
            require([category.text for category in item.findall('category')] == labels,
                    f'Categorias RSS {language} incorretas')
        require({EN_TOPIC, EN_OTHER, EN_TUTORIAL, EN_ANOTHER_TUTORIAL} <= set(english_cards),
                'Fixtures EN não renderizaram')
        require(not {TOPIC, OTHER, TUTORIAL, ANOTHER_TUTORIAL} & set(english_cards),
                'Posts PT vazaram para EN')
        require(not {EN_TOPIC, EN_OTHER, EN_TUTORIAL, EN_ANOTHER_TUTORIAL} & set(home),
                'Posts EN vazaram para PT')
    subprocess.run([sys.executable, str(SITE / 'tests/integration/test_built_site.py'),
                    str(output), '--base-path', prefix or '/'], check=True)
    print(f'PASS fixture prefixo={prefix or "/"} posts={"quatro" if populated else "nenhum"}')


def main():
    scratch = os.environ.get('TMPDIR')
    if not scratch:
        raise RuntimeError('Defina TMPDIR para isolar os builds fora do repositório')
    with tempfile.TemporaryDirectory(prefix='jekyll-off-topic-', dir=scratch) as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        for folder in ('assets', '_data', '_includes', '_layouts', '_posts'):
            if (SITE / folder).exists():
                shutil.copytree(SITE / folder, source / folder)
        for name in ('_config.yml', 'index.html'):
            shutil.copy2(SITE / name, source / name)
        # Copy any new Jekyll source pages except generated/development directories.
        for entry in SITE.iterdir():
            if entry.name.startswith(('_', '.')) or entry.name in (
                    'assets', 'index.html', 'README.md', 'shell.nix', 'tests'):
                continue
            if entry.is_dir():
                shutil.copytree(entry, source / entry.name)
            elif entry.suffix in ('.html', '.md', '.xml') or entry.name == 'search.json':
                shutil.copy2(entry, source / entry.name)
        posts = source / '_posts'
        posts.mkdir(exist_ok=True)
        (posts / '2020-01-01-fixture-topic.md').write_text(
            '---\nlayout: post\ntitle: Fixture off-topic exclusiva\n'
            'lang: pt\ntranslation_key: fixture-topic\ncategories: [off-topic]\n'
            'permalink: /posts/:year/:month/:day/:title/\n---\n\nConteúdo teste.\n')
        (posts / '2020-01-02-fixture-other.md').write_text(
            '---\nlayout: post\ntitle: Fixture fora da categoria exclusiva\n'
            'lang: pt\ntranslation_key: fixture-other\ncategories: [estudos]\n'
            'permalink: /posts/:year/:month/:day/:title/\n---\n\nConteúdo teste.\n')
        (posts / '2020-01-03-fixture-tutorial.md').write_text(
            '---\nlayout: post\ntitle: Fixture tutorial exclusiva\n'
            'lang: pt\ntranslation_key: fixture-tutorial\ncategories: [tutorial]\n'
            'permalink: /posts/:year/:month/:day/:title/\n---\n\nConteúdo teste.\n')
        (posts / '2020-01-04-fixture-another-tutorial.md').write_text(
            '---\nlayout: post\ntitle: Fixture segundo tutorial\n'
            'lang: pt\ntranslation_key: fixture-another-tutorial\ncategories: [tutorial, estudos]\n'
            'permalink: /posts/:year/:month/:day/:title/\n---\n\nOutro conteúdo de teste.\n')
        for day, slug, key, title, category in (
                ('01', 'topic-en', 'fixture-topic', EN_TOPIC, 'off-topic'),
                ('02', 'other-en', 'fixture-other', EN_OTHER, 'studies'),
                ('03', 'tutorial-en', 'fixture-tutorial', EN_TUTORIAL, 'tutorial'),
                 ('04', 'another-tutorial-en', 'fixture-another-tutorial',
                  EN_ANOTHER_TUTORIAL, 'tutorial, studies')):
            (posts / f'2020-01-{day}-{slug}.md').write_text(
                f'---\nlayout: post\nlang: en\ntranslation_key: {key}\n'
                f'title: {title}\ncategories: [{category}]\n'
                f'permalink: /en/posts/2020/01/{day}/{slug}/\n---\n\n'
                f'Test content for {title}.\n')
        for prefix in ('', '/site'):
            build_and_check(source, root, prefix, populated=True)
        site_build = root / 'site/populated'
        english_page = site_build / 'en/index.html'
        english_html = english_page.read_text(encoding='utf-8')
        without_about, count = re.subn(
            r'<a\b[^>]*href="/site/en/sobre/"[^>]*>About</a>', '', english_html)
        require(count == 1, 'Fixture EN precisa de Sobre no rodapé para testar regressão')
        expect_rejected(site_build, english_page, without_about.encode(),
                        'Link Sobre localizado ausente do rodapé',
                        'Remover Sobre do rodapé EN deve falhar')
        home_page = site_build / 'index.html'
        home_html = home_page.read_text(encoding='utf-8')
        search = re.findall(r'<div class="search" data-search\b.*?</div>', home_html, re.S)
        require(len(search) == 1, 'Fixture precisa de busca única para testar posição')
        outside = home_html.replace(search[0], '', 1).replace('</header>', search[0] + '</header>', 1)
        expect_rejected(site_build, home_page, outside.encode(),
                        'Busca deve ficar dentro de .header-actions',
                        'Busca fora do contêiner do cabeçalho deve falhar')
        icon = site_build / 'assets/images/icon.svg'
        expect_rejected(site_build, icon, b'not-an-svg', 'SVG inválido',
                        'Um ícone servido com HTTP 200 mas inválido deve reprovar o build')
        for unsafe_svg in (
                b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/icon.png"/></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg" xml:base="https://example.invalid/"><image href="#remote"/></svg>',
                b'<?xml-stylesheet type="text/css" href="https://example.invalid/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="u\\72l(https://example.invalid/a.svg)"/></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><path style="fill:u/**/rl(https://example.invalid/a.svg)"/></svg>'):
            expect_rejected(site_build, icon, unsafe_svg, 'SVG inseguro',
                            'SVG com script ou referência remota deve reprovar o build')
        png = next((site_build / 'assets/images').glob('*.png'))
        original_png = png.read_bytes()
        expect_rejected(site_build, png, original_png[:24], 'PNG inválido',
                        'PNG truncado com cabeçalho válido deve reprovar o build')
        invalid_pixels = (b'\x89PNG\r\n\x1a\n'
                          + png_chunk(b'IHDR', (1).to_bytes(4, 'big') * 2
                                      + bytes([8, 2, 0, 0, 0]))
                          + png_chunk(b'IDAT', zlib.compress(b'\x05\x00\x00\x00'))
                          + png_chunk(b'IEND', b''))
        expect_rejected(site_build, png, invalid_pixels, 'PNG inválido',
                        'PNG com CRC correto mas filtro inválido deve reprovar o build')
        font = next((site_build / 'assets/fonts').glob('*.woff2'))
        expect_rejected(site_build, font, b'wOF2', 'WOFF2 inválida',
                        'Uma fonte truncada com assinatura válida deve reprovar o build')
        fake_font = b'wOF2' + b'OTTO' + (48).to_bytes(4, 'big') + (1).to_bytes(2, 'big') + bytes(34)
        expect_rejected(site_build, font, fake_font, 'WOFF2 inválida',
                        'WOFF2 com cabeçalho plausível mas sem fonte deve reprovar o build')
        stylesheet = site_build / 'assets/css/style.css'
        original_stylesheet = stylesheet.read_text()
        require(original_stylesheet.count('font-family: var(--font);') == 1,
                'Fixture esperava uma aplicação da fonte declarada no CSS')
        expect_rejected(site_build, stylesheet,
                        original_stylesheet.replace('font-family: var(--font);',
                                                    'font-family: monospace;').encode(),
                        'Fonte declarada mas não utilizada',
                        'Fonte local não aplicada à página deve reprovar o build')
        expect_rejected(site_build, site_build / '.env.local', b'fixture-placeholder\n',
                        'Arquivo privado no build', 'O build não deve aceitar arquivos locais privados')
        expect_rejected(site_build, site_build / 'credentials.json', b'{"fixture": true}\n',
                        'Arquivo privado no build',
                        'Um arquivo privado não previsto em lista de bloqueio deve reprovar o build')
        private_dir = site_build / 'en/private'
        private_dir.mkdir()
        try:
            expect_rejected(site_build, private_dir / 'index.html', b'<h1>Internal page</h1>',
                            'Arquivo privado no build',
                            'Um index.html extra sob en/ não deve ser publicado')
        finally:
            private_dir.rmdir()
        search_index = site_build / 'search.json'
        entries = json.loads(search_index.read_text(encoding='utf-8'))
        require(bool(entries), 'Fixture populada precisa ter posts no índice')
        expect_rejected(site_build, search_index, b'[{invalid json]', 'Índice JSON inválido',
                        'JSON malformado deve reprovar o teste HTTP')
        expect_rejected(site_build, search_index, json.dumps(entries[:-1]).encode(),
                        'Índice não corresponde aos posts publicados',
                        'Índice sem um post publicado deve ser rejeitado')
        rss = site_build / 'feed.xml'
        original_rss = rss.read_text(encoding='utf-8')
        require('<category>estudos</category>' in original_rss,
                'Fixture precisa de RSS com múltiplas categorias')
        expect_rejected(site_build, rss,
                        original_rss.replace('<category>estudos</category>', '', 1).encode(),
                        'Categoria RSS diferente do card',
                        'Remover uma categoria do RSS deve reprovar o build')
        expect_rejected(site_build, site_build / 'other.json', b'[]',
                        'Arquivo privado no build',
                        'A allowlist deve aceitar somente search.json na raiz')
        expect_rejected(site_build, site_build / 'assets/images/unused.svg',
                        b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                        'SVG inseguro', 'SVG não vinculado também deve ser validado antes da publicação')
        originals = {}
        for article in posts.rglob('*.md'):
            content = article.read_text()
            if 'translation_key: 2026-10-19-mudanca' in content:
                originals[article] = content
                article.write_text(re.sub(r'^image(?:_alt)?:[^\n]*\n', '', content, flags=re.M))
        require(len(originals) == 2, 'Fixture deve conter o par ilustrado PT/EN')
        try:
            post_art_by_title(posts)
        except ValueError as error:
            require('Ilustração aprovada ausente' in str(error), str(error))
        else:
            raise AssertionError('Remover a ilustração aprovada deve falhar')
        finally:
            for article, content in originals.items():
                article.write_text(content)
        extra_art = posts / '2020-01-04-unrelated-icon.md'
        extra_art.write_text(
            '---\ntitle: Unrelated icon\nlang: pt\ntranslation_key: unrelated\n'
            'image: /assets/images/icon-agents.svg\nimage_alt: Unrelated\n---\n\nTest.\n')
        try:
            post_art_by_title(posts)
        except ValueError as error:
            require('O ícone dos agentes pertence' in str(error), str(error))
        else:
            raise AssertionError('Ícone aprovado não pode aparecer em outro par de artigos')
        extra_art.unlink()
        folded_alt = posts / '2020-01-05-folded-alt.md'
        folded_alt.write_text(
            '---\nlayout: post\nlang: en\ntitle: "A title: with punctuation"\n'
            'image: /assets/images/icon.svg\nimage_alt: >-\n'
            '  A mascot with glasses\n  and a laptop\n---\n\nTest.\n')
        try:
            artwork = post_art_by_title(posts)
            require(artwork[('en', 'A title: with punctuation')] ==
                    ('/assets/images/icon.svg', 'A mascot with glasses and a laptop'),
                    'Front matter YAML dobrado deve ser interpretado como Jekyll')
        finally:
            folded_alt.unlink()
        shutil.rmtree(posts)  # Only the scratch copy, never the repository's posts.
        for prefix in ('', '/site'):
            build_and_check(source, root, prefix, populated=False)


if __name__ == '__main__':
    main()
