# `Code4lag_`

[Posts](https://limonetoz.github.io/site/#posts) · [GitHub](https://github.com/Limonetoz/site)

---

<img src="assets/images/icon.svg" width="180" height="180" alt="Mascote do 4LagDev: invasor verde-limão de óculos redondos">

## 4LagDev

`DESENVOLVEDOR`

> Um arquivo pessoal sobre estudos e artigos.

Um histórico do que ando trabalhando: estudos, tecnologia e projetos.
Um blog estático feito com **Jekyll**, **Markdown**, **HTML/Liquid** e **CSS**,
sem JavaScript no navegador.

**[Explorar posts →](https://limonetoz.github.io/site/#posts)**

---

## `01 // posts`

Os artigos ficam em [`_posts/`](_posts/) e aparecem automaticamente na página
inicial, com título, categoria, resumo e data.

Para publicar, crie `_posts/AAAA-MM-DD-titulo.md`:

```yaml
---
layout: post
title: Título do artigo
categories:
  - Tecnologia
permalink: /posts/:year/:month/:day/:title/
---
```

Escreva o conteúdo em Markdown abaixo do cabeçalho. As URLs dos artigos
ficam sob `/posts/`.

## `02 // estrutura`

```text
site/
├── .github/workflows/pages.yml   # Build, testes e deploy
├── _includes/                   # Componentes compartilhados
│   ├── header.html
│   └── footer.html
├── _layouts/                    # Estrutura das páginas
│   ├── default.html
│   └── post.html
├── _posts/                      # Artigos em Markdown
├── assets/
│   ├── css/style.css            # Estilos do site
│   └── images/icon.svg          # Mascote verde-limão
├── tests/
│   ├── integration/             # Testes HTTP
│   └── README.md
├── _config.yml                  # Configuração do Jekyll
├── index.html                   # Página inicial
├── README.md
└── shell.nix                    # Ambiente de desenvolvimento
```

`_site/` e `.jekyll-cache/` são gerados pelo Jekyll e ignorados pelo Git.
**Edite os fontes, não os arquivos de `_site/`.**

## `03 // desenvolvimento`

Com Nix instalado, execute na raiz do projeto:

```sh
nix-shell
jekyll serve --host 127.0.0.1 --port 4000
```

Abra `http://127.0.0.1:4000`.

O Jekyll precisa processar Liquid e Markdown: abrir `index.html` diretamente
ou servir os fontes como HTML estático não gera o blog.

## `04 // testes`

```sh
nix-shell --run 'jekyll build --baseurl /site'
nix-shell --run 'python3 tests/integration/test_built_site.py _site --base-path /site'
```

O prefixo `/site` reproduz o endereço de publicação no GitHub Pages.
Os caminhos de arquivos estáticos usam `relative_url` para respeitá-lo.

As verificações cobrem:

- Páginas e artigos descobertos pelos links, sem depender de um post fixo.
- Links e âncoras locais válidos, respeitando o prefixo `/site`.
- Um título principal e uma área de conteúdo por página.
- Imagens com texto alternativo e link do repositório presente.
- CSS, mascote e demais arquivos vinculados acessíveis por HTTP.

[Instruções completas dos testes →](tests/README.md)

## `05 // publicação`

```text
Build Jekyll
    ↓
Testes HTTP
    ↓
Artefato aprovado
    ↓
Validação da origem do Pages
    ↓
Deploy
```

Configure **Settings → Pages → Source → GitHub Actions** no repositório.
O workflow publica o mesmo artefato que passou pelos testes; o deploy depende
do sucesso dos testes e da validação da origem.

A publicação direta da branch deve estar desativada para não contornar essa
verificação.

---

`© 2026 4LagDev // Site estático`

[Início ↑](#code4lag_)
