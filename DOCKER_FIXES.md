# Docker Build Fixes - Troubleshooting Guide

## Problem
The error "runc run failed: container process is already dead" typically occurs during the apt-get package installation step.

## Root Causes
1. Network timeout during package download
2. Interactive prompt requiring user input
3. Container resource issues
4. Package dependency conflicts
5. Git context size too large for Railway

## Solutions Applied

### 1. Better Apt Configuration
- Added `DEBIAN_FRONTEND=noninteractive` to prevent prompts
- Added mirror configuration
- Used `-qq` flag for quiet output
- Removed backup copies that can cause issues

### 2. Better Error Handling
- Added `timeout 5` to healthcheck
- Added proper log permissions setup
- Separated pip upgrades into their own layer
- Added start retries for supervisor processes

### 3. Build Optimization
- Optimized Dockerfile for Railway
- Split into smaller, cacheable layers
- Pre-created log files with proper permissions

## Files Changed

### Dockerfile (main)
- Fixed apt-get installation
- Added mirror configuration
- Separated pip upgrade to separate layer
- Better error handling

### supervisord.conf
- Added `startretries=3` to prevent transient failures
- Added `startsecs=3` for graceful startup
- Added `numprocs=1` to prevent duplicate processes
- Set proper log file permissions

### Dockerfile.railway (alternative)
- Optimized specifically for Railway deployment
- Smaller base image modifications
- Cleaner layer structure

## Testing

### Local Build
```bash
# Using Railway-optimized Dockerfile
docker build -t urdu-voicebot -f Dockerfile.railway .

# Test the container
docker run --rm -p 8000:8000 urdu-voicebot
```

### Using Test Script
```bash
chmod +x test-build.sh
./test-build.sh
```

### Build Logs
Run with verbose output:
```bash
docker build --progress=plain --no-cache -f Dockerfile.railway .
```

## For Railway Deployment

### Using Railway CLI
```bash
# Use the railway-optimized Dockerfile
train build -f Dockerfile.railway
```

### Using Direct Upload
```bash
# Push the optimized image
docker build -t yourusername/urdu-voicebot:latest -f Dockerfile.railway .
docker push yourusername/urdu-voicebot:latest

# Then configure Railway to build from this image
```

## Environment Variables

Ensure your `.env.local` or Railway environment variables include:
```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
GROQ_API_KEY=your_groq_key
DEEPGRAM_API_KEY=your_deepgram_key
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net
PUBLIC_BASE_URL=https://your-app.railway.app
```

## Troubleshooting Steps

### 1. If still failing with apt errors
```bash
# Check if voices directory exists locally
ls -la voices/

# If empty, create placeholder
mkdir -p voices_placeholder
touch voices_placeholder/.gitkeep
```

### 2. Reducing build context size
Make sure `.dockerignore` excludes large files:
```
*.iso
*.zip
*.tar.gz
.venv
logs/
```

### 3. Try building with no cache
```bash
docker build --no-cache -f Dockerfile.railway -t urdu-voicebot .
```

### 4. Check Railway build logs
Railway provides build logs in the dashboard. Look for:
- "Reading from dockerfile configuration"
- "Container process is already dead" (to avoid)
- "Successfully built" (success)

## Notes on SIP Trunk
The `SIP_OUTBOUND_TRUNK_ID` environment variable is set to empty in docker-compose.yml:
```yaml
SIP_OUTBOUND_TRUNK_ID=${SIP_OUTBOUND_TRUNK_ID:-}  # Empty since no SIP trunk
```

This means:
- The dashboard can load but SIP dial-out won't work
- The voice agent will not be able to make outbound calls
- The agent will only work for incoming calls (if LiveKit is configured)
- All other features should work (RAG, STT, TTS, dashboard)