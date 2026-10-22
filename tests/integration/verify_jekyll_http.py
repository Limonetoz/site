"""Validate generated pages and their local links through HTTP."""

import argparse
import base64
import binascii
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from collections import deque
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import urlopen

from PIL import Image, ImageFont


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


def valid_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    offset = 8
    image_data = []
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], 'big')
        end = offset + length + 12
        if end > len(data):
            return False
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        checksum = int.from_bytes(data[end - 4:end], 'big')
        if (offset == 8 and kind != b'IHDR') or zlib.crc32(kind + payload) != checksum:
            return False
        if kind == b'IHDR':
            if (offset != 8 or length != 13
                    or not int.from_bytes(payload[:4], 'big')
                    or not int.from_bytes(payload[4:8], 'big')):
                return False
        elif kind == b'IDAT':
            image_data.append(payload)
        elif kind == b'IEND':
            if length or end != len(data) or not image_data:
                return False
            try:
                decoder = zlib.decompressobj()
                decoder.decompress(b''.join(image_data))
                if not decoder.eof or decoder.unused_data:
                    return False
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    return image.format == 'PNG' and image.width > 0 and image.height > 0
            except (zlib.error, OSError, ValueError):
                return False
        offset = end
    return False


def check_local_asset(url, content_type, data):
    suffix = Path(urlsplit(url).path).suffix.lower()
    expected = {
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.woff2': 'font/woff2',
    }.get(suffix)
    accepted = {expected}
    if suffix == '.js':
        accepted.add('text/javascript')
    if suffix == '.woff2':
        accepted.add('application/font-woff2')
    if expected and (content_type not in accepted or not data):
        raise ValueError(f'Asset local indisponível ou tipo incorreto: {url}')
    if suffix == '.svg':
        try:
            root = ET.fromstring(data)
            if any(True for _ in ET.iterparse(BytesIO(data), events=('pi',))):
                raise ValueError(f'SVG inseguro: {url}')
        except ET.ParseError as error:
            raise ValueError(f'SVG inválido: {url}') from error
        if root.tag != '{http://www.w3.org/2000/svg}svg':
            raise ValueError(f'SVG inválido: {url}')
        safe_tags = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line',
                     'polyline', 'polygon', 'defs', 'linearGradient',
                     'radialGradient', 'stop', 'clipPath', 'mask', 'title',
                     'desc', 'text', 'tspan', 'image'}
        namespace = '{http://www.w3.org/2000/svg}'
        for element in root.iter():
            if not element.tag.startswith(namespace) or element.tag[len(namespace):] not in safe_tags:
                raise ValueError(f'SVG inseguro: {url}')
            for key, value in element.attrib.items():
                name = key.rsplit('}', 1)[-1].lower()
                if (name.startswith('on') or name == 'base'
                        or '@import' in value.lower() or 'javascript:' in value.lower()):
                    raise ValueError(f'SVG inseguro: {url}')
                if name in {'href', 'src'} and not value.startswith('#'):
                    if (element.tag != namespace + 'image'
                            or not value.startswith('data:image/png;base64,')):
                        raise ValueError(f'SVG inseguro: {url}')
                    try:
                        embedded = base64.b64decode(value.split(',', 1)[1], validate=True)
                    except (ValueError, binascii.Error) as error:
                        raise ValueError(f'SVG inseguro: {url}') from error
                    if not valid_png(embedded):
                        raise ValueError(f'SVG inseguro: {url}')
                references = re.findall(r'url\(\s*["\']?([^"\')]+)', value, re.I)
                if any(not ref.startswith('#') for ref in references):
                    raise ValueError(f'SVG inseguro: {url}')
    if suffix == '.png' and not valid_png(data):
        raise ValueError(f'PNG inválido: {url}')
    if suffix == '.woff2' and (len(data) < 48 or data[:4] != b'wOF2'
                               or int.from_bytes(data[8:12], 'big') != len(data)
                               or not int.from_bytes(data[12:14], 'big')):
        raise ValueError(f'WOFF2 inválida: {url}')
    if suffix == '.woff2':
        try:
            ImageFont.truetype(BytesIO(data), size=12).getname()
        except (OSError, ValueError) as error:
            raise ValueError(f'WOFF2 inválida: {url}') from error


def check_post_navigation(page, page_url, base):
    if not any(urljoin(page_url, link.attrs.get('href', '')) == base + '#posts'
               for navigation in page.root.find('nav')
               for link in navigation.find('a')):
        raise ValueError(f'Navegação para a lista de posts incorreta: {page_url}')


