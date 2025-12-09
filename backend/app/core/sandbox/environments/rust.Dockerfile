FROM rust:1.83-slim-bookworm

# Set working directory
WORKDIR /workspace

# Install common utilities and Node.js (for ast-grep)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    vim \
    nano \
    nodejs \
    npm \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep for AST-aware code search
RUN npm install -g @ast-grep/cli

# Install common Rust tools
RUN rustup component add clippy rustfmt && \
    cargo install cargo-watch cargo-edit

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
