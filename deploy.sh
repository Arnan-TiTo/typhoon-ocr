#!/bin/bash
echo "========================================================"
echo "Deploying Typhoon OCR System (Production)"
echo "========================================================"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker is not running or not installed. Please start Docker and try again."
    exit 1
fi

# Pull main repository updates if any (Uncomment if needed)
# git pull origin main

# Build and start containers
echo "Starting containers..."
docker-compose -f docker-compose.prod.yml up -d --build

echo ""
echo "========================================================"
echo "Deployment Successful!"
echo "Gradio UI is running on: http://localhost:7860"
echo "FastApi Server is running on: http://localhost:8000"
echo "========================================================"
