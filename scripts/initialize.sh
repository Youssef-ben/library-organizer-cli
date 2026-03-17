#!/bin/bash

echo "Initializing the project..."
echo "--------------------------------"

echo "Cleaning the project..."
rm -rf .venv
rm -rf build
rm -rf dist
rm -rf __pycache__
rm -rf *.egg-info
rm -rf *.pyd
rm -rf *.pyw
rm -rf *.pyz

# create a virtual environment
echo "Creating a virtual environment..."
python -m venv .venv

# activate the virtual environment
echo "Activating the virtual environment..."
if [ -d ".venv/Scripts" ]; then
  # Windows layout
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
else
  # POSIX layout (Linux/macOS)
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# install the dependencies
# pip install -r requirements.txt
echo "Installing dependencies..."
pip install -e ".[dev]"

echo "Upgrading pip..."
python.exe -m pip install --upgrade pip

echo "--------------------------------"
echo "Project initialized successfully."