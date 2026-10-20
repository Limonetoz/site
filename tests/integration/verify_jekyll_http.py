"""Validate generated pages and their local links through HTTP."""

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import urlopen


class Element:
    def __init__(self, tag='', attrs=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []

    def find(self, tag=None, css_class=None):
        for child in self.children:
            if isinstance(child, Element):
                if ((tag is None or child.tag == tag)
                        and (css_class is None or css_class in child.attrs.get('class', '').split())):
                    yield child
                yield from child.find(tag, css_class)

    def text(self):
        return ''.join(child.text() if isinstance(child, Element) else child
                       for child in self.children).strip()


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.links = []
        self.ids = set()
        self.headings = 0
        self.main_elements = 0
        self.stylesheets = 0
        self.images = []
        self.root = Element()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or '' for key, value in attrs}
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                       'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'h1':
            self.headings += 1
        if tag == 'main':
            self.main_elements += 1
        if tag == 'img':
            self.images.append(attrs)
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split():
            self.stylesheets += 1
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs)
        for attribute in ('href', 'src'):
            if attrs.get(attribute):
                self.references.append(attrs[attribute])

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def one(element, tag=None, css_class=None):
    found = list(element.find(tag, css_class))
    if len(found) != 1:
        raise ValueError(f'Esperado um {tag or "elemento"}.{css_class or ""}; encontrados {len(found)}')
    return found[0]


def check_post_navigation(page, page_url, base):
    if not any(urljoin(page_url, link.attrs.get('href', '')) == base + '#posts'
               for navigation in page.root.find('nav')
               for link in navigation.find('a')):
        raise ValueError(f'Navegação para a lista de posts incorreta: {page_url}')


def check_blog(base, pages):
    home = pages[base]
    check_post_navigation(home, base, base)
    posts = [node for node in home.root.find('section')
             if node.attrs.get('id') == 'posts']
    if len(posts) != 1:
        raise ValueError('Seção #posts ausente ou duplicada')
    cards = list(posts[0].find('article'))
    if not cards:
        empty = [node for node in posts[0].find('p', 'posts-empty')
                 if node.text()]
        if len(empty) != 1:
            raise ValueError('Nenhum post ou mensagem de lista vazia na página inicial')
        return
    seen = set()
    for card in cards:
        headings = [node for node in card.find()
                    if node.tag in ('h2', 'h3', 'h4')]
        if len(headings) != 1:
            raise ValueError('Card sem título único')
        heading = headings[0]
        title = heading.text()
        title_link = one(heading, 'a')
        href = title_link.attrs.get('href', '')
        if not title or not href or not any(p.text() for p in card.find('p')):
            raise ValueError('Card sem título, resumo ou link para o post')
        post_links = list(card.find('a', 'post-link'))
        if any(link.attrs.get('href') != href for link in post_links):
            raise ValueError('Links do card apontam para posts diferentes')
        target, fragment = urldefrag(urljoin(base, href))
        if (fragment or not target.startswith(base) or target == base
                or target in seen or target not in pages):
            raise ValueError(f'Post duplicado, fora do prefixo ou não renderizado: {target}')
        seen.add(target)
        detail = pages[target]
        check_post_navigation(detail, target, base)
        entry = one(one(detail.root, 'main'), 'article')
        if one(entry, 'h1').text() != title:
            raise ValueError(f'Título do card difere do post: {target}')
        if title not in one(detail.root, 'title').text():
            raise ValueError(f'Título do documento não identifica o post: {target}')
        description = [meta.attrs.get('content', '').strip()
                       for meta in detail.root.find('meta')
                       if meta.attrs.get('name') == 'description']
        if len(description) != 1 or not description[0]:
            raise ValueError(f'Descrição do post ausente: {target}')
        content = [node for node in entry.children
                   if isinstance(node, Element) and node.tag != 'header']
        if not any(node.text() for node in content):
            raise ValueError(f'Conteúdo do post vazio: {target}')
        card_time = one(card, 'time')
        post_time = one(entry, 'time')
        timestamp = card_time.attrs.get('datetime', '')
        try:
            day = datetime.fromisoformat(timestamp).strftime('%d.%m.%Y')
        except ValueError:
            raise ValueError(f'Data do post inválida: {target}') from None
        if (not timestamp or post_time.attrs.get('datetime') != timestamp
                or card_time.text() != day or post_time.text() != day):
            raise ValueError(f'Datas do card e do post inconsistentes: {target}')
        category = one(card, 'span', 'post-category').text()
        if not category or one(entry, 'span', 'post-category').text() != category:
            raise ValueError(f'Categoria do card difere do post: {target}')
        back_links = [link for link in one(detail.root, 'main').find('a')
                      if urljoin(target, link.attrs.get('href', '')) == base + '#posts']
        if not back_links:
            raise ValueError(f'Retorno aos posts incorreto: {target}')

