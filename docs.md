---
name: timezone-configuration
description: Pakistan Standard Time (PST) configuration for the Urdu voicebot application
metadata:
  type: project
---

# Timezone Configuration — Pakistan Standard Time

## Overview
The Urdu Voicebot application operates in Pakistan Standard Time (PST).

## Timezone Details
- **Standard Name:** Pakistan Standard Time (PST)
- **Time Zone:** Asia/Karachi
- **UTC Offset:** UTC+5
- **Daylight Saving Time:** None (PST is fixed offset)

## Environment Configuration

### Docker Settings
```bash
# In supervisord.conf or docker-compose.yml
ENV TZ=Asia/Karachi
```

### Dockerfile Additions
```dockerfile
# Add to Dockerfile before install
ENV TZ=Asia/Karachi
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
```

### Application Code
```python
# In app.py or config.py
import pytz
from datetime import datetime

# Set timezone context
karachi_tz = pytz.timezone('Asia/Karachi')
```

### Environment Variables
```bash
# .env.local
TZ=Asia/Karachi

# Or for Docker
docker run -e TZ=Asia/Karachi ... urdu-voicebot
docker-compose up -e TZ=Asia/Karachi
```

## UTC Conversion for Consistency

### Pakistan (UTC+5)
```python
from datetime import datetime, timedelta
import pytz

# Pakistan Time
karachi = pytz.timezone('Asia/Karachi')
pakistan_time = karachi.localize(datetime.now(pytz.UTC) + timedelta(hours=5))

# UTC equivalent
utc_time = datetime.now(pytz.UTC)
# Pakistan = UTC + 5 hours
pakistan_time_from_utc = utc_time + timedelta(hours=5)
```

## Deployment Notes

### Railway Deployment
```bash
# Railway handles timezone via environment
RAILWAY_TZ=Asia/Karachi
```

### Local Development
```bash
# Windows PowerShell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:TIMEZONE='Asia/Karachi'

# Linux/Mac
export TZ=Asia/Karachi
date
```

## Monitoring
- **Logs** in supervisord: `/var/log/supervisor/`
- **Health Check** logs timestamp from Asia/Karachi
- **MongoDB** timestamps stored in UTC and converted to Karachi time for display

## Related Files
- `supervisord.conf` - Supervisor configuration
- `Dockerfile*,docker-compose.yml` - Container/port mappings
- `app.py` - FastAPI application
- `config.py` - Settings and environment loading