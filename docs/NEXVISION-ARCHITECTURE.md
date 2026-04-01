# NexVision IPTV + VOD System Architecture

**Document Version**: 2.0 (March 2026)
**System Version**: NexVision IPTV Platform v8.9
**Last Updated**: March 23, 2026

> 🎨 **Interactive Diagram**: Open [nexvision-system-architecture.drawio](nexvision-system-architecture.drawio) in draw.io for the complete visual system architecture

---

## 🏗️ SYSTEM OVERVIEW

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NexVision IPTV Platform                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                              CLIENT LAYER                                   │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│   TV Client     │  Mobile Web     │  Admin Panel    │   External APIs         │
│  (HTML5/199KB)  │   Interface     │  (Management)   │  (EPG, Storage, etc.)   │
├─────────────────┴─────────────────┴─────────────────┴─────────────────────────┤
│                            WEB SERVER LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Nginx Reverse Proxy (Port 80/443)                                         │
│  • Static file serving • X-Accel-Redirect • SSL termination • Caching      │
├─────────────────────────────────────────────────────────────────────────────┤
│                          APPLICATION LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Flask Application (Port 5000) - 402KB, 186 API endpoints                  │
│  • Authentication • Room Management • Channel Streaming • VOD Delivery      │
│  • Package Management • EPG Integration • Multi-Storage Abstraction         │
├─────────────────────────────────────────────────────────────────────────────┤
│                           STORAGE LAYER                                     │
├─────────┬─────────┬─────────────┬─────────────┬───────────────┬─────────────┤
│ SQLite  │  Local  │     NAS     │  Amazon S3  │ Azure Storage │ Google GCS  │
│Database │ Files   │   Storage   │   Storage   │     Blob      │   Storage   │
├─────────┴─────────┴─────────────┴─────────────┴───────────────┴─────────────┤
│                            DATA SOURCES                                     │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│  M3U Playlists  │  EPG Sources    │   RSS Feeds     │    External APIs        │
│  (11,427+ chs)  │   (XMLTV/CSV)   │  (News/Weather) │   (Weather, Prayer)     │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
```

### System Statistics (Current)
- **Channels**: 11,427+ live TV channels
- **API Endpoints**: 186 REST endpoints
- **Database Tables**: 30 tables (4.9MB SQLite)
- **Rooms**: 20 registered hotel rooms
- **Packages**: Content packages with bulk assignment
- **Storage Backends**: 5 supported (Local, NAS, S3, Azure, GCS)
- **Client Size**: 199KB HTML5 TV interface

---

## 📺 IPTV ARCHITECTURE

### 1. Channel Streaming Pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   M3U Sources   │───▶│  Channel Parser │───▶│ Channel Database│
│  (External CDN) │    │   (Import API)  │    │   (11,427+ ch)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   TV Client     │◀───│  Access Control │◀───│ Package System  │
│  (Room Token)   │    │  (Room Packages)│    │ (Bulk Assignment)│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │
         │              ┌─────────────────┐
         └─────────────▶│ Streaming Proxy │
                        │ (X-Accel-Redirect)│
                        └─────────────────┘
```

### 2. Client Interface Architecture

#### TV Client (tv/index.html - 199KB)
```
┌─────────────────────────────────────────────────────────────────────┐
│                        TV Client Interface                          │
├─────────────┬─────────────────┬─────────────────┬─────────────────────┤
│   Home      │   Live TV       │      VOD        │      Settings       │
│   Screen    │   (Channels)    │   (Movies)      │   (Room Config)     │
├─────────────┼─────────────────┼─────────────────┼─────────────────────┤
│ • Channel   │ • 11,427+ chs   │ • HLS Player    │ • Room Registration │
│   Cards     │ • Pagination    │ • Multi-Storage │ • Package Auth      │
│ • EPG Now   │ • EPG Overlay   │ • Thumbnails    │ • User Preferences  │
│ • Messages  │ • Search/Filter │ • Categories    │ • Admin Access      │
├─────────────┴─────────────────┴─────────────────┴─────────────────────┤
│                      Shared Components                               │
├─────────────────────────────────────────────────────────────────────┤
│ • HLS.js Player  • Room Token Auth  • API Client  • Responsive UI   │
│ • EPG Integration • Message System  • RSS Ticker  • Weather Widget  │
└─────────────────────────────────────────────────────────────────────┘
```

