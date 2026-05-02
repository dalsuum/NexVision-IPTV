# NexVision — PMS Integration Guide

> Version: v8.21 — Last updated: 2026-05-02  
> Covers: Oracle FIAS · GRMS · Third-party PMS

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current State (v8.21)](#2-current-state-v821)
3. [Data Flow](#3-data-flow)
4. [Settings Reference](#4-settings-reference)
5. [Database Schema](#5-database-schema)
6. [Log Storage](#6-log-storage)
7. [Admin Panel Setup](#7-admin-panel-setup)
8. [TV Client Behaviour](#8-tv-client-behaviour)
9. [Planned: Backend PMS Connector](#9-planned-backend-pms-connector)

---

## 1. Overview

NexVision supports connecting to a hotel Property Management System (PMS) to automatically populate guest information — name, check-in time, and check-out time — on each room's TV.

**Supported PMS systems (settings UI):**
| Value | System |
|---|---|
| `fias` | Oracle FIAS (TCP socket, port 5010) |
| `grms` | GRMS System |
| `thirdparty` | Any third-party PMS (custom integration) |

---

## 2. Current State (v8.21)

| Component | Status |
|---|---|
| Admin settings form (host, port, credentials) | ✅ Implemented |
| Guest data fields on rooms (`guest_name`, `checkin_time`, `checkout_time`) | ✅ Implemented |
| Guest welcome overlay on TV (name, times, music) | ✅ Implemented |
| Backend TCP/HTTP connector to live PMS | ⏳ Not yet built |
| Automatic guest sync on check-in/check-out events | ⏳ Not yet built |

Guest data is currently entered manually through **Admin Panel → Rooms** or via the REST API (`PUT /api/rooms/<id>`). The PMS credentials stored in settings are ready for the backend connector when it is built.

---

## 3. Data Flow

### Current flow (manual entry)

```
Admin Panel
    │
    │  PUT /api/rooms/<id>
    │  {guest_name, checkin_time, checkout_time}
    ▼
Flask → room_service.update_room()
    │
    ▼
SQLite/MySQL  rooms  table
    │  guest_name, checkin_time, checkout_time columns
    │
    │  POST /api/rooms/register  {room_number}
    ▼
TV Client (browser localStorage)
    │  ROOM_INFO_KEY  →  {guest_name, checkin_time, checkout_time, token, ...}
    │
    ▼
showGuestWelcome()  (tv.js)
    │  Reads localStorage → renders welcome overlay
    │  Auto-dismisses after 12 seconds
    ▼
Guest sees personalised welcome screen
```

### Settings flow

```
Admin Panel → POST /api/settings
    {pms_enabled, pms_type, pms_host, pms_port, pms_username, pms_password}
    │
    ▼
settings_service.save_settings()
    │
    ▼
SQLite/MySQL  settings  table  (key-value rows)
    │
    │  Cached in Redis  nv:settings  (60s TTL)
    │
    ▼
TV Client  →  GET /api/settings  →  window._settings
    checks:  _settings.pms_enabled === '1'
```

### Room registration sequence

```
TV Client
  POST /api/rooms/register  {room_number: "101"}
        │
        ▼
  room_service.room_register()
        │  SELECT * FROM rooms WHERE LOWER(room_number) = LOWER(?)
        │  UPDATE rooms SET last_seen=..., online=1
        │
        ▼
  Response JSON:
  {
    "status":        "ok",
    "room_number":   "101",
    "tv_name":       "Room 101 TV",
    "token":         "3f8a2b9c-...",
    "guest_name":    "Mr. John Smith",    ← from rooms table
    "checkin_time":  "2026-05-01 14:00",  ← from rooms table
    "checkout_time": "2026-05-03 12:00"   ← from rooms table
  }
        │
        ▼
  TV stores full response in localStorage["nv_room_info"]
```

---

## 4. Settings Reference

All PMS settings are stored as rows in the `settings` table (key-value). They are read by the TV client via `GET /api/settings`.

| Key | Type | Default | Description |
|---|---|---|---|
| `pms_enabled` | `0`/`1` | `0` | Enable PMS integration |
| `pms_type` | string | `fias` | PMS system: `fias` / `grms` / `thirdparty` |
| `pms_host` | string | `` | PMS server hostname or IP address |
| `pms_port` | string | `5010` | PMS server TCP/HTTP port |
| `pms_username` | string | `` | PMS authentication username |
| `pms_password` | string | `` | PMS authentication password (stored as plaintext — use `.env` encryption in production) |
| `welcome_music_enabled` | `0`/`1` | `0` | Play audio during guest welcome overlay |
| `welcome_music_url` | url | `` | URL to audio file played at 70% volume during welcome |
| `pms_welcome_msg` | html | `` | Optional custom HTML shown in the welcome overlay |

---

## 5. Database Schema

### `rooms` table — PMS columns

```sql
CREATE TABLE rooms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room_number   TEXT NOT NULL,
    tv_name       TEXT,
    -- ... other columns ...
    guest_name    TEXT DEFAULT '',   -- PMS guest full name
    checkin_time  TEXT DEFAULT '',   -- ISO datetime: "2026-05-01 14:00:00"
    checkout_time TEXT DEFAULT ''    -- ISO datetime: "2026-05-03 12:00:00"
);
```

**Update guest info via API:**
```http
PUT /api/rooms/<id>
Authorization: Bearer <admin_jwt>
Content-Type: application/json

{
  "room_number":   "101",
  "tv_name":       "Room 101 TV",
  "guest_name":    "Mr. John Smith",
  "checkin_time":  "2026-05-01 14:00:00",
  "checkout_time": "2026-05-03 12:00:00"
}
```

**Clear guest on checkout:**
```http
PUT /api/rooms/<id>
{
  "room_number":   "101",
  "guest_name":    "",
  "checkin_time":  "",
  "checkout_time": ""
}
```

### `settings` table — PMS keys

```sql
-- PMS rows inserted/updated via POST /api/settings
SELECT key, value FROM settings WHERE key LIKE 'pms%';
-- pms_enabled  | 1
-- pms_type     | fias
-- pms_host     | 192.168.1.100
-- pms_port     | 5010
-- pms_username | pms_user
-- pms_password | s3cr3t
```

---

## 6. Log Storage

There is **no dedicated PMS log file or database table** in the current implementation. All activity is captured by the standard application logs.

### Log locations

| Log | Path | Contains |
|---|---|---|
| Gunicorn access | `/var/log/nexvision/access.log` | Every HTTP request (method, path, status, latency) |
| Gunicorn error | `/var/log/nexvision/error.log` | Python exceptions, worker errors |
| Nginx access | `/var/log/nginx/access.log` | All incoming requests before proxying |
| Nginx error | `/var/log/nginx/error.log` | Nginx-level errors (502, upstream down) |
| systemd journal | `journalctl -u nexvision` | Gunicorn stdout/stderr + service events |

### Querying PMS-related log entries

```bash
# Rooms API calls (registration, guest updates)
grep "/api/rooms" /var/log/nexvision/access.log

# Settings saves (pms_enabled, pms_host, etc.)
grep "POST /api/settings" /var/log/nexvision/access.log

# Real-time application log
sudo journalctl -u nexvision -f

# Errors in the last 100 lines
sudo journalctl -u nexvision -n 100 --no-pager | grep -i error
```

### When the backend PMS connector is built

The connector will write to a dedicated log. Planned location:

```
/var/log/nexvision/pms.log
```

Log entries will cover:
- TCP connection open / close to PMS host
- Each check-in event received (room, guest name, times)
- Each check-out event received
- Reconnection attempts and errors

---

## 7. Admin Panel Setup

1. Go to **Admin Panel → Settings → Guest Info & PMS**
2. Toggle **Enable PMS Integration** on
3. Select your **PMS System**: Oracle FIAS / GRMS / Third-party
4. Enter **PMS Host / IP** (e.g. `192.168.1.100`)
5. Enter **Port** (FIAS default: `5010`)
6. Enter **Username** and **Password** (required by some PMS systems)
7. Optionally paste a custom **Welcome Message** (HTML)
8. Optionally enable **Welcome Music** and provide an audio URL
9. Click **Save Settings**

Until the backend connector is built, also update guest data manually:
1. Go to **Admin Panel → Rooms**
2. Click edit on a room
3. Fill in **Guest Name**, **Check-in Time**, **Check-out Time**
4. Save

---

## 8. TV Client Behaviour

### Welcome overlay trigger conditions

The overlay (`#guest-welcome`) is shown when **all** of these are true:

| Condition | Check |
|---|---|
| `settings.pms_enabled === '1'` | Checked in `showGuestWelcome()` at [tv.js:3014](web/tv/tv.js#L3014) |
| Room has a non-empty `guest_name` | Read from `localStorage` via `getRoomInfo()` |
| Session flag not set | `sessionStorage['nv_welcome_shown']` must be absent |

### What the overlay displays

```
┌─────────────────────────────────────┐
│          [hotel_name]               │
│                                     │
│   Welcome, [guest_name]             │
│                                     │
│   Check-in:  [checkin_time]         │
│   Check-out: [checkout_time]        │
│                                     │
│        (tap or press any key)       │
└─────────────────────────────────────┘
```

- Auto-dismisses after **12 seconds**
- Welcome music plays at **70% volume** if `welcome_music_enabled === '1'`
- After dismissal, `sessionStorage['nv_welcome_shown'] = '1'` is set — overlay will **not** appear again until the browser tab is closed and reopened

### Guest data lifecycle on the TV

```
POST /api/rooms/register
    → response stored to localStorage["nv_room_info"]
    → cleared only when clearRegistration() is called
      (e.g. room token invalidated, manual unregister)
```

To force the welcome overlay to appear again (for testing):
```javascript
// In browser DevTools console on the TV client:
sessionStorage.removeItem('nv_welcome_shown');
location.reload();
```

---

## 9. Planned: Backend PMS Connector

When built, the connector will be a background thread (or separate process) that:

### Oracle FIAS (TCP socket)

```
nexvision  ──TCP:5010──→  Oracle FIAS server
                          ← LINK message (connection ack)
                          ← GI|RN=101|GN=John Smith|ARR=20260501|DEP=20260503
                             (Guest Information record on check-in)
                          ← CO|RN=101
                             (Check-out event)
```

On each `GI` event:
1. Parse room number, guest name, arrival/departure dates
2. `UPDATE rooms SET guest_name=?, checkin_time=?, checkout_time=? WHERE room_number=?`
3. Write event to `/var/log/nexvision/pms.log`
4. Invalidate Redis cache for that room's data

On each `CO` event:
1. Clear guest fields for the room
2. Log the checkout

### GRMS / Third-party

Similar event-driven model via HTTP webhooks or polling, with the same DB write and log path.

### Planned API endpoint

```http
GET /api/pms/status
Authorization: Bearer <admin_jwt>

{
  "connected":    true,
  "pms_type":     "fias",
  "host":         "192.168.1.100:5010",
  "last_event":   "2026-05-02 09:14:22",
  "events_today": 12
}
```

---

*NexVision IPTV — PMS Integration Guide*  
*Architecture: Flask + SQLite/MySQL + Redis · TV Client: Vanilla JS localStorage*
