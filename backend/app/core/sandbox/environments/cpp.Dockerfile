FROM gcc:14

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
    cmake \
    make \
    gdb \
    valgrind \
    clang \
    clang-format \
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep for AST-aware code search
RUN npm install -g @ast-grep/cli

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV CC=gcc
ENV CXX=g++
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
