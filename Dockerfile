# Use Nix as the base image for reproducible builds
FROM nixos/nix:latest

# Image metadata
LABEL org.opencontainers.image.title="gf180mcu-precheck"
LABEL org.opencontainers.image.description="Precheck tool for wafer.space MPW runs using the gf180mcu PDK. Validates GDS layouts before fabrication."
LABEL org.opencontainers.image.usage="docker run --rm --network=none -v \$(pwd)/design:/data ghcr.io/wafer-space/gf180mcu-precheck python precheck.py --input /data/chip_top.gds --top chip_top --dir /data"
LABEL org.opencontainers.image.source="https://github.com/wafer-space/gf180mcu-precheck"

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

# Copy Makefile to use for PDK cloning (uses pinned PDK_TAG version)
COPY Makefile ./

# Clone the PDK into the image using Makefile target
RUN nix develop --accept-flake-config --offline --profile /nix/var/nix/profiles/dev-profile --command make clone-pdk

# Copy the rest of the repository
COPY . .

# Set up environment variables
ENV PDK_ROOT=/workspace/gf180mcu
ENV PDK=gf180mcuD
ENV PATH=/usr/local/bin:$PATH

# Create a helper script to enter the development environment
RUN mkdir -p /usr/local/bin && \
    printf '#!/bin/sh\nexec nix develop --accept-flake-config --offline --profile /nix/var/nix/profiles/dev-profile --command "$@"\n' > /usr/local/bin/dev-shell && \
    chmod +x /usr/local/bin/dev-shell

# Use dev-shell as entrypoint so all commands run in the nix environment
# Users can run: docker run <image> python precheck.py --help
ENTRYPOINT ["dev-shell"]

# Default command: start an interactive bash shell
CMD ["bash"]