#### Admin Panel (admin/index.html)
```
┌─────────────────────────────────────────────────────────────────────┐
│                      Admin Management Panel                         │
├─────────────┬─────────────────┬─────────────────┬─────────────────────┤
│  Channels   │    Packages     │     Rooms       │      Storage        │
│ Management  │   Management    │   Management    │    Management       │
├─────────────┼─────────────────┼─────────────────┼─────────────────────┤
│ • CRUD Ops  │ • Bulk Select   │ • Registration  │ • Multi-Backend     │
│ • M3U Import│ • 11,427 ch all │ • Package Assign│ • Health Monitor    │
│ • EPG Sync  │ • Access Control│ • Token Mgmt    │ • Cloud Config      │
│ • Bulk Edit │ • Content Bundle│ • Device Status │ • Storage Analytics │
├─────────────┴─────────────────┴─────────────────┴─────────────────────┤
│                      System Administration                           │
├─────────────────────────────────────────────────────────────────────┤
│ • User Management  • Settings Config  • Analytics  • Log Monitoring │
│ • Message Broadcast • RSS Management  • Reports    • System Health   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3. Package-Based Access Control

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Rooms       │    │    Packages     │    │    Channels     │
│   (20 rooms)    │    │  (Content Bundles)  │ │  (11,427+ chs)  │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • Room 101      │──┐ │ • Package "All" │──┐ │ • BBC One       │
│ • Room 102      │  │ │ • Package "Basic"│ │ │ • CNN           │
│ • Room 103      │  │ │ • Package "VIP" │  │ │ • ESPN         │
│ • ...           │  │ │ • ...           │  │ │ • ...          │
└─────────────────┘  │ └─────────────────┘  │ └─────────────────┘
                     │                      │
                ┌─────────────────┐    ┌─────────────────┐
                │ room_packages   │    │package_channels │
                │   (Mapping)     │    │   (Mapping)     │
                ├─────────────────┤    ├─────────────────┤
                │room_id=23→pkg=2│    │pkg=2→11,427 chs│
                │room_id=24→pkg=2│    │(Bulk Assignment)│
                └─────────────────┘    └─────────────────┘
```

### 4. Authentication & Session Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Device Access  │    │ Room Registration│    │  Token Storage  │
│   (TV Browser)  │───▶│  (POST /rooms/  │───▶│  (localStorage) │
│                 │    │     register)   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │             │   Room Token    │◀──────────────┘
         │             │  (UUID Format)  │
         │             └─────────────────┘
         │                       │
         └─────────────┬─────────────────┐
                      │  API Requests   │
         ┌─────────────▼─────────────────▼─────────────────┐
         │     X-Room-Token: uuid (Header Auth)           │
         │  ┌─────────────────────────────────────────┐   │
         │  │   Package Resolution & Channel Access   │   │
         │  └─────────────────────────────────────────┘   │
         └─────────────────────────────────────────────────┘
```

---

## 🎬 VOD ARCHITECTURE

### 1. Multi-Storage Backend System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VOD Storage Abstraction Layer                    │
├─────────────────────────────────────────────────────────────────────┤
│              StorageBackend Interface (Python ABC)                  │
├─────────┬─────────┬─────────────┬─────────────┬───────────┬─────────┤
│ Local   │  NAS    │  Amazon S3  │Azure Blob   │Google GCS │ Future  │
│Storage  │Storage  │   Storage   │  Storage    │ Storage   │Backends │
├─────────┼─────────┼─────────────┼─────────────┼───────────┼─────────┤
│• Direct │• NFS/   │• boto3 SDK  │• Azure SDK  │• GCS SDK  │• Custom │
│  Files  │  CIFS   │• S3 API     │• Blob API   │• JSON Key │• Cloud  │
│• /opt/  │• Mount  │• IAM Roles  │• SAS Tokens │• OAuth2   │• Hybrid │
│  nexvis │  Point  │• Encryption │• Encryption │• Buckets  │• CDN    │
└─────────┴─────────┴─────────────┴─────────────┴───────────┴─────────┘
```

