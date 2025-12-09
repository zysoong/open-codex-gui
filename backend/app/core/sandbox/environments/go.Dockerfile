FROM golang:1.23-bookworm

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
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep for AST-aware code search
RUN npm install -g @ast-grep/cli

# Install common Go tools
RUN go install golang.org/x/tools/gopls@latest && \
    go install github.com/go-delve/delve/cmd/dlv@latest && \
    go install golang.org/x/lint/golint@latest

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV GOPATH=/go
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
