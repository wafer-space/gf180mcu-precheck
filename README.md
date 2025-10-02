# gf180mcu Precheck

Precheck for wafer.space MPW runs using the gf180mcu PDK

> [!CAUTION]
> This repository is still WIP.

## Prerequisites

Install LibreLane by following the Nix-based installation instructions: https://librelane.readthedocs.io/en/latest/getting_started/common/nix_installation/index.html

## Run the Precheck

Enable a shell with all tools: `nix-shell`

Now run the precheck with your layout:

```
python3 precheck.py --input chip_top.gds --top chip_top
```
