#!/bin/bash
# Create directory structure for Legacy Industrial Data Platform
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

# Create directories
mkdir -p config
mkdir -p src/core
mkdir -p src/io_protocols
mkdir -p src/data_processing
mkdir -p src/storage
mkdir -p src/reporting
mkdir -p src/automation
mkdir -p tests
mkdir -p scripts
mkdir -p data

# Create __init__.py files
touch src/__init__.py
touch src/core/__init__.py
touch src/io_protocols/__init__.py
touch src/data_processing/__init__.py
touch src/storage/__init__.py
touch src/reporting/__init__.py
touch src/automation/__init__.py
touch tests/__init__.py

echo "Directory structure created successfully."
