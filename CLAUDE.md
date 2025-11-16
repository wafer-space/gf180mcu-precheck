# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a precheck tool for wafer.space MPW runs using the gf180mcu PDK. The tool validates GDS layouts before fabrication by performing design rule checks, density verification, and ID generation.

## Build and Run Commands

### Initial Setup

#### Option 1: Using Nix (Recommended for Development)
```bash
# Clone the PDK (required before first run)
make clone-pdk

# Enter development environment with all tools
nix-shell

# Set required environment variables (must be done in every shell session)
export PDK_ROOT=gf180mcu
export PDK=gf180mcuD
```

#### Option 2: Using Docker
```bash
# Pull the pre-built container from GitHub Container Registry
docker pull ghcr.io/wafer-space/gf180mcu-precheck:latest

# Or build locally
docker build -t gf180mcu-precheck .

# Run the container with your layout mounted
docker run -v $(pwd)/my_design:/data ghcr.io/wafer-space/gf180mcu-precheck:latest \
  dev-shell python precheck.py --input /data/chip_top.gds --top chip_top --dir /data
```

### Running the Precheck
```bash
# Basic usage
uv run python precheck.py --input <layout_file> --top <top_cell_name>

# With custom ID (default is "FFFFFFFF")
uv run python precheck.py --input chip_top.gds --top chip_top --id ABCD1234

# Specify output directory
uv run python precheck.py --input chip_top.gds --top chip_top --dir ./output
```

### Running Individual KLayout Scripts
```bash
# Check top-level cell
uv run python scripts/klayout/check_top.py <input.gds> --top <cell_name>

# Generate ID QR code
uv run python scripts/klayout/generate_id.py <input.gds> <output.gds> --id <id_string>

# Read layout and convert to GDS
uv run python scripts/klayout/read_layout.py <input> <output.gds>
```

## Architecture

### Core Components

**precheck.py**: Main entry point that orchestrates the precheck flow using LibreLane's SequentialFlow framework. Defines custom KLayout steps and integrates them with standard LibreLane steps.

**PrecheckFlow**: Sequential flow that executes the following steps:
1. `ReadLayout` - Converts input layout (GDS, GDS.GZ, or OAS) to GDS format
2. `CheckTopLevel` - Verifies exactly one top-level cell exists and matches DESIGN_NAME
3. `GenerateID` - Replaces `gf180mcu_ws_ip__id` cell contents with QR code
4. `KLayout.Density` - Calculates layout density metrics
5. `Checker.KLayoutDensity` - Validates density against requirements
6. `Magic.DRC` - Runs Magic DRC checks
7. `Checker.MagicDRC` - Validates Magic DRC results
8. `KLayout.DRC` - Runs KLayout DRC checks (for filler cells)
9. `Checker.KLayoutDRC` - Validates KLayout DRC results

### Custom LibreLane Steps

All custom steps inherit from `KLayoutStep` and implement the LibreLane Step interface:

- **ReadLayout** (id: `KLayout.ReadLayout`): Uses `read_layout.py` script to normalize input formats to GDS
- **CheckTopLevel** (id: `KLayout.CheckTopLevel`): Uses `check_top.py` to validate top-level cell name
- **GenerateID** (id: `KLayout.GenerateID`): Uses `generate_id.py` to insert QR-coded ID into designated cell

### KLayout Scripts

Located in `scripts/klayout/`:
- `read_layout.py`: Reads various layout formats and outputs GDS
- `check_top.py`: Validates single top-level cell with correct name
- `generate_id.py`: Generates QR code PCell and replaces ID cell contents
- `qrcode_library/`: Custom KLayout PCell library for generating QR codes on Metal3 layer

### PDK-Specific Configuration

The precheck is hardcoded for `gf180mcuD` PDK variant. Key configurations in `precheck.py:main()`:

- **MAGIC_GDS_FLATGLOB**: Critical list of cell patterns that must be flattened during Magic DRC to prevent false positives. Includes:
  - I/O cells (`*_CDNS_*`)
  - Filler cells that need flattening to form special layers (`COMP_fill_cell`, `Poly2_fill_cell`)
  - Foundry SRAM cells (various patterns like `*$$*`, `M1_N*`, `M2_M1*`, etc.)
  - Additional cells with 3.3V devices that trigger DUALGATE warnings (`dcap_103*`, `din_*`, `mux821_*`, etc.)

This flatglob list is essential for successful DRC runs and has been carefully tuned for the gf180mcu PDK.

## Environment Requirements

- **Nix**: Development environment managed via `flake.nix`
- **LibreLane**: EDA flow framework (from specific branch: `github:librelane/librelane/leo/gf180mcu`)
- **Python packages**: qrcode, pillow, click, pya (KLayout Python API)
- **EDA tools**: KLayout, Magic (provided by nix-eda)
- **PDK**: gf180mcu cloned into `./gf180mcu/` directory

## Important Constraints

- Only supports `gf180mcuD` PDK variant (exits with error for other variants)
- Requires `gf180mcu_ws_ip__id` cell in the layout (142.8um × 142.8um)
- ID cell must have exact dimensions matching QR code output (21×21 pixels at 6.8um/pixel)
- Input layout must have exactly one top-level cell
- PDK_ROOT and PDK environment variables must be set correctly

## Development Notes

- All Python code execution should use `uv run python` per global configuration
- The precheck writes intermediate results to a design directory (default: current directory)
- Flow execution creates timestamped run directories within the design directory
- QR code uses octagon-shaped pixels on Metal3 layer for aesthetic appearance
- PCell context information is explicitly stripped from output GDS to avoid downstream issues

## Docker Container

A Docker container is automatically built and published to GitHub Container Registry on every push to main and on tagged releases.

**Container Features:**
- Based on `nixos/nix:latest` with flakes enabled
- Pre-cached Nix development environment with all dependencies
- PDK must be cloned or mounted at runtime (not included in image to reduce size)
- Environment variables PDK_ROOT and PDK pre-configured

**GitHub Actions Workflow:**
- Workflow: `.github/workflows/docker-publish.yml`
- Triggers: pushes to main, version tags (v*), pull requests, manual dispatch
- Tags: `latest` for main branch, semantic versions for tags, SHA-based tags for commits
- Uses Docker buildx with GitHub Actions cache for faster builds
