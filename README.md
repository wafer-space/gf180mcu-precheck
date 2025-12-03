# gf180mcu Precheck

Precheck for wafer.space MPW runs using the gf180mcu PDK

The precheck performs the following checks:

- Ensures there is only one top-level cell and it matches the `--top` argument.
- Checks that the origin is at (0,0), the dbu is 0.001um and the dimensions match the selected slot size.
- Ensures the `gf180mcu_ws_ip__id` cell exists in the layout. Replaces its contents with a QR code of the `--id` argument.
- Checks the density of the layout.
- Ensures there are no zero area polygons in the layout.
- Runs magic DRC.
- Runs KLayout DRC.

## Prerequisites

Install LibreLane by following the Nix-based installation instructions: https://librelane.readthedocs.io/en/latest/getting_started/common/nix_installation/index.html

Clone the PDK with: `make clone-pdk`.

## Run the Precheck

Enable a shell with all tools: `nix-shell`

Export the environment variables:

```
export PDK_ROOT=gf180mcu && export PDK=gf180mcuD
```

Now run the precheck with your layout:

```
python3 precheck.py --input chip_top.gds
```
