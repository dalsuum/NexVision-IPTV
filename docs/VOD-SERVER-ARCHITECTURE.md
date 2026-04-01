# NexVision VOD Server Architecture

**Document Version**: 1.0 (March 2026)
**System Focus**: Video-on-Demand Streaming & Multi-Storage
**Last Updated**: March 23, 2026

> 🎨 **Interactive Diagram**: Open [vod-server-architecture.drawio](vod-server-architecture.drawio) in draw.io for the complete visual VOD architecture

---

## 🎬 VOD SERVER OVERVIEW

### VOD System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NexVision VOD Server Stack                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                           CLIENT LAYER                                      │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│   HLS Players   │  Mobile Apps    │  TV Clients     │   Admin Uploads         │
│ (Video.js/HLS.js│   (WebView)     │ (Hotel Rooms)   │  (Content Management)   │
├─────────────────┴─────────────────┴─────────────────┴─────────────────────────┤
│                          DELIVERY LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Nginx + X-Accel-Redirect (High-Performance Streaming)                      │
│  • HLS Segment Delivery • Adaptive Bitrate • CDN Integration • Caching      │
├─────────────────────────────────────────────────────────────────────────────┤
│                         APPLICATION LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Flask VOD API Server (Python 3.12)                                        │
│  • Authentication • Transcoding • Metadata • Analytics • Storage Abstraction│
├─────────────────────────────────────────────────────────────────────────────┤
│                         STORAGE ABSTRACTION                                 │
├─────────┬─────────┬─────────────┬─────────────┬───────────────┬─────────────┤
│ Local   │  NAS    │  Amazon S3  │Azure Blob   │ Google Cloud  │   Future    │
│ SSD/HDD │ Network │   Storage   │  Storage    │   Storage     │  Backends   │
├─────────┴─────────┴─────────────┴─────────────┴───────────────┴─────────────┤
│                            DATA PIPELINE                                    │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│    Ingest       │   Processing    │   Distribution  │      Analytics          │
│   (Upload)      │  (Transcoding)  │   (Streaming)   │   (View Tracking)       │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
```

---

## 💾 MULTI-STORAGE BACKEND SYSTEM

### 1. Storage Backend Architecture

#### Storage Abstraction Interface
```python
class StorageBackend(ABC):
    """Abstract base class for all storage backends"""

    @abstractmethod
    def upload_file(self, file_path: str, remote_path: str) -> Dict[str, Any]:
        """Upload file to storage backend"""
        pass

    @abstractmethod
    def get_file_url(self, remote_path: str) -> str:
        """Get streaming URL for file"""
        pass

    @abstractmethod
    def delete_file(self, remote_path: str) -> bool:
        """Delete file from storage"""
        pass

    @abstractmethod
    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List files in storage"""
        pass

    @abstractmethod
    def get_health_status(self) -> Dict[str, Any]:
        """Get backend health and statistics"""
        pass
```

#### Implemented Storage Backends

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Storage Backend Implementations                     │
├─────────────┬─────────────┬─────────────┬─────────────┬───────────────────────┤
│   Local     │     NAS     │  Amazon S3  │ Azure Blob  │   Google Cloud        │
│  Storage    │   Storage   │   Storage   │   Storage   │      Storage          │
├─────────────┼─────────────┼─────────────┼─────────────┼───────────────────────┤
│ Class:      │ Class:      │ Class:      │ Class:      │ Class:                │
│ LocalStorage│ NASStorage  │ S3Storage   │ AzureStorage│ GCSStorage            │
├─────────────┼─────────────┼─────────────┼─────────────┼───────────────────────┤
│ Config:     │ Config:     │ Config:     │ Config:     │ Config:               │
│ base_path   │ mount_point │ bucket      │ account     │ bucket                │
│             │ base_path   │ region      │ container   │ credentials_file      │
│             │ mount_cmd   │ access_key  │ account_key │ project_id            │
├─────────────┼─────────────┼─────────────┼─────────────┼───────────────────────┤
│ Performance:│ Performance:│ Performance:│ Performance:│ Performance:          │
│ Highest     │ High        │ Medium      │ Medium      │ Medium                │
│ (Direct I/O)│ (Network)   │ (API calls) │ (API calls) │ (API calls)           │
├─────────────┼─────────────┼─────────────┼─────────────┼───────────────────────┤
│ Scalability:│ Scalability:│ Scalability:│ Scalability:│ Scalability:          │
│ Limited     │ Medium      │ Unlimited   │ Unlimited   │ Unlimited             │
│ (Server HDD)│ (NAS size)  │ (Cloud)     │ (Cloud)     │ (Cloud)               │
└─────────────┴─────────────┴─────────────┴─────────────┴───────────────────────┘
```

### 2. Storage Selection Logic

```python
def get_storage_backend() -> StorageBackend:
    """Factory function to create appropriate storage backend"""

    storage_type = os.getenv('VOD_STORAGE_TYPE', 'local')
    storage_config = json.loads(os.getenv('VOD_STORAGE_CONFIG', '{}'))

    if storage_type == 'local':
        return LocalStorage(storage_config)
    elif storage_type == 'nas':
        return NASStorage(storage_config)
    elif storage_type == 's3':
        return S3Storage(storage_config)
    elif storage_type == 'azure':
        return AzureStorage(storage_config)
    elif storage_type == 'gcs':
        return GCSStorage(storage_config)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")
```

### 3. Storage Performance Comparison

| Storage Type | Upload Speed | Download Speed | Latency | Cost | Durability |
|-------------|--------------|----------------|---------|------|------------|
| **Local SSD** | 500 MB/s | 500 MB/s | < 1ms | Low | 99.9% |
| **Local HDD** | 150 MB/s | 150 MB/s | 5ms | Low | 99.9% |
| **NAS (1Gbps)** | 125 MB/s | 125 MB/s | 2ms | Medium | 99.99% |
| **Amazon S3** | 50-100 MB/s | 50-100 MB/s | 20-50ms | Medium | 99.999999999% |
| **Azure Blob** | 50-100 MB/s | 50-100 MB/s | 20-50ms | Medium | 99.999999999% |
| **Google GCS** | 50-100 MB/s | 50-100 MB/s | 20-50ms | Medium | 99.999999999% |

---

## 🎥 VIDEO PROCESSING PIPELINE

### 1. Content Ingestion Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   File Upload   │───▶│   Validation    │───▶│    Storage      │
│  (Admin Panel)  │    │ • Format check  │    │   Backend       │
│                 │    │ • Size limits   │    │  (Selected)     │
└─────────────────┘    │ • Virus scan    │    └─────────────────┘
                       └─────────────────┘             │
                                │                      │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Database     │◀───│   Metadata      │◀───│  File Analysis  │
│    Storage      │    │   Extraction    │    │ • Duration      │
│                 │    │                 │    │ • Resolution    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 2. HLS Transcoding Pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Source Video   │───▶│   FFmpeg        │───▶│  HLS Segments   │
│   (MP4/AVI/     │    │  Transcoding    │    │   (.ts files)   │
│    MOV/etc)     │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │                        │
                    ┌─────────────────┐    ┌─────────────────┐
                    │  Quality Levels │    │  Master Playlist│
                    │ • 240p (400kbps)│    │  (master.m3u8)  │
                    │ • 480p (800kbps)│    │                 │
                    │ • 720p (1.5Mbps)│    └─────────────────┘
                    │ • 1080p (3Mbps) │
                    └─────────────────┘
```

#### FFmpeg Command Example
```bash
# Generate HLS with multiple quality levels
ffmpeg -i input.mp4 \
  -filter_complex "[0:v]split=4[v1][v2][v3][v4]; \
  [v1]copy[v1out]; [v2]scale=854:480[v2out]; \
  [v3]scale=1280:720[v3out]; [v4]scale=1920:1080[v4out]" \
  -map "[v1out]" -c:v libx264 -b:v 400k -map 0:a -c:a aac -b:a 64k \
    -hls_time 10 -hls_playlist_type vod -f hls 240p/playlist.m3u8 \
  -map "[v2out]" -c:v libx264 -b:v 800k -map 0:a -c:a aac -b:a 128k \
    -hls_time 10 -hls_playlist_type vod -f hls 480p/playlist.m3u8 \
  -map "[v3out]" -c:v libx264 -b:v 1500k -map 0:a -c:a aac -b:a 128k \
    -hls_time 10 -hls_playlist_type vod -f hls 720p/playlist.m3u8 \
  -map "[v4out]" -c:v libx264 -b:v 3000k -map 0:a -c:a aac -b:a 192k \
    -hls_time 10 -hls_playlist_type vod -f hls 1080p/playlist.m3u8
```

### 3. Adaptive Bitrate Structure

```
movie-123/
├── master.m3u8              # Master playlist (adaptive bitrate selector)
├── 240p/
│   ├── playlist.m3u8        # 240p playlist
│   ├── segment000.ts        # Video segments
│   ├── segment001.ts
│   └── ...
├── 480p/
│   ├── playlist.m3u8
│   ├── segment000.ts
│   └── ...
├── 720p/
│   ├── playlist.m3u8
│   ├── segment000.ts
│   └── ...
└── 1080p/
    ├── playlist.m3u8
    ├── segment000.ts
    └── ...
```

---

## 🚀 HIGH-PERFORMANCE STREAMING

### 1. X-Accel-Redirect Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client        │    │   Flask App     │    │   Nginx         │
│  Request HLS    │───▶│  Authenticate   │───▶│  Serve File     │
│                 │    │  & Authorize    │    │  (Kernel Level) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       │                       │
         │              ┌─────────────────┐              │
         │             │ X-Accel-Redirect│              │
         │             │     Header      │              │
         │             └─────────────────┘              │
         │                                              │
         └──────────────────────────────────────────────┘
```

#### Performance Benefits
- **10x Faster**: Nginx serves files at kernel level vs Python I/O
- **Lower CPU**: Flask only handles auth, not file serving
- **Better Caching**: Nginx can cache frequently accessed segments
- **Concurrent Streams**: Handles 500+ streams simultaneously

#### Nginx Configuration
```nginx
location /vod/hls/ {
    # Public access point for HLS streams
    try_files $uri @vod_proxy;
}

location @vod_proxy {
    # Proxy to Flask for authentication
    proxy_pass http://YOUR_SERVER_IP_HERE:5000;
    proxy_set_header X-Original-URI $request_uri;
}

location /internal/vod/ {
    # Internal file serving (X-Accel-Redirect target)
    internal;
    alias /opt/nexvision/;

    # Performance optimizations
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;

    # Caching for HLS segments
    expires 1h;
    add_header Cache-Control "public, immutable";
}
```

### 2. Streaming Performance Optimizations

#### Client-Side (HLS.js Configuration)
```javascript
// Optimized HLS.js configuration for hotel TV
const hls = new Hls({
    // Buffer management
    maxBufferLength: 30,        // 30 second buffer
    maxMaxBufferLength: 60,     // Maximum buffer size

    // Quality selection
    startLevel: 1,              // Start with 480p
    capLevelToPlayerSize: true, // Adapt to player size

    // Network optimization
    manifestLoadingTimeOut: 10000,
    fragmentLoadingTimeOut: 20000,

    // Bandwidth adaptation
    abrEwmaSlowVoD: 0.95,      // Slow adaptation for VOD
    abrEwmaFastVoD: 0.99,      // Fast adaptation threshold
});
```

#### Server-Side Optimizations
```python
# Flask route optimization
@app.route('/vod/hls/<path:file_path>')
def serve_hls_content(file_path):
    # Fast authentication check
    if not authenticate_request():
        return abort(403)

    # Get storage backend file path
    storage_path = vod_storage.get_file_path(file_path)

    # Return X-Accel-Redirect header (no file content)
    response = make_response('')
    response.headers['X-Accel-Redirect'] = f'/internal/vod/{storage_path}'
    response.headers['Content-Type'] = get_mime_type(file_path)

    return response
```

### 3. CDN Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CDN Integration Options                       │
├─────────────┬─────────────────┬─────────────────┬─────────────────────┤
│   Origin    │ CloudFront      │   Azure CDN     │   Google Cloud      │
│   Server    │   (AWS)         │   (Microsoft)   │      CDN            │
├─────────────┼─────────────────┼─────────────────┼─────────────────────┤
│ NexVision   │ • Global Edge   │ • Verizon POP   │ • Google Edge       │
│ YOUR_SERVER_IP_HERE│ • S3 Backend    │ • Azure Blob    │ • GCS Backend       │ │ • Local Cache   │ • Auto-scaling  │ • Fast Purge    │ • ML Optimization   │
│ • Auth Check│ • SSL/HTTPS     │ • Custom Rules  │ • Analytics         │
└─────────────┴─────────────────┴─────────────────┴─────────────────────┘
```

---

## 📊 VOD DATABASE SCHEMA

### 1. VOD-Specific Tables

```sql
-- VOD Movies/Content
CREATE TABLE vod_movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    year INTEGER,
    rating VARCHAR(10),
    duration_minutes INTEGER,
    file_path VARCHAR(500),          -- Storage backend path
    thumbnail_url VARCHAR(500),
    category_id INTEGER,
    language VARCHAR(50),
    subtitle_languages VARCHAR(200), -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    featured BOOLEAN DEFAULT 0,
    active BOOLEAN DEFAULT 1,

    -- Streaming metadata
    hls_master_playlist VARCHAR(500), -- master.m3u8 path
    available_qualities VARCHAR(200), -- JSON: ["240p","480p","720p","1080p"]
    file_size_bytes BIGINT,
    transcoding_status ENUM('pending','processing','completed','failed'),

    FOREIGN KEY (category_id) REFERENCES vod_categories(id)
);

-- VOD Categories
CREATE TABLE vod_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parent_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT 1,

    FOREIGN KEY (parent_id) REFERENCES vod_categories(id)
);

-- Package-VOD Mapping
CREATE TABLE package_vod (
    package_id INTEGER NOT NULL,
    vod_id INTEGER NOT NULL,
    PRIMARY KEY (package_id, vod_id),
    FOREIGN KEY (package_id) REFERENCES content_packages(id),
    FOREIGN KEY (vod_id) REFERENCES vod_movies(id)
);

-- Watch History Analytics
CREATE TABLE watch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER,
    vod_id INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP NULL,
    position_seconds INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT 0,
    user_agent VARCHAR(500),

    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (vod_id) REFERENCES vod_movies(id)
);
```

### 2. Storage Backend Metadata

```sql
-- Storage backend tracking
CREATE TABLE storage_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vod_id INTEGER NOT NULL,
    backend_type ENUM('local','nas','s3','azure','gcs'),
    remote_path VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT,
    content_hash VARCHAR(64),        -- MD5/SHA256 for integrity
    upload_completed_at TIMESTAMP,
    health_check_at TIMESTAMP,
    health_status ENUM('ok','warning','error') DEFAULT 'ok',

    FOREIGN KEY (vod_id) REFERENCES vod_movies(id),
    UNIQUE(vod_id, backend_type)     -- One entry per VOD per backend
);
```

### 3. Performance Indexes

```sql
-- VOD query optimization
CREATE INDEX idx_vod_active ON vod_movies(active);
CREATE INDEX idx_vod_category ON vod_movies(category_id);
CREATE INDEX idx_vod_featured ON vod_movies(featured);
CREATE INDEX idx_vod_year ON vod_movies(year);

-- Package access optimization
CREATE INDEX idx_package_vod_pkg ON package_vod(package_id);
CREATE INDEX idx_package_vod_vod ON package_vod(vod_id);

-- Analytics optimization
CREATE INDEX idx_watch_room ON watch_history(room_id);
CREATE INDEX idx_watch_vod ON watch_history(vod_id);
CREATE INDEX idx_watch_date ON watch_history(started_at);

-- Storage backend optimization
CREATE INDEX idx_storage_backend ON storage_files(backend_type);
CREATE INDEX idx_storage_vod ON storage_files(vod_id);
CREATE INDEX idx_storage_health ON storage_files(health_status);
```

---

## 🔧 VOD API ENDPOINTS

### 1. Content Management API

```python
# VOD Library Management
@app.route('/api/vod', methods=['GET'])
def get_vod_library():
    """Get VOD library with filtering and pagination"""
    # Supports: ?category=1&featured=1&limit=50&offset=0

@app.route('/api/vod', methods=['POST'])
@admin_required
def upload_vod_content():
    """Upload new VOD content with metadata"""
    # Multipart file upload + JSON metadata

@app.route('/api/vod/<int:vod_id>', methods=['GET'])
def get_vod_details(vod_id):
    """Get detailed VOD information"""

@app.route('/api/vod/<int:vod_id>', methods=['PUT'])
@admin_required
def update_vod_metadata(vod_id):
    """Update VOD metadata (title, description, etc.)"""

@app.route('/api/vod/<int:vod_id>', methods=['DELETE'])
@admin_required
def delete_vod_content(vod_id):
    """Delete VOD from storage and database"""
```

### 2. Streaming API

```python
# HLS Stream Access
@app.route('/vod/hls/<path:file_path>')
def serve_hls_content(file_path):
    """Serve HLS content via X-Accel-Redirect"""
    # Authentication + X-Accel-Redirect header

@app.route('/api/vod/<int:vod_id>/stream-url')
def get_stream_url(vod_id):
    """Get authenticated streaming URL"""
    # Returns master.m3u8 URL with temporary token

@app.route('/api/vod/<int:vod_id>/progress', methods=['POST'])
def update_watch_progress(vod_id):
    """Update viewing progress for analytics"""
    # Room token + position tracking
```

### 3. Storage Management API

```python
# Multi-Storage Backend API
@app.route('/storage/health', methods=['GET'])
@admin_required
def storage_health_check():
    """Check health of all storage backends"""

@app.route('/storage/backends', methods=['GET'])
@admin_required
def list_storage_backends():
    """List available and configured backends"""

@app.route('/storage/migrate', methods=['POST'])
@admin_required
def migrate_storage_backend():
    """Migrate VOD content between storage backends"""

@app.route('/storage/analytics', methods=['GET'])
@admin_required
def storage_analytics():
    """Get storage usage and performance analytics"""
```

---

## 📈 ANALYTICS & MONITORING

### 1. VOD Analytics Schema

```python
# Real-time analytics structure
{
    "concurrent_streams": 45,
    "popular_content": [
        {"vod_id": 123, "title": "Movie A", "current_viewers": 12},
        {"vod_id": 456, "title": "Movie B", "current_viewers": 8}
    ],
    "bandwidth_usage": {
        "total_mbps": 150.5,
        "by_quality": {
            "240p": 20.2,
            "480p": 45.8,
            "720p": 60.1,
            "1080p": 24.4
        }
    },
    "storage_stats": {
        "backend_type": "s3",
        "total_size_gb": 2500.5,
        "monthly_cost_usd": 125.50,
        "availability_percentage": 99.95
    }
}
```

### 2. Performance Monitoring

#### Key Metrics to Track
```python
# VOD Performance KPIs
PERFORMANCE_METRICS = {
    "stream_start_time": {
        "target": "< 3 seconds",
        "current": "2.1 seconds avg"
    },
    "buffer_ratio": {
        "target": "< 1%",
        "current": "0.3%"
    },
    "concurrent_streams": {
        "target": "500 max",
        "current": "45 active"
    },
    "storage_response_time": {
        "local": "< 10ms",
        "nas": "< 50ms",
        "s3": "< 200ms",
        "azure": "< 200ms",
        "gcs": "< 200ms"
    }
}
```

#### Monitoring Dashboard Queries
```sql
-- Most popular VOD content (last 24 hours)
SELECT v.title, COUNT(*) as views, AVG(wh.position_seconds) as avg_watch_time
FROM watch_history wh
JOIN vod_movies v ON wh.vod_id = v.id
WHERE wh.started_at > datetime('now', '-1 day')
GROUP BY v.id, v.title
ORDER BY views DESC
LIMIT 10;

-- Storage backend performance
SELECT
    backend_type,
    COUNT(*) as file_count,
    SUM(file_size_bytes)/1024/1024/1024 as total_size_gb,
    AVG(CASE WHEN health_status = 'ok' THEN 1 ELSE 0 END) as health_percentage
FROM storage_files
GROUP BY backend_type;

-- Concurrent streaming analytics  SELECT
    DATE(started_at) as date,
    COUNT(*) as total_streams,
    COUNT(CASE WHEN completed = 1 THEN 1 END) as completed_streams,
    AVG(position_seconds) as avg_watch_duration
FROM watch_history
WHERE started_at > datetime('now', '-7 days')
GROUP BY DATE(started_at)
ORDER BY date DESC;
```

---

## 🚀 DEPLOYMENT CONFIGURATIONS

### 1. Single Server Deployment (Local Storage)

```yaml
# docker-compose.yml for containerized deployment
version: '3.8'

services:
  nexvision-app:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./vod_data:/app/vod_data
      - ./nexvision.db:/app/nexvision.db
    environment:
      - VOD_STORAGE_TYPE=local
      - VOD_STORAGE_CONFIG={"base_path": "/app/vod_data"}

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl/certs
      - ./vod_data:/var/www/vod_data:ro
    depends_on:
      - nexvision-app
```

### 2. Cloud Deployment (S3 Storage)

```bash
# AWS ECS Task Definition
{
  "family": "nexvision-vod",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/nexvision-ecs-role",
  "containerDefinitions": [
    {
      "name": "nexvision-app",
      "image": "nexvision:latest",
      "portMappings": [{"containerPort": 5000}],
      "environment": [
        {"name": "VOD_STORAGE_TYPE", "value": "s3"},
        {"name": "VOD_STORAGE_CONFIG", "value": "{\"bucket\":\"nexvision-vod\",\"region\":\"us-east-1\"}"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/nexvision-vod"
        }
      }
    }
  ]
}
```

### 3. Multi-Region Deployment

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Multi-Region Architecture                      │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┤
│   US East       │    US West      │     Europe      │   Asia Pacific  │
│ (Primary)       │   (Secondary)   │   (Secondary)   │   (Secondary)   │
├─────────────────┼─────────────────┼─────────────────┼─────────────────┤
│ • App Server    │ • App Server    │ • App Server    │ • App Server    │
│ • Master DB     │ • Replica DB    │ • Replica DB    │ • Replica DB    │
│ • S3 Primary    │ • S3 Replica    │ • S3 Replica    │ • S3 Replica    │
│ • CloudFront    │ • CloudFront    │ • CloudFront    │ • CloudFront    │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
                               │
                    ┌─────────────────┐
                    │  Global CDN      │
                    │  • Edge Caching  │
                    │  • Auto-failover │
                    │  • Geo-routing   │
                    └─────────────────┘
```

---

## 🔐 VOD SECURITY ARCHITECTURE

### 1. Content Protection

```python
# DRM and Content Security
class ContentSecurity:
    def generate_streaming_token(self, vod_id: int, room_token: str) -> str:
        """Generate time-limited streaming token"""
        expiry = datetime.utcnow() + timedelta(hours=2)
        payload = {
            'vod_id': vod_id,
            'room_token': room_token,
            'exp': expiry,
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

    def validate_streaming_token(self, token: str) -> Dict[str, Any]:
        """Validate and decode streaming token"""
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            raise SecurityException("Token expired")
        except jwt.InvalidTokenError:
            raise SecurityException("Invalid token")
```

### 2. Access Control Matrix

| Content Type | Guest Access | Admin Access | Package Required | Time Limit |
|-------------|--------------|--------------|------------------|------------|
| **Free VOD** | ✅ Yes | ✅ Yes | ❌ No | None |
| **Premium VOD** | ❌ No | ✅ Yes | ✅ Premium+ | None |
| **Pay-per-View** | 🎫 Token | ✅ Yes | 💰 Purchase | 24-48h |
| **Adult Content** | 🔒 PIN | ✅ Yes | ✅ Adult | None |
| **Live Recordings** | ✅ Room Only | ✅ Yes | ✅ Same as Live | 7 days |

### 3. Storage Security

```python
# Storage Backend Security Configuration
STORAGE_SECURITY_CONFIG = {
    "s3": {
        "encryption": "AES-256",
        "access_control": "IAM + Bucket Policies",
        "audit_logging": "CloudTrail",
        "backup": "Cross-region replication"
    },
    "azure": {
        "encryption": "Azure SSE",
        "access_control": "RBAC + SAS tokens",
        "audit_logging": "Azure Monitor",
        "backup": "Geo-redundant storage"
    },
    "gcs": {
        "encryption": "Google-managed keys",
        "access_control": "IAM + ACLs",
        "audit_logging": "Cloud Audit Logs",
        "backup": "Multi-regional buckets"
    },
    "local": {
        "encryption": "LUKS disk encryption",
        "access_control": "File system permissions",
        "audit_logging": "auditd + fail2ban",
        "backup": "Scheduled rsync/tar"
    }
}
```

---

## 📚 TROUBLESHOOTING GUIDE

### 1. Common VOD Issues

#### Issue: "Video won't load/play"
**Symptoms**: Player shows loading spinner indefinitely
**Diagnosis**:
```bash
# Check HLS playlist accessibility  curl -I http://YOUR_SERVER_IP_HERE/vod/hls/movie-123/master.m3u8

# Check X-Accel-Redirect configuration
tail -f /var/log/nginx/error.log

# Test storage backend connectivity  curl -s http://YOUR_SERVER_IP_HERE/storage/health | jq .
```

#### Issue: "Slow streaming/buffering"
**Symptoms**: Frequent pauses, poor quality selection
**Diagnosis**:
```bash
# Check server bandwidth utilization
iftop -i eth0

# Monitor storage I/O
iostat -x 1

# Check HLS segment generation
ls -la /opt/nexvision/vod_data/movie-123/*/segment*.ts
```

#### Issue: "Storage backend failures"
**Symptoms**: Upload failures, missing files
**Diagnosis**:
```python
# Python debug script
import json
from storage_backends import get_storage_backend

try:
    backend = get_storage_backend()
    health = backend.get_health_status()
    print(json.dumps(health, indent=2))
except Exception as e:
    print(f"Storage backend error: {e}")
```

### 2. Performance Troubleshooting

```bash
# VOD Performance Analysis Script
#!/bin/bash

echo "=== VOD Server Performance Analysis ==="

echo "1. Active HLS streams:"
netstat -an | grep :80 | grep ESTABLISHED | wc -l

echo "2. Storage I/O:"
iostat -x 1 1 | grep -E "Device|vod_data"

echo "3. Memory usage:"
free -h

echo "4. Top CPU processes:"
ps aux --sort=-%cpu | head -10

echo "5. Nginx worker status:"
ps aux | grep nginx

echo "6. Recent errors:"
tail -n 20 /var/log/nginx/error.log
```

---

## 📊 APPENDIX

### A. Storage Backend Comparison Matrix

| Feature | Local | NAS | S3 | Azure | GCS |
|---------|--------|-----|-----|-------|-----|
| **Setup Complexity** | Low | Medium | Medium | Medium | Medium |
| **Initial Cost** | Low | Medium | Low | Low | Low |
| **Operational Cost** | Low | Medium | Variable | Variable | Variable |
| **Performance** | Highest | High | Medium | Medium | Medium |
| **Scalability** | Limited | Limited | Unlimited | Unlimited | Unlimited |
| **Durability** | 99.9% | 99.99% | 99.999999999% | 99.999999999% | 99.999999999% |
| **Backup** | Manual | RAID | Auto | Auto | Auto |
| **CDN Integration** | No | No | Yes | Yes | Yes |
| **Global Distribution** | No | No | Yes | Yes | Yes |

### B. HLS Quality Profiles

```json
{
  "quality_profiles": {
    "240p": {
      "resolution": "426x240",
      "video_bitrate": 400,
      "audio_bitrate": 64,
      "codec": "h264/aac",
      "target_audience": "Low bandwidth/Mobile"
    },
    "480p": {
      "resolution": "854x480",
      "video_bitrate": 800,
      "audio_bitrate": 128,
      "codec": "h264/aac",
      "target_audience": "Standard TV"
    },
    "720p": {
      "resolution": "1280x720",
      "video_bitrate": 1500,
      "audio_bitrate": 128,
      "codec": "h264/aac",
      "target_audience": "HD TV"
    },
    "1080p": {
      "resolution": "1920x1080",
      "video_bitrate": 3000,
      "audio_bitrate": 192,
      "codec": "h264/aac",
      "target_audience": "Full HD TV"
    }
  }
}
```

### C. API Response Examples

```json
// GET /api/vod response
{
  "movies": [
    {
      "id": 123,
      "title": "Sample Movie",
      "description": "A great movie for hotel guests",
      "year": 2024,
      "rating": "PG-13",
      "duration_minutes": 120,
      "thumbnail_url": "/vod/thumbnails/123.jpg",
      "category": "Action",
      "available_qualities": ["240p", "480p", "720p", "1080p"],
      "hls_url": "/vod/hls/123/master.m3u8",
      "file_size_gb": 2.5,
      "transcoding_status": "completed"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}

// GET /storage/health response
{
  "backend_type": "s3",
  "status": "healthy",
  "total_files": 1250,
  "total_size_gb": 3500.5,
  "last_health_check": "2026-03-23T10:30:00Z",
  "response_time_ms": 45,
  "error_rate_24h": 0.02,
  "available_space_gb": "unlimited"
}
```

---

**Document Revision History**:
- v1.0 (March 23, 2026): Initial VOD server architecture documentation

**Architecture Review**: March 23, 2026
**Next Review**: June 2026

*This document focuses specifically on the VOD (Video-on-Demand) components of the NexVision IPTV platform. For complete system architecture, refer to [NEXVISION-ARCHITECTURE.md](NEXVISION-ARCHITECTURE.md).*