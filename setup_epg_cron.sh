#!/bin/bash
# Setup EPG import cron job (requires sudo)

EPG_WORKER="/opt/nexvision/epg_import_worker.py"
CRON_FILE="/etc/cron.d/nexvision-epg"
LOG_FILE="/var/log/nexvision-epg.log"

echo "Setting up EPG import cron job..."

# Create log file
touch "$LOG_FILE" 2>/dev/null || echo "  Note: May need sudo for log file"

# Install cron job
cat > "$CRON_FILE" << 'CRON'
# NexVision EPG Import - Every 6 hours
0 */6 * * * nexvision /usr/bin/python3 /opt/nexvision/epg_import_worker.py >> /var/log/nexvision-epg.log 2>&1
CRON

echo "✓ EPG import cron job installed"
echo "  Schedule: Every 6 hours (0, 6, 12, 18)"
echo "  Command: python3 /opt/nexvision/epg_import_worker.py"
echo "  Log: /var/log/nexvision-epg.log"
echo ""
echo "To verify:"
echo "  sudo cat /etc/cron.d/nexvision-epg"
echo "  tail -f /var/log/nexvision-epg.log"
