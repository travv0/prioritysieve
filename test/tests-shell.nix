{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = with pkgs; [
    git
    which
    pkg-config
    libGL
    libGLU
    libxkbcommon
    xorg.libX11
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXfixes
    xorg.libXext
    xorg.libXrender
    xorg.libXrandr
    xorg.libXtst
    xorg.libXi
    libdrm
    xorg.libXcursor
    xorg.libXinerama
    xorg.libxshmfence
    xorg.libxkbfile
    alsa-lib
    glib
    fontconfig
    freetype
    dbus
    krb5
    nss
    nspr
    stdenv.cc.cc.lib
    (python311.withPackages (ps: with ps; [
      pip
      setuptools
      wheel
      pyqt6
      pyqt6-sip
    ]))
  ];

  shellHook = ''
    export QT_QPA_PLATFORM=offscreen
    export QTWEBENGINE_DISABLE_SANDBOX=1
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.libGL}/lib:${pkgs.libGLU}/lib:${pkgs.libxkbcommon}/lib:${pkgs.xorg.libX11}/lib:${pkgs.xorg.libXcomposite}/lib:${pkgs.xorg.libXdamage}/lib:${pkgs.xorg.libXfixes}/lib:${pkgs.xorg.libXext}/lib:${pkgs.xorg.libXrender}/lib:${pkgs.xorg.libXrandr}/lib:${pkgs.xorg.libXtst}/lib:${pkgs.xorg.libXi}/lib:${pkgs.libdrm}/lib:${pkgs.xorg.libXcursor}/lib:${pkgs.xorg.libXinerama}/lib:${pkgs.xorg.libxshmfence}/lib:${pkgs.xorg.libxkbfile}/lib:${pkgs.alsa-lib}/lib:${pkgs.glib.out}/lib:${pkgs.fontconfig.lib}/lib:${pkgs.freetype.out}/lib:${pkgs.dbus.lib}/lib:${pkgs.krb5.lib}/lib:${pkgs.nss}/lib:${pkgs.nspr}/lib:$LD_LIBRARY_PATH
  '';
}
