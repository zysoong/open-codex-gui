FROM ruby:3.3-slim-bookworm

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
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep for AST-aware code search
RUN npm install -g @ast-grep/cli

# Install common Ruby gems
RUN gem install \
    bundler \
    rake \
    rspec \
    rubocop \
    pry

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV GEM_HOME=/usr/local/bundle
ENV WORKSPACE=/workspace

# Default command
CMD ["/bin/bash"]