def post_art_by_title(posts):
    """Derive optional article artwork expectations from source front matter."""
    artwork = {}
    agent_icon_languages = {}
    for source in posts.rglob('*.md'):
        front_matter = re.match(r'\A---\s*\n(.*?)\n---', source.read_text(encoding='utf-8'), re.S)
        if not front_matter:
            continue
        fields = dict(re.findall(r'^([a-z_]+):[ \t]*(.*)$', front_matter.group(1), re.M))
        image = fields.get('image', '').strip().strip('"\'')
        # The approved illustration must remain on this translated article pair.
        if (fields.get('translation_key') == '2026-10-19-mudanca'
                and image != '/assets/images/icon-agents.svg'):
            raise ValueError(f'Ilustração aprovada ausente: {source}')
        if not image:
            continue
        language = fields.get('lang')
        title = fields.get('title', '').strip().strip('"\'')
        alt = fields.get('image_alt', '').strip().strip('"\'')
        key = (language, title)
        if (language not in ('pt', 'en') or not title or key in artwork
                or not image.startswith('/assets/images/') or not alt):
            raise ValueError(f'Metadados de imagem do post inválidos: {source}')
        artwork[key] = (image, alt)
        if image == '/assets/images/icon-agents.svg':
            translation_key = fields.get('translation_key')
            if not translation_key:
                raise ValueError(f'Ícone dos agentes sem par traduzido: {source}')
            agent_icon_languages.setdefault(translation_key, set()).add(language)
    if agent_icon_languages and (len(agent_icon_languages) != 1
                                 or next(iter(agent_icon_languages.values())) != {'pt', 'en'}):
        raise ValueError('O ícone dos agentes pertence a um único par PT/EN')
    return artwork


def check_blog(base, pages, artwork):
    home = pages[base]
    language = 'en' if base.rstrip('/').endswith('/en') else 'pt'
    art_pages = set()
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
        return art_pages
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
        expected_art = artwork.get((language, title))
        if expected_art:
            illustration = one(entry, 'figure', 'post-entry-art')
            icon = one(illustration, 'img')
            site_base = base if not base.rstrip('/').endswith('/en') else urljoin(base, '../')
            if (urljoin(target, icon.attrs.get('src', ''))
                    != urljoin(site_base, expected_art[0].lstrip('/'))
                    or icon.attrs.get('alt') != expected_art[1]):
                raise ValueError(f'Ilustração do post ausente ou incorreta: {target}')
            art_pages.add(target)
        elif list(entry.find('figure', 'post-entry-art')):
            raise ValueError(f'Ilustração não declarada no post: {target}')
        if one(entry, 'h1').text() != title:
            raise ValueError(f'Título do card difere do post: {target}')
        if title not in one(detail.root, 'title').text():
            raise ValueError(f'Título do documento não identifica o post: {target}')
        description = [meta.attrs.get('content', '').strip()
                       for meta in detail.root.find('meta')
                       if meta.attrs.get('name') == 'description']
        if len(description) != 1 or not description[0] or len(description[0]) > 160:
            raise ValueError(f'Descrição do post ausente ou longa demais: {target}')
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

    if len(art_pages) != sum(lang == language for lang, _ in artwork):
        raise ValueError(f'Posts ilustrados de {language} ausentes da listagem')
    return art_pages

def check_off_topic(base, pages):
    archive = urljoin(base, 'posts/off-topic/')
    home = pages[base]
    for url, page in pages.items():
        if not url.startswith(base):
            continue
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
        if not url.startswith(base):
            continue
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

def check_about(base, pages, language='pt', site_base=None):
    site_base = site_base or base
    about_url = urljoin(base, 'sobre/')
    label = 'sobre' if language == 'pt' else 'about'
    for url, page in pages.items():
        if not url.startswith(base):
            continue
        links = [link for nav in page.root.find('nav') for link in nav.find('a')
                 if link.text().strip().lower() == label]
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
                    or not parsed.path.startswith(urlsplit(urljoin(site_base, 'assets/images/')).path)):
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

def home_posts(base, pages):
    section = [node for node in pages[base].root.find('section')
               if node.attrs.get('id') == 'posts']
    if len(section) != 1:
        raise ValueError(f'Seção #posts ausente: {base}')
    result = {}
    for card in section[0].find('article'):
        headings = [node for node in card.find() if node.tag in ('h2', 'h3', 'h4')]
        if len(headings) != 1:
            raise ValueError(f'Card sem título único: {base}')
        url = urljoin(base, one(headings[0], 'a').attrs['href'])
        result[url] = (headings[0].text(), one(card, 'time').attrs['datetime'],
                       one(card, 'span', 'post-category').text())
    return result


