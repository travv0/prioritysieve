{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.git
    pkgs.which
    pkgs.pkg-config
    pkgs.libGL
    pkgs.glib.out
    pkgs.fontconfig.lib
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXfixes
    pkgs.xorg.libXrender
    pkgs.xorg.libXrandr
    pkgs.xorg.libXtst
    pkgs.libdrm
    pkgs.xorg.libXi
    pkgs.alsa-lib
    pkgs.xorg.libxshmfence
    pkgs.xorg.libxkbfile
    pkgs.libxkbcommon
    pkgs.freetype.out
    pkgs.dbus.lib
    pkgs.krb5.lib
    pkgs.nss
    pkgs.nspr
    pkgs.gcc.cc
    (pkgs.python311.withPackages (ps: with ps; [
      pip
      setuptools
      wheel
      virtualenv
    ]))
  ];

  shellHook = ''
    export PIP_DISABLE_PIP_VERSION_CHECK=1
    export VIRTUAL_ENV_DISABLE_PROMPT=1
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.libGL}/lib:${pkgs.glib.out}/lib:${pkgs.fontconfig.lib}/lib:${pkgs.xorg.libX11}/lib:${pkgs.xorg.libXcomposite}/lib:${pkgs.xorg.libXdamage}/lib:${pkgs.xorg.libXfixes}/lib:${pkgs.xorg.libXrender}/lib:${pkgs.xorg.libXrandr}/lib:${pkgs.xorg.libXtst}/lib:${pkgs.libdrm}/lib:${pkgs.xorg.libXi}/lib:${pkgs.alsa-lib}/lib:${pkgs.xorg.libxshmfence}/lib:${pkgs.xorg.libxkbfile}/lib:${pkgs.libxkbcommon}/lib:${pkgs.freetype.out}/lib:${pkgs.dbus.lib}/lib:${pkgs.krb5.lib}/lib:${pkgs.nss}/lib:${pkgs.nspr}/lib:$LD_LIBRARY_PATH
    echo "💡 Create a virtualenv with 'python -m venv .venv && source .venv/bin/activate'"
  '';
}
