{
  description = "Configure the 8BitDo Retro 87 keyboard and Retro R8 mouse on Linux";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      mkPackage = pkgs: pkgs.python3Packages.buildPythonApplication {
        pname = "eightbitdo";
        version = "0.1.0";
        pyproject = true;
        src = pkgs.lib.fileset.toSource {
          root = ./.;
          fileset = pkgs.lib.fileset.unions [ ./pyproject.toml ./README.md ./eightbitdo ./tests ./udev ];
        };
        build-system = [ pkgs.python3Packages.setuptools ];
        postInstall = ''
          install -Dm644 udev/70-8bitdo.rules $out/lib/udev/rules.d/70-8bitdo.rules
          install -Dm644 eightbitdo/ui/eightbitdo.desktop $out/share/applications/eightbitdo.desktop
          install -Dm644 eightbitdo/ui/icon.svg $out/share/icons/hicolor/scalable/apps/eightbitdo.svg
        '';
        checkPhase = ''
          runHook preCheck
          python -m unittest discover -s tests -v
          runHook postCheck
        '';
        meta = with pkgs.lib; {
          description = "Configure the 8BitDo Retro 87 keyboard and Retro R8 mouse";
          mainProgram = "8bitdo-cfg";
          platforms = platforms.linux;
        };
      };
    in
    {
      packages = forAll (pkgs: rec {
        eightbitdo = mkPackage pkgs;
        default = eightbitdo;
      });

      apps = forAll (pkgs: rec {
        eightbitdo = { type = "app"; program = "${mkPackage pkgs}/bin/8bitdo-cfg"; };
        default = eightbitdo;
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (ps: [ ps.pytest ])) ];
          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH
            alias 8bitdo-cfg='python3 -m eightbitdo'
          '';
        };
      });

      # NixOS module: installs the tool, its udev rule and the menu entry.
      #   imports = [ eightbitdo.nixosModules.default ];
      #   hardware.eightbitdo.enable = true;
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          pkg = self.packages.${pkgs.stdenv.hostPlatform.system}.eightbitdo;
        in {
          options.hardware.eightbitdo.enable = lib.mkEnableOption "8BitDo Retro 87 / R8 configuration tool and udev rule";
          config = lib.mkIf config.hardware.eightbitdo.enable {
            environment.systemPackages = [ pkg ];
            services.udev.packages = [ pkg ];
          };
        };
    };
}