### 2. Content Delivery Pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Upload API    │───▶│ Storage Backend │───▶│  File Metadata  │
│  (Admin Panel)  │    │   (Abstracted)  │    │   (Database)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   HLS Player    │◀───│ X-Accel-Redirect│◀───│ Access Control  │
│  (TV Client)    │    │  (Nginx Proxy)  │    │ (Package Check) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

#### HLS Streaming with X-Accel-Redirect
```
1. Client requests: GET /vod/hls/movie-123/master.m3u8

2. Flask authenticates and authorizes request

3. Flask returns X-Accel-Redirect header:
   X-Accel-Redirect: /internal/vod/hls/movie-123/master.m3u8

4. Nginx serves file directly (kernel-level performance):
   location /internal/vod/ {
       internal;
       alias /opt/nexvision/;  # or storage backend path
   }

5. Subsequent .ts segment requests bypass Flask entirely
```

### 3. Storage Configuration Matrix

| Backend | Configuration | Use Case | Performance | Scalability |
|---------|---------------|----------|-------------|-------------|
| **Local** | `{"base_path": "/opt/nexvision/vod_data"}` | Single server, small scale | Highest (direct I/O) | Limited |
| **NAS** | `{"base_path": "/mnt/nas", "mount_point": "/mnt/nas"}` | Shared storage cluster | High (network I/O) | Medium |
| **S3** | `{"bucket": "nexvision-vod", "region": "us-east-1"}` | Cloud-native, global CDN | Medium (API latency) | Unlimited |
| **Azure** | `{"account_name": "nexvision", "container": "vod"}` | Microsoft ecosystem | Medium (API latency) | Unlimited |
| **GCS** | `{"bucket": "nexvision-vod", "credentials_file": "..."}` | Google ecosystem | Medium (API latency) | Unlimited |

