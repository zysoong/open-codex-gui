FROM node:22-slim

# Set working directory
WORKDIR /workspace

# Install common utilities
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    vim \
    nano \
    && rm -rf /var/lib/apt/lists/*

# Install common npm packages globally (including ast-grep for AST-aware code search)
RUN npm install -g \
    typescript \
    ts-node \
    nodemon \
    eslint \
    prettier \
    @ast-grep/cli \
    tsx \
    vitest

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV NODE_ENV=development
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
