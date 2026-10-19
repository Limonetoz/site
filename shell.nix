{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    nodejs
    jekyll
    python3
  ];

  shellHook = ''
    echo "Ambiente Jekyll carregado"
    echo "Execute: jekyll serve --host 127.0.0.1 --port 4000"
    echo "Abra: http://127.0.0.1:4000"
  '';
}
