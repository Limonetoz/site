{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    nodejs
    live-server
  ];

  shellHook = ''
    echo "🌐 Ambiente HTML/CSS carregado"
    echo "Execute: live-server"
  '';
}
