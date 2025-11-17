# Use Nix as the base image for reproducible builds
FROM nixos/nix:latest

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
RUN nix develop --accept-flake-config --profile /nix/var/nix/profiles/dev-profile --command echo "Dependencies cached"

# Copy the rest of the repository
COPY . .

# Set up environment variables
ENV PDK_ROOT=/workspace/gf180mcu
ENV PDK=gf180mcuD
ENV PATH=/usr/local/bin:$PATH

# Create a helper script to enter the development environment
RUN mkdir -p /usr/local/bin && \
    echo '#!/bin/sh\nexec nix develop --accept-flake-config --profile /nix/var/nix/profiles/dev-profile --command "$@"' > /usr/local/bin/dev-shell && \
    chmod +x /usr/local/bin/dev-shell

# Default command: enter the development shell
CMD ["nix", "develop", "--accept-flake-config", "--profile", "/nix/var/nix/profiles/dev-profile"]
