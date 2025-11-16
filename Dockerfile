# Use Nix as the base image for reproducible builds
FROM nixos/nix:latest

# Enable flakes and other experimental features
RUN echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf

# Set working directory
WORKDIR /workspace

# Copy flake files first for better layer caching
COPY flake.nix flake.lock ./

# Build the development environment and cache dependencies
# This creates a profile with all dependencies installed
RUN nix develop --profile /nix/var/nix/profiles/dev-profile --command echo "Dependencies cached"

# Copy the rest of the repository
COPY . .

# Set up environment variables
ENV PDK_ROOT=/workspace/gf180mcu
ENV PDK=gf180mcuD

# Create a helper script to enter the development environment
RUN echo '#!/bin/sh\nexec nix develop --profile /nix/var/nix/profiles/dev-profile --command "$@"' > /usr/local/bin/dev-shell && \
    chmod +x /usr/local/bin/dev-shell

# Default command: enter the development shell
CMD ["nix", "develop", "--profile", "/nix/var/nix/profiles/dev-profile"]
