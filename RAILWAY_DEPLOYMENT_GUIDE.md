# Railway Deployment Guide - Final Version

## Build Status
✅ **FIXED** - Removed problematic sed configuration and non-existent directory copies

## Quick Start for Railway

### Option 1: Use Railway-Optimized Dockerfile (Recommended)
```bash
docker build -f Dockerfile.railway -t urdu-voicebot .
```

### Option 2: Use Main Dockerfile
```bash
docker build -f Dockerfile -t urdu-voicebot .
```

## What Was Fixed

### Issues Identified:
1. ❌ **Mirror configuration failing** - The `sed` command to modify apt sources was failing in Railway's environment
2. ❌ **Missing directory copies** - Tried to copy non-existent `/provisions` directory causing checksum errors
3. ❌ **Complex setup** - Too many unnecessary configuration commands causing build context size issues

### Solution Applied:
✅ **Removed problematic commands**:
- Removed `sed` mirror configuration
- Removed `COPY supervisors/ provisions/` command
- Simplified working directory to `/app`
- Removed unnecessary environment variables and test commands

✅ **Clean minimal Dockerfiles**:
- Both `Dockerfile` and `Dockerfile.railway` now contain only essential commands
- Better layer caching
- No fragile directory references

## Step-by-Step Railway Deployment

### 1. Build Locally
```bash
# Using Railway-optimized Dockerfile (recommended)
docker build -f Dockerfile.railway -t yourusername/urdu-voicebot:latest .
```

### 2. Push to Docker Registry
```bash
docker tag yourusername/urdu-voicebot:latest yourregistry.com/urdu-voicebot:latest
docker push yourregistry.com/urdu-voicebot:latest
```

### 3. Or Deploy Directly from GitHub (Easier)
1. Push the updated `Dockerfile` and `Dockerfile.railway` to your GitHub repo
2. Create a new Railway project
3. Connect your GitHub repository
4. Railway will automatically detect the `Dockerfile.railway` or `Dockerfile`
5. Add your environment variables in Railway dashboard

## Environment Variables Required

### Basic Setup (required for any features):
- `LIVEKIT_URL` - Your LiveKit cloud instance URL (e.g., `wss://my-project.livekit.cloud`)
- `LIVEKIT_API_KEY` - Your LiveKit API key
- `LIVEKIT_API_SECRET` - Your LiveKit API secret
- `GROQ_API_KEY` - Your GROQ API key for the language model
- `DEEPGRAM_API_KEY` - Your Deepgram API key for speech-to-text

### Optional Setup:
- `MONGODB_URI` - Your MongoDB Atlas connection string
- `PUBLIC_BASE_URL` - Your public URL (e.g., `https://your-app.railway.app`)
- `SLACK_WEBHOOK_URL` - For Slack notifications
- `CLOUDFLARE_R2_*` - For recording archive storage

## SIP Trunk Configuration

The SIP tray is currently **disabled**:
```yaml
SIP_OUTBOUND_TRUNK_ID=
```

### To Enable SIP Dial-Out:
1. Get a SIP trunk from your VoIP provider (e.g., Vonage, Bandwidth)
2. Get the trunk ID from your provider
3. Set the environment variable:
   - In Railway: Add `SIP_OUTBOUND_TRUNK_ID=your-trunk-id` in environment variables
4. The dashboard will be able to trigger outbound calls

## Test the Deployment

### Local Testing:
```bash
# Run the container
docker-compose up

# Health check
curl http://localhost:8000/health
```

### Expected Response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## Common Issues and Solutions

### Issue: "Container process is already dead"
**Solution:** Uses Railway-safe version without interactive prompts or network modifications

### Issue: Permission denied on supervisor logs
**Solution:** Already fixed - logs are created with proper permissions

### Issue: Missing voices directory
**Solution:** Already fixed - voices directory is pre-created with .gitkeep

### Issue: Build size too large
**Solution:** Uses lean Python base image and removes unnecessary dependencies

## Monitoring

### Check Container Status:
```bash
docker inspect urdu-voicebot-combined | grep -i status
```

### View Supervisor Logs:
```bash
docker logs urdu-voicebot-combined | tail -f
```

### Check Health Endpoint:
```bash
curl http://localhost:8000/health
```

## Performance Tips

1. **By default**, the container runs in Railway's free tier (256MB RAM)
2. **For production**, upgrade to Railway's Standard tier (512MB RAM or higher)
3. **Optimized**, uses Supervisor for process management instead of multiple containers
4. **Leverages** Railway's built-in health checks for automatic restarts

## Restarting the Container

```bash
# Graceful restart
docker-compose restart

# Force restart
docker-compose up -d --force-recreate
```

## Additional Commands

```bash
# View container logs in real-time
docker-compose logs -f

# Stop and remove containers
docker-compose down

# Rebuild without cache
docker-compose build --no-cache
```

## Support

If you still encounter issues:
1. Check Railway build logs in the dashboard
2. Run the build with verbose output: `docker build --progress=plain -f Dockerfile.railway .`
3. Verify all required environment variables are set
4. Check the supervisor.conf for process configuration

## Summary

✅ **Main Issues Fixed:**
- Removed sed mirror configuration (was failing)
- Removed non-existent directory copy (was causing checksum errors)
- Simplified Dockerfile structure (works now)
- Proper error handling and health checks

🎯 **Next Steps:**
1. Build using Dockerfile.railway
2. Push to Railway or let Railway detect the updated Dockerfile
3. Add required environment variables
4. Deploy