#!/usr/bin/env python3
"""
EPG Import Worker - Fetches and imports guide.xml into NexVision database
Matches EPG channels by tvg_id
"""
import os
import sys
import sqlite3
import urllib.request
from datetime import datetime
from xml.etree import ElementTree as ET

EPG_URL = os.getenv('EPG_URL', 'http://localhost:3000/guide.xml')
DB_PATH = os.getenv('DB_PATH', '/opt/nexvision/nexvision.db')
TIMEOUT = int(os.getenv('EPG_TIMEOUT', '30'))

def fetch_guide(url):
    """Fetch guide.xml from EPG server"""
    try:
        print(f"Fetching EPG from: {url}")
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read()
            print(f"  Downloaded: {len(data):,} bytes")
            return data
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None

def parse_guide(xml_data):
    """Parse guide.xml and extract EPG entries"""
    try:
        root = ET.fromstring(xml_data)
        programmes = []
        
        # Parse programmes
        for prog in root.findall('programme'):
            start = prog.get('start')
            stop = prog.get('stop')
            channel_id = prog.get('channel')
            title = prog.findtext('title')
            desc = prog.findtext('desc', '')
            
            if start and stop and channel_id and title:
                programmes.append({
                    'start': start,
                    'stop': stop,
                    'channel_id': channel_id,
                    'title': title,
                    'desc': desc[:500] if desc else ''
                })
        
        print(f"  Parsed: {len(programmes):,} programmes")
        return programmes
    except Exception as e:
        print(f"  ERROR parsing: {e}", file=sys.stderr)
        return []

def import_to_db(programmes):
    """Import EPG data into NexVision database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Clear old entries
        cursor.execute('''DELETE FROM epg_entries WHERE start_time < datetime('now', '-7 days')''')

        imported = 0
        unmatched = 0

        for prog in programmes:
            # Find channel by tvg_id (EPG channel ID)
            cursor.execute('SELECT id FROM channels WHERE tvg_id = ?', (prog['channel_id'],))
            result = cursor.fetchone()
            
            if result:
                channel_id = result['id']
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO epg_entries
                        (channel_id, title, description, start_time, end_time, category)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (channel_id, prog['title'], prog['desc'], prog['start'], prog['stop'], 'TV'))
                    imported += 1
                except sqlite3.IntegrityError:
                    pass
            else:
                unmatched += 1

        conn.commit()
        
        # Update settings
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                      ('epg_last_sync_status', 'ok'))
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                      ('epg_last_imported', str(imported)))
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                      ('epg_last_unmatched', str(unmatched)))
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                      ('epg_last_sync_at', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        print(f"  Imported: {imported:,}, Unmatched: {unmatched:,}")
        return imported, unmatched
    except Exception as e:
        print(f"  ERROR importing: {e}", file=sys.stderr)
        return 0, 0

def main():
    """Main EPG import workflow"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] EPG Import Starting")
    
    xml_data = fetch_guide(EPG_URL)
    if not xml_data:
        return 1
    
    programmes = parse_guide(xml_data)
    if not programmes:
        print("  No programmes found")
        return 1
    
    import_to_db(programmes)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] EPG Import Complete\n")
    return 0

if __name__ == '__main__':
    sys.exit(main())
