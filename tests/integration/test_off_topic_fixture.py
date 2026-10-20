"""Build isolated blog fixtures; assert category filtering and empty state at / and /site."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from verify_jekyll_http import Page, one

SITE = Path(__file__).resolve().parents[2]
TOPIC = 'Fixture off-topic exclusiva'
OTHER = 'Fixture fora da categoria exclusiva'
TUTORIAL = 'Fixture tutorial exclusiva'
EN_TOPIC = 'English off-topic fixture'
EN_OTHER = 'English uncategorized fixture'
EN_TUTORIAL = 'English tutorial fixture'


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


def build_and_check(source, root, prefix, populated):
    output = root / ('site' if prefix else 'root') / ('populated' if populated else 'empty')
    subprocess.run(['jekyll', 'build', '--source', str(source), '--destination', str(output),
                    '--baseurl', prefix], check=True, cwd=source)
    home = cards(parse(output / 'index.html'), 'posts')
    archive_path = output / 'posts/off-topic/index.html'
    if not archive_path.is_file():
        raise AssertionError('Arquivo /posts/off-topic/ não foi gerado')
    archive = parse(archive_path)
    listed = cards(archive)
    if populated:
        assert TOPIC in home and OTHER in home, 'Fixtures não renderizaram na página inicial'
        assert TOPIC in listed, 'Post categorizado off-topic ausente do arquivo'
        assert OTHER not in listed, 'Post sem off-topic vazou para o arquivo'
        assert listed[TOPIC] == home[TOPIC], 'Links da listagem e da página inicial divergem'
        assert generated_path(output, listed[TOPIC], prefix).is_file(), 'Destino não existe'
    else:
        assert not listed, 'Arquivo sem posts deve estar vazio'
        assert any(node.text() for node in one(archive.root, 'main').find('p', 'posts-empty')), (
            'Estado vazio Off-topic ausente')
    tutorial_path = output / 'posts/tutorial/index.html'
    if not tutorial_path.is_file():
        raise AssertionError('Arquivo /posts/tutorial/ não foi gerado')
    tutorial = parse(tutorial_path)
    tutorial_cards = cards(tutorial)
    if populated:
        assert TUTORIAL in home, 'Fixture tutorial não renderizou na página inicial'
        assert set(tutorial_cards) == {TUTORIAL}, (
            'Arquivo Tutorial deve conter apenas posts categorizados tutorial')
        assert tutorial_cards[TUTORIAL] == home[TUTORIAL], (
            'Link Tutorial difere da página inicial')
        assert generated_path(output, tutorial_cards[TUTORIAL], prefix).is_file(), (
            'Destino Tutorial não existe')
    else:
        assert not tutorial_cards, 'Arquivo Tutorial sem posts deve estar vazio'
        assert any(node.text() for node in one(tutorial.root, 'main').find('p', 'posts-empty')), (
            'Estado vazio Tutorial ausente')
    english_home = output / 'en/index.html'
    assert english_home.is_file(), 'Página inicial EN não foi gerada'
    english_cards = cards(parse(english_home), 'posts')
    english_archives = {
        'off-topic': (EN_TOPIC, EN_OTHER),
        'tutorial': (EN_TUTORIAL, EN_OTHER),
    }
    for category, (expected, excluded) in english_archives.items():
        path = output / 'en/posts' / category / 'index.html'
        assert path.is_file(), f'Arquivo EN {category} não foi gerado'
        page = parse(path)
        listed = cards(page)
        if populated:
            assert expected in english_cards and expected in listed, f'Fixture EN {category} ausente'
            assert excluded not in listed and TOPIC not in listed, f'Post de outro idioma/categoria no arquivo EN {category}'
            assert listed[expected] == english_cards[expected], f'Links EN {category} divergem'
            assert generated_path(output, listed[expected], prefix).is_file(), 'Destino EN não existe'
        else:
            assert not listed, f'Arquivo EN {category} deveria estar vazio'
            assert any(node.text() for node in one(page.root, 'main').find('p', 'posts-empty')), (
                f'Estado vazio EN {category} ausente')
    if populated:
        assert {EN_TOPIC, EN_OTHER, EN_TUTORIAL} <= set(english_cards), 'Fixtures EN não renderizaram'
        assert not {TOPIC, OTHER, TUTORIAL} & set(english_cards), 'Posts PT vazaram para EN'
        assert not {EN_TOPIC, EN_OTHER, EN_TUTORIAL} & set(home), 'Posts EN vazaram para PT'
    subprocess.run([sys.executable, str(SITE / 'tests/integration/test_built_site.py'),
                    str(output), '--base-path', prefix or '/'], check=True)
    print(f'PASS fixture prefixo={prefix or "/"} posts={"três" if populated else "nenhum"}')


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
            elif entry.suffix in ('.html', '.md', '.xml'):
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
        for day, slug, key, title, category in (
                ('01', 'topic-en', 'fixture-topic', EN_TOPIC, 'off-topic'),
                ('02', 'other-en', 'fixture-other', EN_OTHER, 'studies'),
                ('03', 'tutorial-en', 'fixture-tutorial', EN_TUTORIAL, 'tutorial')):
            (posts / f'2020-01-{day}-{slug}.md').write_text(
                f'---\nlayout: post\nlang: en\ntranslation_key: {key}\n'
                f'title: {title}\ncategories: [{category}]\n'
                f'permalink: /en/posts/2020/01/{day}/{slug}/\n---\n\nTest content.\n')
        for prefix in ('', '/site'):
            build_and_check(source, root, prefix, populated=True)
        shutil.rmtree(posts)  # Only the scratch copy, never the repository's posts.
        for prefix in ('', '/site'):
            build_and_check(source, root, prefix, populated=False)


if __name__ == '__main__':
    main()