### 4. VOD Management API

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VOD Management API                            │
├─────────────┬─────────────────┬─────────────────┬─────────────────────┤
│   Upload    │    Metadata     │   Transcoding   │     Delivery        │
│     API     │      API        │      API        │       API           │
├─────────────┼─────────────────┼─────────────────┼─────────────────────┤
│POST /vod    │GET /vod/{id}    │POST /vod/{id}/  │GET /vod/hls/{id}/   │
│• Multipart  │PUT /vod/{id}    │    transcode    │    master.m3u8      │
│• Validation │• Title, desc    │• HLS generation │• X-Accel-Redirect  │
│• Storage    │• Thumbnail      │• Quality levels │• Authentication     │
│• Processing │• Categories     │• Progress track │• Package checking   │
└─────────────┴─────────────────┴─────────────────┴─────────────────────┘
```

---

## 🔌 API ARCHITECTURE

### Core API Endpoints (186 total)

#### Authentication & Session Management
```
POST   /api/auth/login          # Admin authentication
GET    /api/auth/me             # Current user info
POST   /api/rooms/register      # Room device registration
GET    /api/rooms/setup/{token} # Room setup details
```

#### Channel Management (IPTV Core)
```
GET    /api/channels             # Channel list (paginated)
POST   /api/channels             # Create channel
PUT    /api/channels/{id}        # Update channel
DELETE /api/channels/{id}        # Delete channel
POST   /api/channels/import-m3u  # Bulk M3U import
GET    /api/channels/export-m3u  # Export channels
```

#### Package Management (Access Control)
```
GET    /api/packages             # Package list
POST   /api/packages             # Create package (with select_all_channels)
PUT    /api/packages/{id}        # Update package (with bulk assignment)
DELETE /api/packages/{id}        # Delete package
```

#### VOD Management
```
GET    /api/vod                  # VOD library
POST   /api/vod                  # Upload video
GET    /api/vod/{id}             # Video details
PUT    /api/vod/{id}             # Update video
DELETE /api/vod/{id}             # Delete video
GET    /vod/hls/{id}/master.m3u8 # Stream video (X-Accel-Redirect)
```

#### EPG (Electronic Program Guide)
```
GET    /api/epg                  # EPG data (hours parameter)
POST   /api/epg/sync             # Manual EPG sync
GET    /api/epg/channels         # Channels with EPG coverage
```

#### System & Configuration
```
GET    /api/health               # System health check
GET    /api/settings             # System settings
PUT    /api/settings             # Update settings
GET    /api/nav                  # Navigation configuration
GET    /api/skin                 # Current room skin
```

### API Request/Response Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client        │    │  Flask Router   │    │   Business      │
│  (TV/Admin)     │───▶│  (186 routes)   │───▶│    Logic        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │             │  Authentication │◀──────────────┘
         │             │   Middleware    │
         │             └─────────────────┘
         │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   JSON Response │◀───│  Response       │◀───│   Database      │
│   (REST API)    │    │  Formatter      │    │   Operations    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🗄️ DATABASE ARCHITECTURE

### Entity Relationship Model

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│      users      │    │      rooms      │    │    channels     │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ id (PK)         │    │ id (PK)         │    │ id (PK)         │
│ username        │    │ room_number     │    │ name            │
│ password_hash   │    │ tv_name         │    │ stream_url      │
│ role            │    │ room_token (UK) │    │ logo            │
│ active          │    │ online          │    │ active          │
└─────────────────┘    │ last_seen       │    │ media_group_id  │
                       └─────────────────┘    └─────────────────┘
                               │                       │
                               │               ┌─────────────────┐
                        ┌─────────────────┐    │  media_groups   │
                        │ room_packages   │    ├─────────────────┤
                        ├─────────────────┤    │ id (PK)         │
                        │ room_id (FK)    │    │ name            │
                        │ package_id (FK) │    │ sort_order      │
                        └─────────────────┘    └─────────────────┘
                               │
                    ┌─────────────────┐
                    │content_packages │
                    ├─────────────────┤    ┌─────────────────┐
                    │ id (PK)         │    │package_channels │
                    │ name            │    ├─────────────────┤
                    │ description     │────│ package_id (FK) │
                    │ active          │    │ channel_id (FK) │
                    └─────────────────┘    └─────────────────┘
```

### Key Tables and Relationships

#### Core Content (IPTV)
- **channels** (11,427+ records): Live TV channel definitions
- **media_groups**: Channel categorization (News, Sports, etc.)
- **content_packages**: Content bundles (Basic, Premium, All)
- **package_channels**: Channel-to-package mapping (supports bulk "all channels")

#### Access Control  - **rooms**: Hotel room/device registrations
- **room_packages**: Room access permissions
- **users**: Admin user accounts
- **vip_channel_access**: Individual channel grants

#### Content Delivery (VOD)
- **vod_movies**: Video library metadata
- **package_vod**: VOD-to-package mapping
- **watch_history**: User viewing analytics

#### Program Guide (EPG)
- **epg_entries**: TV program schedule data
- **settings**: EPG source configuration

#### System Configuration
- **settings**: System-wide configuration
- **nav_items**: UI navigation structure
- **promo_slides**: Marketing content
- **skins**: UI theming

### Database Performance Optimizations

```sql
-- Channel access optimization (most frequent query)
CREATE INDEX idx_package_channels_pkg ON package_channels(package_id);
CREATE INDEX idx_room_packages_room ON room_packages(room_id);

-- EPG performance
CREATE INDEX idx_epg_channel ON epg_entries(channel_id);
CREATE INDEX idx_epg_times ON epg_entries(start_time, end_time);
CREATE UNIQUE INDEX idx_epg_uniq ON epg_entries(channel_id, start_time);

-- Room token lookup
CREATE UNIQUE INDEX idx_rooms_token ON rooms(room_token);
```