def check_off_topic(base, pages):
    archive = urljoin(base, 'posts/off-topic/')
    home = pages[base]
    for url, page in pages.items():
        if not any(urljoin(url, link.attrs.get('href', '')) == archive
                   and 'off-topic' in link.text().lower()
                   for nav in page.root.find('nav') for link in nav.find('a')):
            raise ValueError(f'Navegação Off-topic ausente: {url}')
    if archive not in pages:
        raise ValueError(f'Arquivo Off-topic não renderizado: {archive}')
    main = one(pages[archive].root, 'main')
    cards = list(main.find('article'))
    if not cards and not any(node.text() for node in main.find('p', 'posts-empty')):
        raise ValueError('Arquivo Off-topic sem posts e sem estado vazio visível')
    home_sections = [section for section in home.root.find('section')
                     if section.attrs.get('id') == 'posts']
    if len(home_sections) != 1:
        raise ValueError('Seção de posts da página inicial ausente')
    home_targets = {
        urljoin(base, link.attrs['href'])
        for card in home_sections[0].find('article')
        for heading in card.find() if heading.tag in ('h2', 'h3', 'h4')
        for link in heading.find('a') if link.attrs.get('href')
        if any(part.strip().lower() == 'off-topic'
               for part in one(card, 'span', 'post-category').text().split('//'))
    }
    seen = set()
    for card in cards:
        headings = [node for node in card.find() if node.tag in ('h2', 'h3', 'h4')]
        if len(headings) != 1:
            raise ValueError('Card Off-topic sem título único')
        link = one(headings[0], 'a')
        target = urljoin(archive, link.attrs.get('href', ''))
        if target not in home_targets or target in seen or target not in pages:
            raise ValueError(f'Post Off-topic inválido ou repetido: {target}')
        seen.add(target)
    if seen != home_targets:
        raise ValueError(f'Arquivo Off-topic não corresponde aos posts categorizados: '
                         f'esperados {sorted(home_targets)}, encontrados {sorted(seen)}')

