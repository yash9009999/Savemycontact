#!/usr/bin/env bash
# Build script for Render deployment
# Installs Tesseract OCR and Python dependencies

set -o errexit

# Install Tesseract OCR
apt-get update && apt-get install -y tesseract-ocr

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
mkdir -p static/uploads
mkdir -p csv_archive
