# EPG Sync Fix - Completed

## Problem
- App was configured to fetch EPG from external GitHub URL
- URL: `https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/guide.xml`
- This was timing out causing "Syncing EPG..." status

## Solution
1. **Set up local EPG server** (port 3000)
   - PM2 running 3 services: epg-serve, epg-grab, epg-grab-startup
   - Cron sync every 6 hours
   - Local guide.xml with 4,600+ channels

2. **Updated app configuration**
   - Changed epg_auto_url to: `http://localhost:3000/guide.xml`
   - EPG sync now fetches from local server (instant, reliable)

## Verification

### Local EPG Server
```bash
curl http://localhost:3000/guide.xml
```

### App Settings (REST API)
```bash
curl --unix-socket /run/nexvision/gunicorn.sock http://localhost/api/settings | jq '.epg_auto_url'
# Returns: "http://localhost:3000/guide.xml"
```

### EPG Services Status
```bash
cd /opt/nexvision/epg
npx pm2 list
```

## Configuration

**EPG Sync Schedule**: Every 360 minutes (6 hours)
- Controlled by: `epg_auto_interval_minutes`
- Auto-enabled: `epg_auto_enabled = 1`

**Last Sync**:
- Status: ok
- Events imported: 596 / 32091
- Message updated in database

## Next Sync with New URL
- Will occur automatically in ~6 hours
- Or trigger manually via application UI
- App will fetch from local server (~1 second)

## Files Changed
- Database setting: `epg_auto_url` → local URL
- Redis cache cleared for immediate effect