def check_localization(base, pages):
    english = urljoin(base, 'en/')
    if english not in pages:
        raise ValueError(f'Página inicial EN não renderizada: {english}')
    static = {base: english,
              urljoin(base, 'sobre/'): urljoin(english, 'sobre/'),
              urljoin(base, 'posts/tutorial/'): urljoin(english, 'posts/tutorial/'),
              urljoin(base, 'posts/off-topic/'): urljoin(english, 'posts/off-topic/')}
    counterparts = dict(static)
    pt_posts = home_posts(base, pages)
    en_posts = home_posts(english, pages)
    for url in pt_posts:
        if url.startswith(english):
            raise ValueError(f'Post em inglês vazou para página PT: {url}')
        if url not in pages:
            raise ValueError(f'Post PT não renderizado: {url}')
        switches = [link for header in pages[url].root.find('header')
                    for link in header.find('a') if link.text().strip().upper() == 'EN']
        if len(switches) != 1:
            raise ValueError(f'Post PT sem switch EN: {url}')
        counterpart = urljoin(url, switches[0].attrs.get('href', ''))
        if counterpart not in en_posts:
            raise ValueError(f'Switch EN não leva ao post traduzido: {url} -> {counterpart}')
        if pt_posts[url][0] == en_posts[counterpart][0]:
            raise ValueError(f'Título do post não foi traduzido: {url}')
        pt_body = one(one(pages[url].root, 'main'), 'div', 'post-entry-content').text()
        en_body = one(one(pages[counterpart].root, 'main'), 'div', 'post-entry-content').text()
        if not pt_body or not en_body or pt_body == en_body:
            raise ValueError(f'Corpo do post traduzido ausente ou idêntico ao original: {url}')
        counterparts[url] = counterpart
    if set(en_posts) != set(counterparts.values()) - set(static.values()):
        raise ValueError('Listagens PT/EN não contêm exatamente os posts correspondentes')
    for url, counterpart in counterparts.items():
        for current, other, language, switch_label in (
                (url, counterpart, 'pt', 'EN'),
                (counterpart, url, 'en', 'PT')):
            if current not in pages:
                raise ValueError(f'Página localizada não renderizada: {current}')
            html = one(pages[current].root, 'html')
            if html.attrs.get('lang', '').split('-')[0].lower() != language:
                raise ValueError(f'Idioma HTML incorreto: {current}')
            switches = [link for header in pages[current].root.find('header')
                        for link in header.find('a')
                        if link.text().strip().upper() == switch_label]
            if len(switches) != 1 or urljoin(current, switches[0].attrs.get('href', '')) != other:
                raise ValueError(f'Switch {switch_label} não é recíproco: {current}')
    for url in en_posts:
        if not url.startswith(english):
            raise ValueError(f'Post PT vazou para página EN: {url}')
    if one(pages[base].root, 'p', 'description').text() == one(
            pages[english].root, 'p', 'description').text():
        raise ValueError(f'Descrição inicial não foi localizada: {english}')
    about_pt = urljoin(base, 'sobre/')
    about_en = counterparts[about_pt]
    if one(one(pages[about_pt].root, 'main'), 'h1').text() == one(
            one(pages[about_en].root, 'main'), 'h1').text():
        raise ValueError(f'Título principal não foi localizado: {about_en}')


def configured_public_origin():
    config = (Path(__file__).resolve().parents[2] / '_config.yml').read_text()
    for line in config.splitlines():
        if line.startswith('url:'):
            value = line.partition(':')[2].strip().strip('"\'')
            parsed = urlsplit(value)
            if parsed.scheme == 'https' and parsed.netloc and not parsed.path.strip('/'):
                return parsed.scheme, parsed.netloc
    raise ValueError('Configure a origem HTTPS em _config.yml para os feeds RSS')


def published_feed_url(feed_url, value):
    """Map a canonical public RSS URL onto the local build's HTTP origin."""
    parsed = urlsplit(value)
    expected_scheme, expected_host = configured_public_origin()
    if (parsed.scheme != expected_scheme or parsed.netloc != expected_host
            or parsed.query or parsed.fragment):
        raise ValueError(f'RSS sem URL pública absoluta: {value}')
    local = urlsplit(feed_url)
    return f'{local.scheme}://{local.netloc}{parsed.path}'


