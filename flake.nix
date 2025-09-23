{
  nixConfig = {
    extra-substituters = [
      "https://nix-cache.fossi-foundation.org"
    ];
    extra-trusted-public-keys = [
      "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
    ];
  };

  inputs = {
    librelane.url = github:librelane/librelane/leo/gf180mcu;
  };

  outputs = {
    self,
    librelane,
    ...
  }: let
    nix-eda = librelane.inputs.nix-eda;
    devshell = librelane.inputs.devshell;
    nixpkgs = nix-eda.inputs.nixpkgs;
    lib = nixpkgs.lib;
  in {
    # Outputs
    legacyPackages = nix-eda.forAllSystems (
      system:
        import nixpkgs {
          inherit system;
          overlays = [nix-eda.overlays.default devshell.overlays.default librelane.overlays.default];
        }
    );
    
    packages = nix-eda.forAllSystems (system: {
      inherit (self.legacyPackages.${system}.python3.pkgs);
    });
    
    devShells = nix-eda.forAllSystems (system: let
      pkgs = (self.legacyPackages.${system});
    in {
      default = lib.callPackageWith pkgs (librelane.createOpenLaneShell {}) {};
    });
  };
}
