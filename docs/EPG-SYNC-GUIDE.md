# EPG Sync Configuration & Usage

## Overview
The EPG (Electronic Program Guide) service fetches and serves TV channel programming information in XMLTV format.

## Status
- **Server**: Running on port 3000
- **Guide**: `/opt/nexvision/epg/public/guide.xml` (1.2MB)
- **Sync Schedule**: Every 6 hours (configured via CRON_SCHEDULE)

## Services
Three PM2-managed services:
1. `epg-serve` - HTTP server (port 3000) serving guide.xml
2. `epg-grab` - Scheduled sync job (cron: `0 */6 * * *`)
3. `epg-grab-startup` - One-time grab at startup

## Commands

### Check Status
```bash
cd /opt/nexvision/epg
npx pm2 list
npx pm2 logs
```

### Manual Sync
```bash
cd /opt/nexvision/epg
npm run grab -- --channels=channels.xml --output=public/guide.xml
```

### View Guide
```bash
curl http://localhost:3000/guide.xml
```

### Stop/Start Services
```bash
npx pm2 stop epg-grab
npx pm2 start epg-grab
npx pm2 restart all
```

## Configuration

### .env File (`/opt/nexvision/epg/.env`)
```
CRON_SCHEDULE=0 */6 * * *    # Every 6 hours
RUN_AT_STARTUP=true          # Grab on app start
# SITE=epg-grabber           # Optional: specific EPG source
```

### PM2 Config (`pm2.config.js`)
- Runs 3 apps in fork mode
- Auto-restarts on failure
- Logs available via `pm2 logs`

## Integration with NexVision

### For M3U Playlist with EPG
```
#EXTINF:-1 tvg-id="channel-1" tvg-name="Channel Name" tvg-logo="URL" group-title="Group"
http://YOUR_SERVER_IP:8080/stream/channel
```

Access guide for EPG data:
- Direct: `http://YOUR_SERVER_IP:3000/guide.xml`
- Via NexVision API: Configure in app to fetch from EPG endpoint

## Troubleshooting

### Services not running
```bash
cd /opt/nexvision/epg
npx pm2 start pm2.config.js
```

### Guide.xml not updating
```bash
npm run grab -- --channels=channels.xml --output=public/guide.xml --debug
```

### Port 3000 conflict
Edit `pm2.config.js` and change `PORT: 3000` to another port

## Logs
```bash
npx pm2 logs epg-serve      # HTTP server logs
npx pm2 logs epg-grab       # Sync job logs
npx pm2 logs epg-grab-startup
```

## Performance Notes
- Each sync downloads EPG data for 4,600+ channels
- First sync takes ~30 seconds
- Subsequent syncs update guide.xml incrementally
- Guide size: ~1.2MB (compressed with GZIP available)

## Scheduled Restart (Optional)
```bash
npx pm2 startup
npx pm2 save
```

This ensures services restart on server reboot.
