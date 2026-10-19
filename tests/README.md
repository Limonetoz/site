# Testes de integração

`integration/verify_jekyll_http.py` verifica o site gerado via HTTP:

- página inicial sem Liquid ou front matter expostos;
- publicação `2026-10-19-mudanca` listada e acessível;
- layout e conteúdo do post renderizados;
- CSS e imagem respondendo com HTTP 200.

Esse teste usa o post existente como referência; ajuste as expectativas se ele for removido ou renomeado. Não cria nem apaga publicações.

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
