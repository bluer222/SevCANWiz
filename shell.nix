{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = [ (pkgs.python3.withPackages (p: [ p.pyside6 ])) ];
  QT_QPA_PLATFORM_PLUGIN_PATH = "${pkgs.qt6.qtbase}/lib/qt-6/plugins/platforms";
}