def check_tutorial(base, pages):
    archive = urljoin(base, 'posts/tutorial/')
    for url, page in pages.items():
        links = [link for nav in page.root.find('nav') for link in nav.find('a')
                 if link.text().strip().lower() == 'tutorial']
        if len(links) != 1 or urljoin(url, links[0].attrs.get('href', '')) != archive:
            raise ValueError(f'Navegação Tutorial fora do baseurl: {url}')
    if archive not in pages:
        raise ValueError(f'Arquivo Tutorial não renderizado: {archive}')
    main = one(pages[archive].root, 'main')
    cards = list(main.find('article'))
    if not cards and not any(node.text() for node in main.find('p', 'posts-empty')):
        raise ValueError('Arquivo Tutorial sem posts e sem estado vazio visível')
    home_posts = [section for section in pages[base].root.find('section')
                  if section.attrs.get('id') == 'posts']
    if len(home_posts) != 1:
        raise ValueError('Seção de posts da página inicial ausente')
    home_targets = {
        urljoin(base, one(heading, 'a').attrs['href'])
        for card in home_posts[0].find('article')
        if any(part.strip().lower() == 'tutorial'
               for part in one(card, 'span', 'post-category').text().split('//'))
        for heading in card.find() if heading.tag in ('h2', 'h3', 'h4')
    }
    seen = set()
    for card in cards:
        headings = [node for node in card.find() if node.tag in ('h2', 'h3', 'h4')]
        if len(headings) != 1:
            raise ValueError('Card Tutorial sem título único')
        target = urljoin(archive, one(headings[0], 'a').attrs.get('href', ''))
        if target not in home_targets or target in seen or target not in pages:
            raise ValueError(f'Post Tutorial inválido ou repetido: {target}')
        seen.add(target)
    if seen != home_targets:
        raise ValueError(f'Arquivo Tutorial não corresponde aos posts categorizados: '
                         f'esperados {sorted(home_targets)}, encontrados {sorted(seen)}')

def check_about(base, pages):
    about_url = urljoin(base, 'sobre/')
    for url, page in pages.items():
        links = [link for nav in page.root.find('nav') for link in nav.find('a')
                 if link.text().strip().lower() == 'sobre']
        if len(links) != 1 or urljoin(url, links[0].attrs.get('href', '')) != about_url:
            raise ValueError(f'Navegação Sobre fora do baseurl: {url}')
    if about_url not in pages:
        raise ValueError(f'Página Sobre não renderizada: {about_url}')

    about = pages[about_url]
    main = one(about.root, 'main')
    if not one(main, 'h1').text():
        raise ValueError('Página Sobre sem título visível no conteúdo principal')
    home_styles = {link.attrs.get('href') for link in pages[base].root.find('link')
                   if 'stylesheet' in link.attrs.get('rel', '').split()}
    about_styles = {link.attrs.get('href') for link in about.root.find('link')
                    if 'stylesheet' in link.attrs.get('rel', '').split()}
    if not home_styles.intersection(about_styles):
        raise ValueError('Página Sobre não usa a folha de estilos compartilhada')

    profiles = {'https://github.com/Limonetoz/', 'https://codeberg.org/Code4lag',
                'https://www.linkedin.com/in/gabriel-lima-6735452b9/'}
    external = [link for link in main.find('a')
                if urlsplit(link.attrs.get('href', '')).scheme in ('http', 'https')]
    if len(external) != 3 or {link.attrs['href'] for link in external} != profiles:
        raise ValueError('Página Sobre deve conter exatamente os três links de perfil')
    for link in external:
        if not link.text():
            raise ValueError(f'Link de perfil sem texto acessível: {link.attrs["href"]}')
        accessible_name = link.attrs.get('aria-label') or link.text()
        if 'linkedin.com' in link.attrs['href'] and 'linkedin' not in accessible_name.lower():
            raise ValueError('Link LinkedIn sem nome acessível da plataforma')
        if (link.attrs.get('target') != '_blank' or
                not {'noopener', 'noreferrer'} <= set(link.attrs.get('rel', '').split())):
            raise ValueError(f'Link de perfil em nova aba sem proteção: {link.attrs["href"]}')
        icons = list(link.find('img'))
        is_linkedin = 'linkedin.com' in link.attrs['href']
        if len(icons) != (2 if is_linkedin else 1):
            raise ValueError(f'Quantidade de ícones incorreta: {link.attrs["href"]}')
        if is_linkedin:
            classes = {tuple(icon.attrs.get('class', '').split()) for icon in icons}
            if not all(any(theme in group for group in classes)
                       for theme in ('about-icon-linkedin-dark', 'about-icon-linkedin-light')):
                raise ValueError('LinkedIn precisa de ícones oficiais para ambos os temas')
        if len({icon.attrs.get('src') for icon in icons}) != len(icons):
            raise ValueError('Ícones de perfil duplicados')
        for icon in icons:
            src = icon.attrs.get('src', '')
            parsed = urlsplit(urljoin(about_url, src))
            if is_linkedin and 'linkedin' not in parsed.path.lower():
                raise ValueError('Perfil LinkedIn deve usar ícone local da marca LinkedIn')
            extension = '.png' if is_linkedin else '.svg'
            if (not parsed.path.lower().endswith(extension) or
                    (parsed.scheme, parsed.netloc) != (urlsplit(base).scheme, urlsplit(base).netloc)
                    or not parsed.path.startswith(urlsplit(base).path)):
                raise ValueError(f'Ícone local inválido: {src}')
            if 'alt' not in icon.attrs and icon.attrs.get('aria-hidden') != 'true':
                raise ValueError(f'Ícone sem alt ou aria-hidden: {src}')
            with urlopen(urljoin(about_url, src), timeout=10) as response:
                content_type = 'image/png' if is_linkedin else 'image/svg+xml'
                if response.status != 200 or response.headers.get_content_type() != content_type:
                    raise ValueError(f'Ícone não carregado: {src}')
                data = response.read()
                if is_linkedin:
                    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise ValueError(f'Ícone PNG inválido: {src}')
                else:
                    try:
                        if ET.fromstring(data).tag != '{http://www.w3.org/2000/svg}svg':
                            raise ValueError(f'Ícone SVG sem conteúdo SVG: {src}')
                    except ET.ParseError as error:
                        raise ValueError(f'Ícone SVG inválido: {src}: {error}') from error

