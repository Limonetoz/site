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

## GitHub Actions

O workflow `.github/workflows/pages.yml` roda em cada push para `main`
e também pode ser iniciado manualmente na aba Actions.

1. Confirma que o Pages usa GitHub Actions, em vez do deploy direto da branch.
2. Compila o site com a ação oficial do Jekyll para GitHub Pages.
3. Serve o resultado em HTTP e executa os testes no prefixo de produção.
4. Envia o artefato somente se os testes passarem.
5. Publica esse mesmo artefato em um job com `needs: build_test`.

Se build ou testes falharem, o job de deploy não executa. O workflow precisa
ter permissão `pages: write` para configurar a origem de publicação. Se a
política do repositório impedir essa alteração, selecione **GitHub Actions**
em **Settings → Pages → Build and deployment → Source**.

Para testar um build local sem iniciar um servidor manualmente:

```sh
nix-shell --run 'jekyll build --baseurl /site'
python3 tests/integration/test_built_site.py _site --base-path /site
```

O servidor usa uma porta livre, é encerrado ao final e o processo retorna
código diferente de zero se qualquer verificação falhar.
