# EPG Data Import - Setup & Troubleshooting

## Overview
EPG (Electronic Program Guide) data is fetched from the local EPG server (port 3000) and imported into the NexVision database.

## Current Status
- **Imported Programmes**: 251
- **Unmatched**: 121 (channels without matching tvg_id)
- **Last Import**: 2026-04-01 05:15:40 UTC
- **Auto-sync**: Enabled

## Import Worker
`/opt/nexvision/epg_import_worker.py` - Fetches guide.xml and imports to database

### Manual Import
```bash
# Run import immediately
EPG_URL="http://localhost:3000/guide.xml" python3 /opt/nexvision/epg_import_worker.py

# With custom settings
EPG_URL="http://192.168.1.100:3000/guide.xml" \
DB_PATH="/opt/nexvision/nexvision.db" \
python3 /opt/nexvision/epg_import_worker.py
```

### Automatic Imports (Cron)
```bash
# Setup cron job (requires sudo)
sudo bash /opt/nexvision/setup_epg_cron.sh

# Verify installation
sudo cat /etc/cron.d/nexvision-epg

# View logs
tail -f /var/log/nexvision-epg.log
```

**Schedule**: Every 6 hours (0:00, 6:00, 12:00, 18:00 UTC)

## Database Schema

### epg_entries table
```sql
CREATE TABLE epg_entries (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    title TEXT,
    description TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    category TEXT,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);
```

### Matching Logic
EPG entries are matched to channels by `tvg_id`:
- EPG guide.xml: `<programme channel="tvg-id-value">`
- NexVision channels: `tvg_id` field in channels table

## Troubleshooting

### No EPG Data Importing
1. Verify EPG server running:
   ```bash
   curl http://localhost:3000/guide.xml
   ```

2. Check app configuration:
   ```bash
   sqlite3 /opt/nexvision/nexvision.db "SELECT value FROM settings WHERE key='epg_auto_enabled';"
   # Should return: 1
   ```

3. Run manual import with debug:
   ```bash
   python3 /opt/nexvision/epg_import_worker.py
   ```

### High Unmatched Rate (>50%)
This means channels in guide.xml don't have matching `tvg_id` in NexVision.

**Solution**: Add tvg_id to channels
```sql
UPDATE channels SET tvg_id='channel-id-from-epg' WHERE name='Channel Name';
```

### Import Worker Permissions
If cron job fails, check:
```bash
# nexvision user should own the database
ls -l /opt/nexvision/nexvision.db
# Should be: nexvision:nexvision -rw-r--r--

# Fix permissions if needed
sudo chown nexvision:nexvision /opt/nexvision/nexvision.db
```

## Performance
- **Guide fetch**: ~1.2MB (30-60 seconds)
- **Parse time**: ~2-5 seconds
- **Import time**: ~5-10 seconds (depends on channel matches)
- **Total**: ~1 minute per sync

## Settings (Database)
```sql
SELECT key, value FROM settings WHERE key LIKE '%epg%';
```

| Setting | Default | Purpose |
|---------|---------|---------|
| `epg_auto_enabled` | 1 | Enable/disable auto-import |
| `epg_auto_url` | http://localhost:3000/guide.xml | Guide source |
| `epg_auto_interval_minutes` | 360 | Sync interval (6 hours) |
| `epg_last_sync_at` | timestamp | Last successful import |
| `epg_last_imported` | count | Programmes imported |
| `epg_last_unmatched` | count | Programmes without matches |

## Next Steps
1. Verify channels have `tvg_id` values
2. Increase import by adding missing channel IDs
3. Monitor `/var/log/nexvision-epg.log` for issues
