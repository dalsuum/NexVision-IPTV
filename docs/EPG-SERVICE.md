# EPG Service - Operations Guide

## Overview

The EPG service runs from `/opt/nexvision/epg/` and is managed by **PM2**.
It grabs XMLTV guide data and serves it locally on **port 3000** for NexVision to consume.

**Three PM2 processes:**

| Name | Role |
|------|------|
| `epg-serve` | HTTP server — serves `public/guide.xml` on port 3000 |
| `epg-grab` | Cron job — grabs EPG data every 6 hours |
| `epg-grab-startup` | One-time grab on startup |

---

## Start / Stop / Restart

```bash
cd /opt/nexvision/epg

# Start all services
npx pm2 start pm2.config.js

# Stop all
npx pm2 stop all

# Restart all
npx pm2 restart all

# Stop/start individual service
npx pm2 stop epg-serve
npx pm2 start epg-serve

npx pm2 stop epg-grab
npx pm2 start epg-grab
```

### Persist across reboots

```bash
cd /opt/nexvision/epg
npx pm2 startup        # generates systemd command — run the output command
npx pm2 save           # saves current process list
```

---

## Check Status

```bash
cd /opt/nexvision/epg

# List all processes and their status
npx pm2 list

# Detailed info for one process
npx pm2 show epg-serve
npx pm2 show epg-grab
```

---

## Logs

```bash
cd /opt/nexvision/epg

# All services (live tail)
npx pm2 logs

# Individual service
npx pm2 logs epg-serve
npx pm2 logs epg-grab
npx pm2 logs epg-grab-startup

# Last 100 lines
npx pm2 logs --lines 100
```

---

## Manual EPG Grab

Run an immediate grab without waiting for the cron schedule:

```bash
cd /opt/nexvision/epg
npm run grab -- --channels=channels.xml --output=public/guide.xml
```

With debug output:

```bash
npm run grab -- --channels=channels.xml --output=public/guide.xml --debug
```

---

## Verify Guide Is Serving

```bash
# Check the HTTP server is up
curl -s http://localhost:3000/guide.xml | head -c 200

# Check guide file exists and has content
ls -lh /opt/nexvision/epg/public/guide.xml
```

---

## Configuration

### `/opt/nexvision/epg/.env`

```env
CRON_SCHEDULE=0 */6 * * *    # Grab interval (default: every 6 hours)
RUN_AT_STARTUP=true           # Grab once on startup
# SITE=epg-grabber            # Optional: restrict to specific site
```

### `/opt/nexvision/epg/pm2.config.js`

Defines the 3 PM2 apps. Edit here to change port (default `PORT: 3000`) or cron schedule.

### `/opt/nexvision/epg/channels.xml`

Defines which channels to grab EPG data for.

---

## Troubleshooting

### PM2 shows no processes

Services were never started or the PM2 daemon was reset.

```bash
cd /opt/nexvision/epg
npx pm2 start pm2.config.js
npx pm2 list
```

### Port 3000 not responding

```bash
# Check if epg-serve is running
npx pm2 list | grep epg-serve

# Restart it
cd /opt/nexvision/epg
npx pm2 restart epg-serve

# Check what's using port 3000
ss -tlnp | grep 3000
```

### Guide not updating

```bash
# Check grab logs for errors
cd /opt/nexvision/epg
npx pm2 logs epg-grab --lines 50

# Run manually to see output
npm run grab -- --channels=channels.xml --output=public/guide.xml --debug
```

### NexVision not picking up EPG data

Verify the app is configured to use the local EPG server:

```bash
curl --unix-socket /run/nexvision/gunicorn.sock \
  http://localhost/api/settings | python3 -m json.tool | grep epg
```

Expected: `"epg_auto_url": "http://localhost:3000/guide.xml"`
