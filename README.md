# gf180mcu Precheck

Precheck for wafer.space MPW runs using the gf180mcu PDK

The precheck performs the following checks:

- Ensures there is only one top-level cell and it matches the `--top` argument.
- Checks that the origin is at (0,0), the dbu is 0.001um, the max metal layer, and the dimensions match the selected slot size.
- Ensures the `gf180mcu_ws_ip__id` cell exists in the layout. Replaces its contents with a QR code of the `--id` argument.
- Checks the density of the layout.
- Ensures there are no zero area polygons in the layout.
- Runs KLayout antenna check.
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

> [!NOTE]
> If your top-level cell name does not match the file name, you need to specify it using the `--top` argument:
>
> ```
> python3 precheck.py --input chip_top.gds --top my_top_cell
> ```
>
> If you use a slot size other than 1x1, you need to specify it using the `--slot` argument:
>
> ```
> python3 precheck.py --input chip_top.gds --slot 0p5x0p5
> ```
>
> The valid slot sizes are: `1x1`, `0p5x1`, `1x0p5`, `0p5x0p5`.