---

## 🔧 DEPLOYMENT ARCHITECTURE

### Production Deployment Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Load Balancer                               │
│                    (Optional - HA Setup)                            │
├─────────────────────────────────────────────────────────────────────┤
│                         Web Server                                   │
│  Nginx (Port 80/443) - Reverse Proxy + Static Files + SSL          │
├─────────────────────────────────────────────────────────────────────┤
│                      Application Server                              │
│  Gunicorn (Port 5000) - WSGI Server with 4 workers                 │
│  ├── Worker 1: Flask App Instance                                   │
│  ├── Worker 2: Flask App Instance                                   │  │  ├── Worker 3: Flask App Instance                                   │
│  └── Worker 4: Flask App Instance                                   │
├─────────────────────────────────────────────────────────────────────┤
│                        Process Management                            │
│  Systemd Service (nexvision.service) - Auto-restart + Monitoring    │
├─────────────────────────────────────────────────────────────────────┤
│                         File System                                  │
│  /opt/nexvision/ - Application Code + SQLite + Local Storage        │
│  /var/log/nginx/ - Web server logs                                  │
│  /var/log/journal/ - Application logs (systemd)                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Network Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Internet/CDN   │    │   Hotel LAN     │    │  Room Devices   │
│   (EPG/M3U)     │    │  (172.17.x.x)   │    │  (TV Clients)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         └─────────────▶│ NexVision Server│◀──────────────┘
                        │ YOUR_SERVER_IP_HERE    │
                        └─────────────────┘
                                │
                       ┌─────────────────┐
                       │  External CDN   │
                       │ (Channel URLs)  │
                       └─────────────────┘
```

### Storage Architecture Deployment

#### Single Server (Local Storage)
```
Server: YOUR_SERVER_IP_HERE
├── OS: Ubuntu 22.04 LTS
├── Storage: /opt/nexvision/
│   ├── nexvision.db (SQLite - 4.9MB)
│   ├── vod_data/ (Local VOD files)
│   ├── hls/ (HLS segments)
│   └── thumbnails/ (Video thumbnails)
└── Nginx: X-Accel-Redirect for performance
```

#### Multi-Server (Cloud Storage)
```
Web Server: YOUR_SERVER_IP_HERE
├── Nginx + Flask App
├── SQLite Database
└── Storage Backend: Cloud

Storage Options:
├── AWS S3: nexvision-vod bucket
├── Azure: nexvision storage account
├── Google GCS: nexvision-vod bucket
└── NAS: /mnt/nas/vod_data
```

---

## 📊 PERFORMANCE & SCALING

### Current Performance Metrics

| Component | Current Capacity | Bottleneck | Scaling Strategy |
|-----------|------------------|------------|------------------|
| **Channels** | 11,427+ channels | Package resolution | Database indexing |
| **Concurrent Streams** | 500 users | Nginx/bandwidth | Load balancer + CDN |
| **Database** | 4.9MB SQLite | Write concurrency | MySQL cluster |
| **Storage** | Local filesystem | I/O throughput | Cloud storage backends |
| **API Response** | <200ms avg | Database queries | Query optimization |

### Scaling Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Future Scaling                             │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┤
│  Load Balancer  │   Web Servers   │  App Servers    │    Database     │
│   (HAProxy)     │   (Nginx x3)    │ (Flask x6)      │  (MySQL HA)     │
├─────────────────┼─────────────────┼─────────────────┼─────────────────┤
│ • SSL Term      │ • Static Files  │ • Stateless     │ • Master/Slave  │
│ • Health Check  │ • X-Accel-Redir │ • Auto-scaling  │ • Read Replicas │
│ • Failover      │ • Rate Limiting │ • Worker Pools  │ • Backup/HA     │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
                                │
                    ┌─────────────────────┐
                    │   Content Delivery   │
                    │   (CDN + Storage)    │
                    ├─────────────────────┤
                    │ • AWS CloudFront     │
                    │ • Azure CDN         │
                    │ • Google Cloud CDN  │
                    │ • Multi-region      │
                    └─────────────────────┘
```