def check_font(base, pages):
    for page_url, page in pages.items():
        styles = [urljoin(page_url, link.attrs.get('href', ''))
                  for link in page.root.find('link')
                  if 'stylesheet' in link.attrs.get('rel', '').split()]
        found_weights = set()
        for style_url in styles:
            if not style_url.startswith(base):
                continue
            with urlopen(style_url, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f'CSS local indisponível: {style_url}')
                css = response.read().decode('utf-8')
            css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
            rules = [(selector.strip(), body) for selector, body in
                     re.findall(r'([^{}]+)\{([^{}]*)\}', css)]
            family = r'["\']?JetBrains\s+Mono["\']?'
            faces = [body for selector, body in rules if selector == '@font-face'
                     and re.search(r'font-family\s*:\s*' + family + r'\s*(?:;|$)', body, re.I)]
            body_fonts = [body for selector, body in rules
                          if 'body' in [part.strip() for part in selector.split(',')]
                          and re.search(r'font-family\s*:', body)]
            root_fonts = [body for selector, body in rules if selector == ':root'
                          and re.search(r'--font\s*:\s*' + family + r'\s*(?:[,;]|$)', body, re.I)]
            primary = any(re.search(r'font-family\s*:\s*' + family + r'\s*(?:[,;]|$)', body, re.I)
                          or (re.search(r'font-family\s*:\s*var\(\s*--font\s*\)', body)
                              and root_fonts)
                          for body in body_fonts)
            if not faces or not primary:
                continue
            for face in faces:
                weight = re.search(r'font-weight\s*:\s*(400|500|700)\s*(?:;|$)', face)
                urls = re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', face)
                for source in urls:
                    font_url = urljoin(style_url, source)
                    if not source.lower().split('?')[0].endswith('.woff2') or not font_url.startswith(base):
                        continue
                    with urlopen(font_url, timeout=10) as response:
                        if response.status == 200 and response.read(4) == b'wOF2' and weight:
                            found_weights.add(weight.group(1))
        if found_weights != {'400', '500', '700'}:
            raise ValueError(f'JetBrains Mono local WOFF2 incompleta como fonte primária: '
                             f'{page_url} ({sorted(found_weights)})')

