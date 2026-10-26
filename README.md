# `Code4lag_`

[Posts](https://limonetoz.github.io/site/#posts) · [English](https://limonetoz.github.io/site/en/) · [RSS](https://limonetoz.github.io/site/feed.xml) · [Tutorial](https://limonetoz.github.io/site/posts/tutorial/) · [Sobre](https://limonetoz.github.io/site/sobre/) · [GitHub](https://github.com/Limonetoz/site)

---

<img src="assets/images/icon.svg" width="180" height="180" alt="Mascote do 4LagDev: invasor verde-limão de óculos redondos">

## 4LagDev

`DESENVOLVEDOR`

> Um arquivo pessoal sobre estudos e artigos.

Um histórico do que ando trabalhando: estudos, tecnologia e projetos.
Um blog estático feito com **Jekyll**, **Markdown**, **HTML/Liquid** e **CSS**,
com JavaScript leve para alternar o tema e buscar posts no próprio navegador.

**[Explorar posts →](https://limonetoz.github.io/site/#posts)**

---

## `01 // posts`

Os artigos ficam em [`_posts/`](_posts/) e aparecem automaticamente na página
inicial, dedicada ao feed de posts, com título, categoria, resumo e data.
O mascote identifica o site ao lado de `Code4lag_` no cabeçalho.

Para publicar, crie `_posts/AAAA-MM-DD-titulo.md`:

```yaml
---
layout: post
title: Título do artigo
description: Resumo editorial do artigo em até 160 caracteres
lang: pt
translation_key: AAAA-MM-DD-identificador
categories:
  - Tecnologia
permalink: /posts/:year/:month/:day/:title/
---
```

Escreva o conteúdo em Markdown abaixo do cabeçalho. As URLs dos artigos
ficam sob `/posts/`. Para a versão inglesa, crie outro arquivo em `_posts/`
com a mesma data e `translation_key`, `lang: en`, título, descrição e corpo traduzidos,
e `permalink: /en/posts/:year/:month/:day/:title/`. O botão PT/EN leva à
versão correspondente do artigo; publique as duas versões juntas.
As páginas de interface compartilham os textos em `_data/i18n.yml`.

O cabeçalho oferece RSS em cada idioma: [`/feed.xml`](https://limonetoz.github.io/site/feed.xml)
para português e [`/en/feed.xml`](https://limonetoz.github.io/site/en/feed.xml)
para inglês. Assine o endereço desejado em um leitor RSS que ofereça alertas;
o feed publica novos artigos, mas o site não envia notificações push por conta própria.

A busca no cabeçalho pesquisa títulos, resumos e categorias dos posts no idioma
da página. O Jekyll gera `search.json` no build; o navegador consulta esse índice
localmente, sem serviço externo. Sem JavaScript, o link Posts permanece disponível.
Em telas menores, a navegação fica em um menu; a busca continua visível.
Os links Sobre e GitHub do site ficam no rodapé para manter o cabeçalho compacto.

Para incluir um artigo na subcategoria **Off-topic**, use
`categories: [off-topic]` no cabeçalho. A página
[`/posts/off-topic/`](https://limonetoz.github.io/site/posts/off-topic/)
lista apenas esses artigos e mostra uma mensagem quando não houver nenhum.
Para incluir um artigo em **Tutorial**, use `categories: [tutorial]`.
A página [`/posts/tutorial/`](https://limonetoz.github.io/site/posts/tutorial/)
lista apenas os tutoriais e também mostra uma mensagem quando estiver vazia.
O botão de tema no cabeçalho acompanha a preferência do sistema até a primeira
escolha manual; depois, guarda essa escolha no navegador.

A página [Sobre](https://limonetoz.github.io/site/sobre/) reúne os perfis
GitHub, Codeberg e LinkedIn com os ícones das respectivas plataformas. O símbolo do
GitHub foi extraído do [perfil no GitHub](https://github.com/Limonetoz/) e o
do Codeberg do [SVG oficial](https://codeberg.org/assets/img/svg/cb-logo.svg).
Os ícones [in] são PNGs do [pacote oficial do LinkedIn](https://brand.linkedin.com/downloads):
`in-logo/InBug-White.png` (SHA-256 `ed22a5ab46c171e3449708ff34923de7298da00ac204c7f85444db05bf888791`)
para o tema escuro e `in-logo/LI-In-Bug.png` (SHA-256
`3c0149f26168b5fe0f43e68664abe40341a6443b3cd435d18a73e12f64f8b600`)
para o tema claro. São usados apenas para identificar o link do perfil.
As marcas pertencem às respectivas plataformas; esses arquivos não representam
uma licença de uso das marcas fora deste contexto de identificação de links.
A ilustração do artigo sobre agentes reaproveita `assets/images/icon.svg` e
mostra no notebook o símbolo do Hermes Agent. O símbolo foi incorporado de
`website/static/img/logo-dark.png` do repositório NousResearch/hermes-agent,
revisão `d923a5eb` (SHA-256 do PNG original:
`b76ed32dd5ffdf842db696dc6dc0992529acfe12903ec1b2128251a41dfd31d2`).
O site usa [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) como fonte
padrão, hospedada localmente em pesos 400, 500 e 700. Os arquivos de fonte
seguem a licença [SIL Open Font License](assets/fonts/OFL.txt), distribuída
junto deles.

## `02 // estrutura`

```text
site/
├── .github/workflows/pages.yml   # Build, testes e deploy
├── _data/i18n.yml              # Textos de interface PT/EN
├── _includes/                   # Componentes compartilhados
│   ├── header.html
│   ├── footer.html
│   └── post-categories.html     # Rótulos compartilhados de categorias
├── _layouts/                    # Estrutura das páginas
│   ├── default.html
│   └── post.html
├── _posts/                      # Artigos em Markdown
├── posts/off-topic/index.html   # Arquivo da subcategoria Off-topic
├── posts/tutorial/index.html    # Arquivo da categoria Tutorial
├── sobre/index.html             # Página de perfis e links
├── en/                          # Páginas e feed em inglês
├── feed.xml                     # RSS em português
├── assets/
│   ├── css/style.css            # Estilos do site
│   ├── js/theme.js              # Alternância de tema
│   ├── js/search.js             # Busca local no cabeçalho
│   ├── js/menu.js               # Menu responsivo de navegação
│   ├── images/                  # Mascote e ícones dos perfis
│   └── fonts/                   # JetBrains Mono WOFF2 e OFL.txt
├── tests/
│   ├── integration/             # Testes HTTP
│   └── README.md
├── _config.yml                  # Configuração do Jekyll
├── search.json                  # Índice de busca gerado com Liquid
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
- Arquivos Off-topic e Tutorial filtrados e com estado vazio; tema persistido.
- Página Sobre, três perfis com ícones locais e JetBrains Mono, também em `/site`.
- Páginas e posts PT/EN com alternância recíproca e arquivos separados por idioma.
- Feeds RSS 2.0 por idioma, XML válido, metadados e itens correspondentes aos posts.

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
