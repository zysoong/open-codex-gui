FROM mcr.microsoft.com/dotnet/sdk:8.0

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

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
