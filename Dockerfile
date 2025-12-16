# Use Nix as the base image for reproducible builds
FROM nixos/nix:latest

# Build arguments for version information (populated by CI from flake.lock)
ARG NIX_EDA_REF=""
ARG NIX_EDA_REV=""
ARG LIBRELANE_REF=""
ARG LIBRELANE_REV=""
ARG NIXPKGS_REF=""
ARG NIXPKGS_REV=""
ARG CIEL_REV=""
ARG KLAYOUT_VERSION=""
ARG MAGIC_VERSION=""
ARG PYTHON_VERSION=""

# Image metadata - standard OCI labels
LABEL org.opencontainers.image.title="gf180mcu-precheck"
LABEL org.opencontainers.image.description="Precheck tool for wafer.space MPW runs using the gf180mcu PDK. Validates GDS layouts before fabrication."
LABEL org.opencontainers.image.usage="docker run --rm --network=none -v \$(pwd)/design:/data ghcr.io/wafer-space/gf180mcu-precheck python precheck.py --input /data/chip_top.gds --top chip_top --dir /data"
LABEL org.opencontainers.image.source="https://github.com/wafer-space/gf180mcu-precheck"

# Nix flake input versions - fossi-foundation packages
LABEL org.fossi-foundation.nix-eda.ref="${NIX_EDA_REF}"
LABEL org.fossi-foundation.nix-eda.rev="${NIX_EDA_REV}"
LABEL org.fossi-foundation.ciel.rev="${CIEL_REV}"

# Nix flake input versions - other inputs
LABEL org.librelane.librelane.ref="${LIBRELANE_REF}"
LABEL org.librelane.librelane.rev="${LIBRELANE_REV}"
LABEL org.nixos.nixpkgs.ref="${NIXPKGS_REF}"
LABEL org.nixos.nixpkgs.rev="${NIXPKGS_REV}"

# Runtime tool versions
LABEL space.wafer.klayout.version="${KLAYOUT_VERSION}"
LABEL space.wafer.magic.version="${MAGIC_VERSION}"
LABEL space.wafer.python.version="${PYTHON_VERSION}"

# Enable flakes and configure binary caches
RUN echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf && \
    echo "extra-substituters = https://cache.nixos.org https://nix-cache.fossi-foundation.org" >> /etc/nix/nix.conf && \
    echo "extra-trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY= nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs=" >> /etc/nix/nix.conf

# Set working directory
WORKDIR /workspace

# Copy flake files first for better layer caching
COPY flake.nix flake.lock ./

# Build the development environment and cache dependencies
# This creates a profile with all dependencies installed
# Running python3 --version ensures Python environment is fully cached
RUN nix develop --accept-flake-config --profile /nix/var/nix/profiles/dev-profile --command python3 --version

# Verify the nix environment works offline (no network needed)
# This ensures all dependencies are properly cached in the profile
RUN nix develop --accept-flake-config --offline --profile /nix/var/nix/profiles/dev-profile --command python3 --version

# Extract and store runtime tool versions (captured at build time)
# Using Python to avoid shell quoting issues with JSON
RUN nix develop --accept-flake-config --offline --profile /nix/var/nix/profiles/dev-profile --command python3 -c "\
import json, subprocess, re, pathlib; \
pathlib.Path('/etc/gf180mcu-precheck').mkdir(parents=True, exist_ok=True); \
klayout = subprocess.run(['klayout', '-v'], capture_output=True, text=True).stdout.split()[1]; \
magic = subprocess.run(['magic', '--version'], capture_output=True, text=True).stdout.strip(); \
python = subprocess.run(['python3', '--version'], capture_output=True, text=True).stdout.split()[1]; \
pathlib.Path('/etc/gf180mcu-precheck/tool-versions.json').write_text(json.dumps({'klayout': klayout, 'magic': magic, 'python': python}, indent=2)); \
print(pathlib.Path('/etc/gf180mcu-precheck/tool-versions.json').read_text())"

# Copy Makefile for PDK cloning (version pinned by PDK_TAG in Makefile)
COPY Makefile ./

# Clone the PDK into the image using Makefile target
RUN nix develop --accept-flake-config --offline --profile /nix/var/nix/profiles/dev-profile --command make clone-pdk

# Copy the rest of the repository
COPY . .

# Store flake input versions from build args (if provided)
# Using Python to avoid shell quoting issues with JSON
RUN python3 -c "import json; print(json.dumps({'nix-eda': {'ref': '${NIX_EDA_REF}', 'rev': '${NIX_EDA_REV}'}, 'librelane': {'ref': '${LIBRELANE_REF}', 'rev': '${LIBRELANE_REV}'}, 'nixpkgs': {'ref': '${NIXPKGS_REF}', 'rev': '${NIXPKGS_REV}'}, 'ciel': {'rev': '${CIEL_REV}'}}, indent=2))" > /etc/gf180mcu-precheck/flake-inputs.json

# Set up environment variables
ENV PDK_ROOT=/workspace/gf180mcu
ENV PDK=gf180mcuD
ENV PATH=/usr/local/bin:$PATH

# Copy helper scripts
COPY scripts/dev-shell /usr/local/bin/dev-shell
COPY scripts/version-info /usr/local/bin/version-info
RUN chmod +x /usr/local/bin/dev-shell /usr/local/bin/version-info

# Verify precheck command works by running --help
RUN dev-shell python precheck.py --help

# Use dev-shell as entrypoint so all commands run in the nix environment
# Users can run: docker run <image> python precheck.py --help
ENTRYPOINT ["dev-shell"]

# Default: enter interactive nix develop shell (no CMD needed)