def check_feeds(base, pages):
    english = urljoin(base, 'en/')
    for language, home, feed_path in (('pt', base, 'feed.xml'),
                                      ('en', english, 'en/feed.xml')):
        feed_url = urljoin(base, feed_path)
        posts = home_posts(home, pages)
        for page_url, page in pages.items():
            if page_url.startswith(english) != (language == 'en'):
                continue
            discovery = [node for node in page.root.find('link')
                         if 'alternate' in node.attrs.get('rel', '').split()
                         and node.attrs.get('type') == 'application/rss+xml']
            if len(discovery) != 1 or urljoin(page_url, discovery[0].attrs.get('href', '')) != feed_url:
                raise ValueError(f'RSS autodiscovery incorreto: {page_url}')
            header_links = [node for header in page.root.find('header')
                            for node in header.find('a')
                            if urljoin(page_url, node.attrs.get('href', '')) == feed_url]
            if len(header_links) != 1 or not (header_links[0].text() or header_links[0].attrs.get('aria-label')):
                raise ValueError(f'Link RSS acessível ausente no cabeçalho: {page_url}')
        with urlopen(feed_url, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() not in (
                    'application/rss+xml', 'application/xml', 'text/xml'):
                raise ValueError(f'RSS indisponível ou tipo incorreto: {feed_url}')
            try:
                rss = ET.fromstring(response.read())
            except ET.ParseError as error:
                raise ValueError(f'RSS inválido: {feed_url}: {error}') from error
        if rss.tag != 'rss' or rss.get('version') != '2.0':
            raise ValueError(f'Feed não é RSS 2.0: {feed_url}')
        channel = rss.find('channel')
        if channel is None or not channel.findtext('title') or not channel.findtext('description'):
            raise ValueError(f'Canal RSS sem título ou descrição: {feed_url}')
        if channel.findtext('language', '').lower().split('-')[0] != language:
            raise ValueError(f'Idioma RSS incorreto: {feed_url}')
        if published_feed_url(feed_url, channel.findtext('link', '')) != home:
            raise ValueError(f'Link do canal RSS incorreto: {feed_url}')
        entries = {}
        for item in channel.findall('item'):
            link = published_feed_url(feed_url, item.findtext('link', ''))
            if link in entries or link not in posts:
                raise ValueError(f'Item RSS repetido ou de outro idioma: {link}')
            title, timestamp, category = posts[link]
            if item.findtext('title') != title or not item.findtext('description'):
                raise ValueError(f'Item RSS sem título/resumo do card: {link}')
            if not item.findtext('guid') or not item.findtext('category') or not item.findtext('pubDate'):
                raise ValueError(f'Item RSS sem GUID/categoria/data: {link}')
            if item.findtext('guid') != item.findtext('link'):
                raise ValueError(f'GUID RSS não corresponde ao link permanente: {link}')
            if item.findtext('category') not in category.split(' // '):
                raise ValueError(f'Categoria RSS diferente do card: {link}')
            try:
                published = parsedate_to_datetime(item.findtext('pubDate', ''))
                if not published or published.date() != datetime.fromisoformat(timestamp).date():
                    raise ValueError('Data RSS diferente do card')
            except (TypeError, ValueError) as error:
                raise ValueError(f'Data RSS inválida: {link}: {error}') from error
            entries[link] = item
        if set(entries) != set(posts):
            raise ValueError(f'Itens RSS não correspondem aos posts {language}: '
                             f'esperados {sorted(posts)}, encontrados {sorted(entries)}')


def check_font(base, pages):
    styles = {urljoin(page_url, link.attrs.get('href', ''))
              for page_url, page in pages.items()
              for link in page.root.find('link')
              if 'stylesheet' in link.attrs.get('rel', '').split()}
    checked_fonts = set()
    face_families = set()
    font_variables = {}
    body_fonts = []
    for style_url in styles:
        if not style_url.startswith(base):
            continue
        try:
            with urlopen(style_url, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f'CSS local indisponível: {style_url}')
                css_data = response.read()
                check_local_asset(style_url, response.headers.get_content_type(), css_data)
                css = css_data.decode('utf-8')
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f'CSS local indisponível: {style_url}') from error
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            selectors = [part.strip() for part in selector.split(',')]
            if ':root' in selectors:
                font_variables.update(re.findall(r'(--[\w-]+)\s*:\s*([^;]+)', body))
            if 'body' in selectors:
                body_fonts.extend(re.findall(r'font-family\s*:\s*([^;]+)', body))
        for face in re.findall(r'@font-face\s*\{([^{}]*)\}', css, flags=re.I):
            family = re.search(r'font-family\s*:\s*([^;]+)', face, flags=re.I)
            if not family:
                raise ValueError(f'@font-face sem família: {style_url}')
            face_families.add(family.group(1).strip().strip('"\''))
            sources = re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', face)
            if not sources:
                raise ValueError(f'@font-face sem arquivo: {style_url}')
            for source in sources:
                font_url = urljoin(style_url, source)
                if not font_url.startswith(base) or not urlsplit(font_url).path.endswith('.woff2'):
                    raise ValueError(f'Fonte não local WOFF2: {font_url}')
                if font_url in checked_fonts:
                    continue
                try:
                    with urlopen(font_url, timeout=10) as response:
                        if response.status != 200:
                            raise ValueError(f'Fonte indisponível: {font_url}')
                        check_local_asset(font_url, response.headers.get_content_type(), response.read())
                except OSError as error:
                    raise ValueError(f'Fonte indisponível: {font_url}') from error
                checked_fonts.add(font_url)
    if not checked_fonts:
        raise ValueError('Nenhuma fonte WOFF2 local carregada a partir do CSS')
    active_families = set()
    for value in body_fonts:
        variable = re.fullmatch(r'var\(\s*(--[\w-]+)\s*\)', value.strip())
        value = font_variables.get(variable.group(1), '') if variable else value
        active_families.add(value.split(',', 1)[0].strip().strip('"\''))
    if not active_families.intersection(face_families):
        raise ValueError('Fonte declarada mas não utilizada pela página')

