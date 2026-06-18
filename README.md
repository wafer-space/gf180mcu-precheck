# gf180mcu Precheck

Precheck for wafer.space MPW runs using the gf180mcu PDK.

The precheck performs the following checks:

- Ensures there is only one top-level cell and it matches the `--top` argument.
- Checks that the origin is at (0,0), the dbu is 0.001um, the max metal layer is Metal5, and the dimensions match the selected slot size.
- If the CoB switch is selected:
  - Ensures the `gf180mcu_ws_ip__qrcode_id`, `gf180mcu_ws_ip__shuttle_id`, `gf180mcu_ws_ip__project_id` and `gf180mcu_ws_ip__marker` cells exists in the layout.
  - Ensures there is only one instance of each and their location is as in the project template.
  - Replaces their contents with the value of the `--id` argument.
  - Checks that the pad openings match the pad mask for the selected slot. Additional pad openings are possible.
- Checks the density of the layout.
- Ensures there are no zero area polygons in the layout.
- Runs KLayout antenna check.
- Runs magic DRC.
- Runs KLayout DRC.

## Prerequisites

Install LibreLane by following the Nix-based installation instructions: https://librelane.readthedocs.io/en/latest/getting_started/common/nix_installation/index.html

Enable a shell with all tools: `nix-shell`

Clone the PDK with: `make clone-pdk`.

## Run the Precheck

Enable a shell with all tools: `nix-shell`

Export the environment variables:

```
export PDK_ROOT=gf180mcu && export PDK=gf180mcuD
```

Now run the precheck with your layout (supported file formats are `.gds`, `.gds.gz`, `.oas`):

```
python3 precheck.py --input chip_top.gds
```

You can also specify where to save the output layout:

```
python3 precheck.py --input chip_top.gds --output chip_top.oas
```

> [!NOTE]
> If your top-level cell name does not match the file name, you need to specify it using the `--top` argument:
>
> ```
> python3 precheck.py --input chip_top.gds --top my_top_cell
> ```

> [!NOTE]
> If you use a slot size other than 1x1, you need to specify it using the `--slot` argument:
>
> ```
> python3 precheck.py --input chip_top.gds --slot 0p5x0p5
> ```
> The valid slot sizes are: `1x1`, `0p5x1`, `1x0p5`, `0p5x0p5`.

> [!NOTE]
>
> If you want to use the CoB (Chip-On-Board) packaging option, pass `--cob`.
>
> ```
> python3 precheck.py --input chip_top.gds --cob
> ```

> [!NOTE]
> To speed up KLayout DRC check, you can change the number of threads vs the number of workers.
> A high number of workers increases RAM usage, but can significantly improve the performance.
> workers * threads should equal the available hardware threads for a best possible utilization.
>
> ```
> python3 precheck.py --input chip_top.gds --threads 1 --workers max
> ```
