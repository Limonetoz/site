# 4LagDev — blog pessoal

Site estático em português, gerado com Jekyll. O conteúdo fica em Markdown;
o visual usa HTML/Liquid e CSS, sem JavaScript no navegador.

## Estrutura

```text
.github/workflows/pages.yml   Build, testes e publicação no GitHub Pages
_includes/                   Componentes compartilhados
  header.html                Cabeçalho e navegação
  footer.html                Rodapé
_layouts/                    Estrutura das páginas
  default.html               Documento HTML, metadados e CSS
  post.html                  Conteúdo e metadados dos artigos
_posts/                      Artigos em Markdown
assets/
  css/style.css              Estilos do site
  images/icon.svg            Mascote
tests/                       Testes e instruções de execução
  integration/               Verificações HTTP e servidor de teste
_config.yml                  Configuração do Jekyll
index.html                   Conteúdo da página inicial
shell.nix                    Ambiente de desenvolvimento
```

`_site/` e `.jekyll-cache/` são gerados pelo Jekyll e ignorados pelo Git.
Não edite `_site/`: altere os arquivos-fonte.

## Desenvolvimento

Com Nix instalado, na raiz do projeto:

```sh
nix-shell
jekyll serve --host 127.0.0.1 --port 4000
```

Abra `http://127.0.0.1:4000`. O Jekyll processa Liquid e Markdown;
não abra `index.html` diretamente nem sirva os fontes como HTML estático.

## Publicar artigos

Crie `_posts/AAAA-MM-DD-titulo.md` com este cabeçalho:

```yaml
---
layout: post
title: Título do artigo
categories:
  - Tecnologia
permalink: /posts/:year/:month/:day/:title/
---
```

Escreva o conteúdo em Markdown abaixo do cabeçalho. A página inicial lista
os artigos automaticamente. As URLs públicas continuam sob `/posts/`.

## Testar

```sh
nix-shell --run 'jekyll build --baseurl /site'
python3 tests/integration/test_built_site.py _site --base-path /site
```

O prefixo `/site` reproduz o caminho usado no GitHub Pages. Os links para
arquivos estáticos usam `relative_url` para respeitar esse prefixo.
Veja `tests/README.md` para detalhes e testes de um servidor já em execução.

## Deploy

O workflow de GitHub Actions compila, testa e publica o mesmo artefato.
Configure **Settings → Pages → Source → GitHub Actions** para impedir que
a publicação direta da branch contorne os testes. O job de deploy depende
do sucesso dos testes e da validação dessa origem.
