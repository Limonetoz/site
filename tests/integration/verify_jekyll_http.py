"""Validate generated pages and their local links through HTTP."""

import argparse
import sys
from collections import deque
from datetime import datetime
from html.parser import HTMLParser
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
