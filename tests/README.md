# Testes de integração

`integration/verify_jekyll_http.py` verifica o site gerado via HTTP:

- páginas sem Liquid ou front matter expostos;
- links internos descobertos automaticamente a partir da página inicial;
- arquivos vinculados respondendo com HTTP 200, sem redirecionamentos;
- links respeitando o prefixo do site e âncoras existentes;
- exatamente um `h1` e um `main` por página;
- imagens com atributo `alt` e folha de estilos presente;
- link do repositório e proteção `noopener` em links que abrem nova aba;
- cards de posts com título, resumo e link para a página publicada; se não houver
  artigos, mensagem explícita de lista vazia;
- título, categoria e data ISO/data visível consistentes entre card e artigo;
- artigo com conteúdo, título do documento, descrição, navegação e retorno para `#posts`.
- botão acessível `#theme-toggle` em todas as páginas, script local e execução
  isolada em Node.js: tema inicial conforme `prefers-color-scheme`, preferência
  `site-theme` prevalecendo e alternância persistida após clique;
- navegação Off-topic para `/posts/off-topic/`, arquivo com somente os posts
  categorizados `off-topic` (links descobertos dos cards da página inicial)
  ou mensagem explícita quando vazio;
- navegação Tutorial para `/posts/tutorial/`, arquivo com somente os posts
  categorizados `tutorial` ou mensagem explícita quando vazio;
- navegação Sobre, página em `/sobre/`, três links de perfil exatos (GitHub,
  Codeberg e LinkedIn), seguros e acessíveis, com ícones locais SVG e PNG por HTTP;
- JetBrains Mono como fonte primária no CSS, definida em `@font-face` por
  arquivo WOFF2 local servido por HTTP em `/` e `/site`.
- `/en/`, `/en/sobre/`, arquivos `/en/posts/…/` e posts em inglês com
  `html lang` correto, títulos/conteúdo localizados e switch PT/EN no cabeçalho
  apontando de volta à página equivalente (inclusive artigo);
- feeds RSS 2.0 `/feed.xml` e `/en/feed.xml`, descobertos por `<link>` em cada
  página e acessíveis no cabeçalho: HTTP/MIME/XML, idioma, metadados e itens
  idênticos aos posts da listagem de cada idioma, sem vazamento entre idiomas.

As comparações usam os próprios cards renderizados, sem fixar título, data, URL
ou frases de uma publicação. Um blog sem posts é válido se mostrar o estado
vazio. Não cria nem apaga publicações. Links externos não são consultados,
evitando falhas de rede de terceiros no deploy. Ele verifica a estrutura do
HTML, mas não substitui a revisão visual de responsividade e contraste.

Na raiz do projeto, inicie o servidor:

```sh
nix-shell --run 'jekyll serve --host 127.0.0.1 --port 4000'
```

Em outro terminal, também na raiz:

```sh
nix-shell --run 'python3 tests/integration/verify_jekyll_http.py http://127.0.0.1:4000'
```

O script retorna código 0 quando todas as verificações passam e 1 quando alguma falha. O servidor precisa estar em execução.

A pasta `tests/` é excluída do site publicado por `_config.yml`.

## GitHub Actions

O workflow `.github/workflows/pages.yml` roda em cada push para `main`
e também pode ser iniciado manualmente na aba Actions.

1. Compila o site com a ação oficial do Jekyll para GitHub Pages.
2. Serve o resultado em HTTP e executa os testes no prefixo de produção.
3. Valida fixtures isoladas das categorias Off-topic e Tutorial com e sem artigos, em `/` e `/site`.
4. Envia o artefato somente se os testes passarem.
5. Confirma que o Pages usa GitHub Actions, em vez do deploy direto da branch.
6. Publica esse mesmo artefato em um job com `needs: [build_test, pages_source]`.

Se build, testes ou validação da origem falharem, o job de deploy não executa.
A origem precisa ser selecionada uma vez, manualmente: **Settings → Pages →
Build and deployment → Source → GitHub Actions**. O workflow não altera essa
configuração administrativa. Enquanto a origem continuar sendo a branch,
o deploy automático antigo pode publicar sem respeitar estes testes.

Para testar um build local sem iniciar um servidor manualmente:

```sh
nix-shell --run 'jekyll build --baseurl /site'
nix-shell --run 'python3 tests/integration/test_built_site.py _site --base-path /site'
```

O servidor usa uma porta livre, é encerrado ao final e o processo retorna
código diferente de zero se qualquer verificação falhar.

Para provar filtragem e estado vazio sem editar `_posts/`, rode a fixture
isolada (requer Jekyll, Node.js e `TMPDIR`):

```sh
nix-shell --run 'python3 tests/integration/test_off_topic_fixture.py'
```

Ela copia o código-fonte para `$TMPDIR`, adiciona posts PT/EN correspondentes
`off-topic`, `tutorial` e `estudos` com datas passadas, compila e testa tanto
`/` quanto `/site/`, inclusive arquivos e feeds de cada idioma.
Depois remove somente os posts da cópia, recompila e verifica o estado vazio;
também executa as verificações HTTP/alt/links e o teste do script de tema.
Não cria nem altera posts no repositório.

Para provar que a validação de títulos rejeita artefatos quebrados sem tocar
nos posts, crie uma cópia temporária do build e altere apenas o HTML gerado
(entre em `nix-shell` antes do bloco se `python3` não existir no sistema):

```sh
fixture=$(mktemp -d "${TMPDIR:?Defina TMPDIR para uma pasta temporária}/jekyll-negative-XXXXXX")
cp -a _site/. "$fixture/"
python3 - "$fixture" <<'PY'
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import sys

sys.path.insert(0, str(Path('tests/integration').resolve()))
from verify_jekyll_http import Page

root = Path(sys.argv[1])
home = Page()
home.feed((root / 'index.html').read_text())
posts = next(node for node in home.root.find('section') if node.attrs.get('id') == 'posts')
card = next(posts.find('article'))
heading = next(node for node in card.find() if node.tag in ('h2', 'h3', 'h4'))
href = next(heading.find('a')).attrs['href']
path = urlsplit(urljoin('https://example.test/site/', href)).path.removeprefix('/site/')
post = root / path
if post.is_dir():
    post /= 'index.html'
html = post.read_text()
assert '<h1>' in html
post.write_text(html.replace('<h1>', '<h1>Incompatível ', 1))
PY
nix-shell --run "python3 tests/integration/test_built_site.py '$fixture' --base-path /site"
# Esperado: código 1, com "Título do card difere do post".
```

A fixture fica fora do repositório; o build original continua intacto.
