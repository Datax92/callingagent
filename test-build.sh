#!/bin/bash

# Test Docker build with verbose output
echo "=== Testing Docker Build ==="

# Clean up any previous builds
docker system prune -f 2>/dev/null || true

# Build with detailed output
docker build \
  -t urdu-voicebot-test \
  --progress=plain \
  --no-cache \
  -f Dockerfile .

# Test the container
echo "=== Testing Container ==="
docker run --rm urdu-voicebot-test \
  supervisorctl status

echo "=== Build Complete ==="