def check_theme(base, pages):
    scripts = set()
    for url, page in pages.items():
        buttons = [node for node in page.root.find('button')
                   if node.attrs.get('id') == 'theme-toggle']
        if len(buttons) != 1 or not (buttons[0].text() or
                                    buttons[0].attrs.get('aria-label')):
            raise ValueError(f'Botão acessível #theme-toggle ausente: {url}')
        local = [urljoin(url, node.attrs['src']) for node in page.root.find('script')
                 if node.attrs.get('src') and
                 urljoin(url, node.attrs['src']).startswith(base)]
        if not local:
            raise ValueError(f'Script local do tema ausente: {url}')
        scripts.update(local)
    if not shutil.which('node'):
        raise ValueError('Node.js necessário para testar persistência do tema')
    failures = []
    for script in scripts:
        with urlopen(script, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() not in (
                    'text/javascript', 'application/javascript'):
                raise ValueError(f'Script local indisponível: {script}')
            source = response.read().decode('utf-8')
        result = subprocess.run(['node', str(Path(__file__).with_name('verify_theme.js'))],
                                input=source, text=True, capture_output=True, check=False)
        if not result.returncode:
            return
        failures.append(f'{script}: {result.stderr.strip()}')
    raise ValueError('Nenhum script local inicializa/persiste o tema: ' + '; '.join(failures))


def verify(base):
    base = base.rstrip('/') + '/'
    origin = urlsplit(base)
    if origin.scheme not in ('http', 'https') or not origin.netloc:
        raise ValueError('Informe uma URL HTTP ou HTTPS válida.')
    queue = deque([base])
    visited = set()
    pages = {}
    fragments = []
    errors = []
    successful = []
    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            with urlopen(url, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f'HTTP {response.status}')
                if response.url != url:
                    raise ValueError(f'Redirecionamento inesperado: {response.url}')
                data = response.read()
                content_type = response.headers.get_content_type()
            if content_type == 'text/html':
                html = data.decode('utf-8')
                if '{%' in html or '{{' in html or html.startswith('---'):
                    raise ValueError('Liquid ou front matter não processado')
                page = Page()
                page.feed(html)
                pages[url] = page
                if page.headings != 1 or page.main_elements != 1:
                    raise ValueError('A página deve ter exatamente um h1 e um main')
                if not page.stylesheets:
                    raise ValueError('Folha de estilos ausente')
                if any('alt' not in image for image in page.images):
                    raise ValueError('Imagem sem atributo alt')
                github = [link for link in page.links
                          if link['href'] == 'https://github.com/Limonetoz/site']
                if not github:
                    raise ValueError('Link do repositório ausente')
                for link in page.links:
                    if (link.get('target') == '_blank'
                            and 'noopener' not in link.get('rel', '').split()):
                        raise ValueError('Link em nova aba sem noopener')
                for reference in page.references:
                    target, fragment = urldefrag(urljoin(url, reference))
                    parsed = urlsplit(target)
                    if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
                        continue
                    if not parsed.path.startswith(origin.path):
                        raise ValueError(f'Link fora do prefixo do site: {reference}')
                    queue.append(target)
                    if fragment:
                        fragments.append((target, fragment))
            successful.append(url)
        except (OSError, ValueError) as error:
            errors.append(f'{url}: {error}')
    for target, fragment in fragments:
        if target in pages and fragment not in pages[target].ids:
            errors.append(f'Âncora inexistente: {target}#{fragment}')
    if base in pages and not errors:
        try:
            check_blog(base, pages)
            check_off_topic(base, pages)
            check_tutorial(base, pages)
            check_about(base, pages)
            check_font(base, pages)
            check_theme(base, pages)
        except ValueError as error:
            errors.append(f'{base}: {error}')
    for error in errors:
        print('FAIL', error, file=sys.stderr)
    if not errors:
        for url in successful:
            print('PASS', url)
    return bool(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    args = parser.parse_args()
    try:
        return int(verify(args.base_url))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
