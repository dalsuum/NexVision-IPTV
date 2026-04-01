#!/bin/bash
# EPG Sync Setup Script
# Sets up and manages EPG synchronization service

set -e

EPG_DIR="/opt/nexvision/epg"
EPG_ENV="$EPG_DIR/.env"
EPG_PUBLIC="$EPG_DIR/public"

echo "=== NexVision EPG Sync Setup ==="

# Create public folder
mkdir -p "$EPG_PUBLIC"
echo "✓ EPG public folder ready"

# Create .env if not exists
if [ ! -f "$EPG_ENV" ]; then
  cat > "$EPG_ENV" << EOF
# EPG Sync Configuration
CRON_SCHEDULE=0 */6 * * *
RUN_AT_STARTUP=true
# SITE=epg-grabber  # Optional: specific site
EOF
  echo "✓ .env created"
fi

# Start EPG services with PM2
cd "$EPG_DIR"
npx pm2 start pm2.config.js --update-env
echo "✓ PM2 services started"

# Show status
echo ""
echo "=== EPG Services Status ==="
npx pm2 list

# Make PM2 persist across reboots
npx pm2 startup systemd -u a13 --hp /home/a13 2>/dev/null || true
npx pm2 save

echo ""
echo "=== EPG Configuration ==="
echo "CRON Schedule: Every 6 hours ($(grep CRON_SCHEDULE $EPG_ENV))"
echo "Server: http://localhost:3000"
echo "Guide: http://localhost:3000/guide.xml"
echo ""
echo "✓ EPG Sync setup complete!"
