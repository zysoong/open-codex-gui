FROM eclipse-temurin:21-jdk

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
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Kotlin compiler
RUN curl -s https://get.sdkman.io | bash && \
    bash -c "source /root/.sdkman/bin/sdkman-init.sh && sdk install kotlin"

# Install ast-grep for AST-aware code search
RUN npm install -g @ast-grep/cli

# Install Gradle
RUN curl -L https://services.gradle.org/distributions/gradle-8.5-bin.zip -o gradle.zip && \
    unzip gradle.zip -d /opt && \
    rm gradle.zip && \
    ln -s /opt/gradle-8.5/bin/gradle /usr/local/bin/gradle

# Create workspace structure
RUN mkdir -p /workspace/project_files \
    /workspace/out

# Set environment variables
ENV JAVA_HOME=/opt/java/openjdk
ENV WORKSPACE=/workspace
ENV PATH="/root/.sdkman/candidates/kotlin/current/bin:${PATH}"

# Default command
CMD ["/bin/bash"]