### Performance Optimization Features

#### X-Accel-Redirect (Implemented)
- **Benefit**: Nginx serves files at kernel level (10x faster than Python)
- **Use Case**: HLS video segments, large file downloads
- **Implementation**: Flask returns headers, Nginx serves files

#### Package Bulk Assignment (Recently Added)
- **Benefit**: Assign all 11,427+ channels in one SQL operation
- **Use Case**: "All Channels" packages for VIP rooms
- **Implementation**: `INSERT INTO package_channels SELECT *, ? FROM channels`

#### Database Optimization
- **SQLite Tuning**: WAL mode, optimized cache size
- **Indexing**: Optimized for package resolution queries
- **Query Optimization**: Prepared statements, efficient joins

---

## 🔐 SECURITY ARCHITECTURE

### Authentication & Authorization Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Device       │    │  Registration   │    │   Token Auth    │
│  (TV Client)    │───▶│  (Room Number)  │───▶│ (X-Room-Token)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │             │   Package       │◀──────────────┘         │             │   Resolution    │
         │             └─────────────────┘
         │                       │
┌─────────────────┐    ┌─────────────────┐
│  Content Access │◀───│  Authorization  │
│  (Filtered API) │    │    Check        │
└─────────────────┘    └─────────────────┘
```

### Security Layers

#### Network Security
- **Nginx**: Reverse proxy, rate limiting, SSL termination
- **Firewall**: UFW/iptables rules (ports 80, 443, 22 only)
- **SSL/TLS**: HTTPS encryption, certificate management

#### Application Security
- **Token-based Auth**: UUID tokens for room devices
- **Admin Authentication**: Username/password + session management
- **Package-based Access**: Granular content permissions
- **Input Validation**: SQL injection prevention, XSS protection

#### File System Security
- **User Isolation**: nexvision system user (non-root)
- **File Permissions**: 600 (.env), 640 (app.py), 755 (directories)
- **Database Security**: SQLite file permissions, no remote access

#### API Security
- **CORS**: Cross-origin request validation
- **Rate Limiting**: API endpoint throttling
- **Input Sanitization**: All user inputs validated and sanitized
- **Error Handling**: No sensitive information in error responses

---

## 📚 APPENDIX

### A. Technology Stack
- **Backend**: Python 3.12, Flask, Gunicorn
- **Database**: SQLite (production), MySQL (optional)
- **Web Server**: Nginx with X-Accel-Redirect
- **Client**: HTML5, JavaScript (ES6+), CSS3
- **Storage**: Multi-backend (Local, NAS, S3, Azure, GCS)
- **Streaming**: HLS (HTTP Live Streaming)

### B. File Structure
```
/opt/nexvision/
├── app.py                      # Main Flask application (402KB)
├── storage_backends.py         # Multi-storage abstraction
├── vod_storage_admin.py        # Storage management API
├── nexvision.db               # SQLite database (4.9MB)
├── .env                       # Configuration (secured)
├── tv/
│   └── index.html             # TV client interface (199KB)
├── admin/
│   └── index.html             # Admin panel interface
├── docs/                      # Documentation
├── logs/                      # Application logs
├── backups/                   # Database backups
├── vod_data/                  # Local VOD storage
├── hls/                       # HLS stream segments
└── thumbnails/                # Video thumbnails
```

### C. Configuration Reference
See [STORAGE-QUICK-REFERENCE.md](STORAGE-QUICK-REFERENCE.md) for storage backend configuration details.

### D. Related Documentation
- [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) - Complete deployment procedures
- [SOB-System-Operations-Book.md](SOB-System-Operations-Book.md) - Operations manual
- [Server-Hardening-Procedure.md](Server-Hardening-Procedure.md) - Security procedures

---

**Document Revision History**:
- v1.0 (March 2026): Initial architecture documentation
- v2.0 (March 23, 2026): Updated with current system implementation, multi-storage backend, package bulk assignment

**Architecture Review Date**: March 23, 2026
**Next Review**: June 2026