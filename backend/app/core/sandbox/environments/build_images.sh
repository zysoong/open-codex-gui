#!/bin/bash

# Build all environment images for Open Claude UI sandbox
# Run this script from the environments directory

set -e

echo "=========================================="
echo "Building Open Claude UI Sandbox Images"
echo "=========================================="

# Python environments
echo ""
echo ">>> Building Python 3.11 environment..."
docker build -t openclaudeui-env-python3.11:latest -f python3.11.Dockerfile .

echo ""
echo ">>> Building Python 3.12 environment..."
docker build -t openclaudeui-env-python3.12:latest -f python3.12.Dockerfile .

echo ""
echo ">>> Building Python 3.13 environment..."
docker build -t openclaudeui-env-python3.13:latest -f python3.13.Dockerfile .

# JavaScript/TypeScript environments
echo ""
echo ">>> Building Node.js 20 environment..."
docker build -t openclaudeui-env-node20:latest -f node20.Dockerfile .

echo ""
echo ">>> Building Node.js 22 environment..."
docker build -t openclaudeui-env-nodejs:latest -f nodejs.Dockerfile .

# JVM languages
echo ""
echo ">>> Building Java 21 environment..."
docker build -t openclaudeui-env-java:latest -f java.Dockerfile .

echo ""
echo ">>> Building Kotlin environment..."
docker build -t openclaudeui-env-kotlin:latest -f kotlin.Dockerfile .

echo ""
echo ">>> Building Scala environment..."
docker build -t openclaudeui-env-scala:latest -f scala.Dockerfile .

# Systems languages
echo ""
echo ">>> Building Go 1.23 environment..."
docker build -t openclaudeui-env-go:latest -f go.Dockerfile .

echo ""
echo ">>> Building Rust 1.83 environment..."
docker build -t openclaudeui-env-rust:latest -f rust.Dockerfile .

echo ""
echo ">>> Building C++ (GCC 14) environment..."
docker build -t openclaudeui-env-cpp:latest -f cpp.Dockerfile .

# Scripting languages
echo ""
echo ">>> Building Ruby 3.3 environment..."
docker build -t openclaudeui-env-ruby:latest -f ruby.Dockerfile .

echo ""
echo ">>> Building PHP 8.3 environment..."
docker build -t openclaudeui-env-php:latest -f php.Dockerfile .

# .NET
echo ""
echo ">>> Building .NET 8 environment..."
docker build -t openclaudeui-env-dotnet:latest -f dotnet.Dockerfile .

echo ""
echo "=========================================="
echo "All environment images built successfully!"
echo "=========================================="
echo ""
docker images | grep openclaudeui-env