def check_theme(base, pages):
    theme_script = urljoin(base, 'assets/js/theme.js')
    for url, page in pages.items():
        buttons = [node for node in page.root.find('button')
                   if node.attrs.get('id') == 'theme-toggle']
        if len(buttons) != 1 or not (buttons[0].text() or
                                    buttons[0].attrs.get('aria-label')):
            raise ValueError(f'Botão acessível #theme-toggle ausente: {url}')
        language = one(page.root, 'html').attrs.get('lang')
        labels = ({
            'data-theme-current-dark': 'Theme: dark',
            'data-theme-current-light': 'Theme: light',
            'data-theme-activate-dark': 'Activate dark mode',
            'data-theme-activate-light': 'Activate light mode',
        } if language == 'en' else {
            'data-theme-current-dark': 'Tema: escuro',
            'data-theme-current-light': 'Tema: claro',
            'data-theme-activate-dark': 'Ativar modo escuro',
            'data-theme-activate-light': 'Ativar modo claro',
        })
        if any(buttons[0].attrs.get(key) != value for key, value in labels.items()):
            raise ValueError(f'Rótulos do tema não correspondem ao idioma: {url}')
        local = [urljoin(url, node.attrs['src']) for node in page.root.find('script')
                 if node.attrs.get('src') and
                 urljoin(url, node.attrs['src']).startswith(base)]
        if local.count(theme_script) != 1:
            raise ValueError(f'Script local do tema ausente ou duplicado: {url}')
    if not shutil.which('node'):
        raise ValueError('Node.js necessário para testar persistência do tema')
    with urlopen(theme_script, timeout=10) as response:
        if response.status != 200 or response.headers.get_content_type() not in (
                'text/javascript', 'application/javascript'):
            raise ValueError(f'Script local indisponível: {theme_script}')
        source = response.read().decode('utf-8')
    result = subprocess.run(['node', str(Path(__file__).with_name('verify_theme.js'))],
                            input=source, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f'Script do tema falhou: {theme_script}: {result.stderr.strip()}')


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
            check_local_asset(url, content_type, data)
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
                icons = [node for node in page.root.find('link')
                         if 'icon' in node.attrs.get('rel', '').split()]
                if (len(icons) != 1 or icons[0].attrs.get('type') != 'image/svg+xml'
                        or urljoin(url, icons[0].attrs.get('href', ''))
                        != urljoin(base, 'assets/images/icon.svg')):
                    raise ValueError('Favicon local ausente ou incorreto')
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
            check_localization(base, pages)
            artwork = post_art_by_title(Path(__file__).resolve().parents[2] / '_posts')
            allowed_art_pages = set()
            for locale, language in ((base, 'pt'), (urljoin(base, 'en/'), 'en')):
                localized = {url: page for url, page in pages.items()
                             if url.startswith(locale)
                             and (language == 'en' or not url.startswith(urljoin(base, 'en/')))}
                allowed_art_pages.update(check_blog(locale, localized, artwork))
                check_off_topic(locale, localized)
                check_tutorial(locale, localized)
                check_about(locale, localized, language, base)
            art_url = urljoin(base, 'assets/images/icon-agents.svg')
            for url, page in pages.items():
                if url not in allowed_art_pages and any(
                        urljoin(url, image.get('src', '')) == art_url for image in page.images):
                    raise ValueError(f'Ícone dos agentes fora dos dois artigos: {url}')
            check_feeds(base, pages)
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
