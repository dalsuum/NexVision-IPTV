# NexVision — Cast Server Integration Reference

This document defines what the **separate cast server** needs to know
to integrate with the NexVision IPTV system.

---

## Architecture Overview

```
Guest Phone (Guest VLAN)
      │
      ▼  scan QR
Cast Server  ◄──── dual-homed (Guest VLAN + IPTV VLAN)
      │
      ├──► NexVision IPTV Server (IPTV VLAN)
      │      - Chromecast receiver page
      │      - Channel stream URLs
      │      - Room/device API
      │
      └──► TV / Chromecast / Android STB (IPTV VLAN)
```

---

## QR Code — Where It Appears

NexVision displays the cast QR in **three places**, all controlled by the
admin panel (CMS → Settings → Cast QR):

| Location | Description |
|---|---|
| **Home screen corner badge** | Small QR overlay in a configurable corner (top/bottom, left/right) |
| **Screensaver** | QR shown bottom-right of screensaver when TV is idle |
| **Cast nav page** | Full-page cast screen accessible from the "📡 Cast" nav menu item |

The admin configures:
- **Enable/disable** the QR globally (`cast_qr_enabled`)
- **Cast Server URL** — the base URL the QR points to (`cast_server_url`)
- **Show On** — home only, screensaver only, or both (`cast_qr_display`)
- **Position** — which corner of the home screen (`cast_qr_position`)

---

## QR Code Format

The QR code encodes this URL:

```
{cast_server_url}/room/{room_number}
```

**Example:**
```
https://cast.hotel.com/room/304
```

- `cast_server_url` — configured in NexVision CMS → Settings → Cast QR
- `room_number` — the room number registered on that TV (e.g. `304`, `101A`)
- URL-encoded with `encodeURIComponent` on the room number

The cast server owns the `/room/{room_number}` route entirely.
NexVision only generates and displays the QR — it does not handle
what happens after the guest scans.

---

## Cast Nav Page

The TV nav bar includes a dedicated **📡 Cast** menu item. When the
guest selects it, they see a full-page cast screen:

```
┌──────────────────────────────────────────────────────┐
│  Cast to This TV          Room 304                   │
│                                                      │
│  ┌──────────────┐   How to Cast                      │
│  │              │                                    │
│  │  [QR 200px]  │   ❶ Scan QR code with your phone  │
│  │              │   ❷ Open Netflix, YouTube etc      │
│  │              │   ❸ Tap Cast icon → select TV      │
│  └──────────────┘                                    │
│  Scan with your phone  ─────────────────────────     │
│                        Or visit on your browser      │
│                        cast.hotel.com/room/304       │
└──────────────────────────────────────────────────────┘
```

The cast page handles three states:
1. **Configured + room registered** → QR + instructions shown
2. **Cast server URL not set** → "Cast Not Available — contact front desk"
3. **TV not registered to a room** → "Room Not Registered" message

The admin can enable/disable the Cast nav item from CMS → Navigation,
the same as any other nav item (Live TV, Movies, Radio, etc.).

---

## NexVision APIs Available to the Cast Server

Base URL: `http://{nexvision_server}/api`

### GET /rooms
Returns all registered rooms and their device tokens.

```json
[
  {
    "id": 1,
    "room_number": "304",
    "tv_name": "Room 304 TV",
    "token": "abc123...",
    "status": "occupied"
  }
]
```

### GET /rooms/by-number/{room_number}
Look up a single room by room number.

```json
{
  "id": 1,
  "room_number": "304",
  "tv_name": "Room 304 TV",
  "token": "abc123..."
}
```

### GET /channels
Returns the full channel list with stream URLs.

```json
[
  {
    "id": 12,
    "name": "BBC News",
    "url": "http://iptv-server/stream/12",
    "logo": "http://iptv-server/logos/bbc.png",
    "group": "News"
  }
]
```

### GET /api/settings
Returns all NexVision settings including cast configuration.

```json
{
  "hotel_name": "Grand Hotel",
  "cast_qr_enabled": "1",
  "cast_server_url": "https://cast.hotel.com",
  "cast_qr_display": "both",
  "cast_qr_position": "bottom-right"
}
```

### POST /api/cast/session
Log a cast session start (optional — for admin reporting).

**Request body:**
```json
{
  "room_id": 1,
  "channel_id": 12,
  "sender_platform": "android"
}
```

**Response:**
```json
{ "session_id": 42, "status": "started" }
```

### PATCH /api/cast/session/{session_id}
Log a cast session end.

**Request body:**
```json
{ "duration_seconds": 1834 }
```

---

## Chromecast Receiver Page

NexVision hosts a custom CAF v3 Chromecast receiver at:

```
http://{nexvision_server}/cast-receiver
```

This receiver plays HLS streams (NexVision IPTV channels).
To use it for NexVision content casting, register this URL as your
Cast Application's receiver URL in the Google Cast Developer Console.

The receiver accepts a standard CAF `LoadRequest` with:
- `contentId` — the HLS stream URL
- `contentType` — `application/x-mpegURL`
- `metadata.title` — channel name (optional)
- `metadata.images[0].url` — channel logo URL (optional)

---

## Cast Flow: NexVision IPTV Content

```
1. Guest opens Cast nav page or scans QR → cast_server_url/room/304
2. Cast server shows guest the NexVision channel list (GET /api/channels)
3. Guest selects a channel
4. Cast server sends LoadRequest to room's Chromecast:
     contentId   = channel.url
     contentType = "application/x-mpegURL"
5. Chromecast loads /cast-receiver (from NexVision)
6. Receiver plays the HLS stream
7. Cast server logs session (POST /api/cast/session)
```

---

## Cast Flow: Third-Party Apps (Netflix / YouTube)

This flow requires the cast server to act as an mDNS proxy
between the Guest VLAN and IPTV VLAN so the guest's phone
can discover the room's Chromecast/Android TV.

```
1. Guest opens Cast nav page or scans QR → cast_server_url/room/304
2. Cast server identifies room 304's Chromecast IP (IPTV VLAN)
3. Cast server reflects mDNS discovery to guest phone (Guest VLAN)
4. Guest phone sees Chromecast in Netflix/YouTube → casts natively
5. Cast server NAT-routes the Cast signaling traffic
6. Media stream flows phone → cast server → Chromecast
```

NexVision has no role in this flow after displaying the QR.

---

## Settings Configured in NexVision Admin

| Setting | Key | Default | Description |
|---|---|---|---|
| Enable Cast QR | `cast_qr_enabled` | `"0"` | `"1"` = on, `"0"` = off |
| Cast Server URL | `cast_server_url` | `""` | Base URL of your cast server |
| Show On | `cast_qr_display` | `"both"` | `"both"`, `"home"`, `"screensaver"` |
| Position | `cast_qr_position` | `"bottom-right"` | `"bottom-right"`, `"bottom-left"`, `"top-right"`, `"top-left"` |

The cast server can read these from `GET /api/settings` to verify
configuration without manual coordination.

---

## Room Number Encoding Notes

- Room numbers are strings, not integers (e.g. `"101A"`, `"PH1"`)
- URL-encoded in the QR: `encodeURIComponent(room_number)`
- Decode on cast server with standard URL decoding
- Room numbers match exactly what is shown on `GET /api/rooms`