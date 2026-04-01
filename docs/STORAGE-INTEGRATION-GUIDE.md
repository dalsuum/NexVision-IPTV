# NexVision Multi-Storage Integration Guide

This guide shows how to integrate the `storage_backends.py` module into your NexVision Flask app to support multiple storage backends.

## Quick Start

### 1. Install Backend Dependencies

```bash
# For S3
pip install boto3 botocore

# For Azure
pip install azure-storage-blob

# For GCS (optional)
pip install google-cloud-storage
```

### 2. Configure Environment

Create or update `.env`:

```ini
# ═════════════════════════════════════════════════════════════════
# STORAGE BACKEND SELECTION
# ═════════════════════════════════════════════════════════════════

# Options: local, nas, s3, azure, gcs
STORAGE_BACKEND=local

# ─── LOCAL STORAGE ──────────────────────────────────────────────────
VOD_DATA_DIR=./vod_data
# or for absolute path: VOD_DATA_DIR=/var/vod/data

# ─── NAS STORAGE ────────────────────────────────────────────────────
# NAS_MOUNT=/mnt/nas/vod

# ─── AWS S3 ─────────────────────────────────────────────────────────
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY=AKIA...
# AWS_SECRET_KEY=...
# S3_BUCKET_UPLOADS=nexvision-uploads
# S3_BUCKET_HLS=nexvision-hls
# CLOUDFRONT_URL=https://d123.cloudfront.net

# ─── AZURE BLOB ──────────────────────────────────────────────────────
# AZURE_STORAGE_ACCOUNT=mystorageaccount
# AZURE_STORAGE_KEY=...
# AZURE_CDN_URL=https://mycdn.azureedge.net

# ─── GOOGLE CLOUD STORAGE ───────────────────────────────────────────
# GCP_PROJECT_ID=my-project
# GCS_BUCKET=nexvision-vod
```

### 3. Integration Points in app.py

Below are the key changes needed in your Flask app.

#### A. Import and Initialize Storage

```python
# At the top of app.py
from storage_backends import get_storage_backend, create_health_check_route

# After Flask app creation
storage = get_storage_backend()
logger.info(f"Storage backend: {type(storage).__name__}")

# Add health check endpoint
create_health_check_route(app)
```

#### B. Replace Video Upload Handler

**Current code (to replace):**
```python
@app.route('/api/vod/upload', methods=['POST'])
def upload_video():
    # ... existing code ...
    video_path = os.path.join(VIDEOS_DIR, f"{video_id}.mp4")
    request.files['video'].save(video_path)
```

**New code (with storage abstraction):**
```python
@app.route('/api/vod/upload', methods=['POST'])
def upload_video():
    """Upload video with multi-backend support"""
    from werkzeug.utils import secure_filename
    import tempfile
    
    # Validate
    if 'video' not in request.files:
        return {'error': 'No video file'}, 400
    
    video_file = request.files['video']
    if not video_file.filename:
        return {'error': 'Empty filename'}, 400
    
    # Get video ID from database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    video_id = cursor.fetchone()[0] + 1
    
    try:
        # Save to temporary location first
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            video_file.save(tmp.name)
            temp_path = tmp.name
        
        # Save to configured storage backend
        storage_path = storage.save_upload(video_id, temp_path)
        
        # Store metadata in database
        cursor.execute("""
            INSERT INTO videos (id, title, storage_path, status)
            VALUES (?, ?, ?, 'pending')
        """, (video_id, video_file.filename, storage_path))
        conn.commit()
        
        # Queue transcoding job
        queue_transcode_job(video_id, storage_path)
        
        return {
            'video_id': video_id,
            'filename': secure_filename(video_file.filename),
            'status': 'transcoding',
            'storage_path': storage_path
        }, 201
    
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {'error': str(e)}, 500
    
    finally:
        # Cleanup temp file
        try:
            os.unlink(temp_path)
        except:
            pass
```

#### C. Replace Transcoding Handler

**New transcoding with multi-backend output:**

```python
def transcode_video(video_id: int, source_path: str):
    """
    Transcode video to HLS with multi-backend support
    
    Args:
        video_id: Video ID
        source_path: Path to source video (local or S3/Azure path)
    """
    import tempfile
    import subprocess
    from pathlib import Path
    
    temp_dir = tempfile.mkdtemp(prefix=f"transcode_{video_id}_")
    
    try:
        # Ensure source is local (download from cloud if needed)
        if source_path.startswith('s3://'):
            local_src = os.path.join(temp_dir, 'source.mp4')
            storage.download_s3_file(source_path, local_src)
        elif source_path.startswith('azure://'):
            local_src = os.path.join(temp_dir, 'source.mp4')
            storage.download_azure_file(source_path, local_src)
        else:
            local_src = source_path
        
        # Transcode to HLS
        output_base = os.path.join(temp_dir, 'output')
        os.makedirs(output_base, exist_ok=True)
        
        qualities = ['360p', '480p', '720p']  # Adjust as needed
        
        for quality in qualities:
            width, height, vbr, abr = QUALITY_PROFILES[quality]
            
            quality_dir = os.path.join(output_base, quality)
            os.makedirs(quality_dir, exist_ok=True)
            
            cmd = [
                FFMPEG_BIN,
                '-i', local_src,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-s', f'{width}x{height}',
                '-b:v', vbr,
                '-b:a', abr,
                '-hls_time', '4',
                '-hls_list_size', '0',
                os.path.join(quality_dir, 'index.m3u8')
            ]
            
            subprocess.run(cmd, check=True)
            
            # Upload segments to storage backend
            for segment_file in Path(quality_dir).glob('*.ts'):
                url = storage.upload_hls_segment(
                    video_id, quality, str(segment_file)
                )
                logger.info(f"Uploaded {quality}: {url}")
        
        # Generate thumbnail
        thumb_path = os.path.join(temp_dir, 'thumb.jpg')
        cmd = [
            FFPROBE_BIN, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1:nozero=1',
            local_src
        ]
        try:
            duration = float(subprocess.check_output(cmd).decode().strip())
            thumb_time = int(duration * 0.1)  # 10% into video
        except:
            thumb_time = 5
        
        cmd = [
            FFMPEG_BIN,
            '-ss', str(thumb_time),
            '-i', local_src,
            '-vframes', '1',
            '-vf', 'scale=320:180',
            thumb_path
        ]
        
        subprocess.run(cmd, check=True)
        thumb_url = storage.upload_thumbnail(video_id, thumb_path)
        
        # Update database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE videos 
            SET status = 'ready',
                hls_url = ?,
                thumbnail_url = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (storage.get_hls_url(video_id), thumb_url, video_id))
        conn.commit()
        
        logger.info(f"Transcoding completed: video_id={video_id}")
        
    except Exception as e:
        logger.error(f"Transcoding failed for {video_id}: {e}")
        
        # Update database with error
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE videos 
            SET status = 'error', error_msg = ?
            WHERE id = ?
        """, (str(e), video_id))
        conn.commit()
    
    finally:
        # Cleanup temporary files
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


# Celery background task (for distributed transcoding)
from celery import Celery

celery = Celery('vod_transcoder', broker=os.getenv('REDIS_URL', 'redis://localhost:6379'))

@celery.task(bind=True, max_retries=3)
def transcode_video_task(self, video_id: int, source_path: str):
    """Celery task for async transcoding"""
    try:
        transcode_video(video_id, source_path)
        return {'status': 'completed', 'video_id': video_id}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# Queue transcoding job
def queue_transcode_job(video_id: int, source_path: str):
    """Queue transcoding job (async or sync)"""
    if os.getenv('USE_CELERY') == '1':
        # Async via Celery
        transcode_video_task.apply_async(
            args=(video_id, source_path),
            countdown=10
        )
    else:
        # Sync (for development)
        transcode_video(video_id, source_path)
```

#### D. Replace HLS Serving Route

**Current code:**
```python
@app.route('/vod/hls/<int:video_id>/<path:filename>')
def serve_hls(video_id, filename):
    return send_from_directory(os.path.join(HLS_DIR, str(video_id)), filename)
```

**New code (with CDN awareness):**
```python
@app.route('/api/vod/video/<int:video_id>/master.m3u8')
def get_hls_manifest(video_id):
    """GET /api/vod/video/{id}/master.m3u8 - Get HLS master manifest URL"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT hls_url, status FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    
    if not row:
        return {'error': 'Video not found'}, 404
    
    hls_url, status = row
    
    if status != 'ready':
        return {'error': f'Video not ready: {status}'}, 412
    
    return {
        'video_id': video_id,
        'hls_url': hls_url,  # CloudFront, CDN, or local URL
        'status': status
    }

# For local storage, still serve directly
@app.route('/vod/hls/<int:video_id>/<path:filename>')
def serve_hls_local(video_id, filename):
    """Serve HLS segments (local storage only)"""
    # This only works for local/NAS storage
    # Cloud backends return URLs directly
    
    backend_name = os.getenv('STORAGE_BACKEND', 'local')
    if backend_name not in ['local', 'nas']:
        return {'error': 'Not available for cloud storage'}, 403
    
    return send_from_directory(
        os.path.join(storage.hls_dir, str(video_id)),
        filename
    )
```

#### E. Add Storage Status Endpoint

```python
@app.route('/api/admin/storage/info')
def storage_info():
    """GET /api/admin/storage/info - Get storage configuration and stats"""
    try:
        health = storage.check_health()
        stats = storage.get_storage_stats()
        
        return {
            'backend': type(storage).__name__,
            'health': health,
            'stats': stats,
            'config': {
                'backend_name': os.getenv('STORAGE_BACKEND', 'local'),
                'vod_data_dir': os.getenv('VOD_DATA_DIR'),
                'cloudfront_url': os.getenv('CLOUDFRONT_URL'),
                'azure_cdn_url': os.getenv('AZURE_CDN_URL'),
            }
        }
    except Exception as e:
        return {'error': str(e)}, 500


@app.route('/api/admin/storage/test')
def test_storage():
    """GET /api/admin/storage/test - Test storage connectivity"""
    import tempfile
    
    try:
        # Create test file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test data")
            tmp_path = tmp.name
        
        # Save to storage
        storage.save_upload(999999, tmp_path)
        os.unlink(tmp_path)
        
        return {
            'status': 'ok',
            'message': 'Storage backend is accessible',
            'backend': type(storage).__name__
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'backend': type(storage).__name__
        }, 500
```

## Environment Examples

### Example 1: Local Storage (Development)

```bash
STORAGE_BACKEND=local
VOD_DATA_DIR=./vod_data
```

**Test:**
```bash
curl http://localhost:5000/api/admin/storage/info
```

### Example 2: NAS (Hotel/On-Prem)

```bash
STORAGE_BACKEND=nas
VOD_DATA_DIR=/mnt/nas/vod
```

**Setup NAS mount first:**
```bash
sudo mount -t nfs 192.168.1.10:/export/vod /mnt/nas/vod
```

### Example 3: AWS S3 + CloudFront

```bash
STORAGE_BACKEND=s3
AWS_REGION=us-east-1
AWS_ACCESS_KEY=AKIA...
AWS_SECRET_KEY=...
S3_BUCKET_UPLOADS=nexvision-uploads
S3_BUCKET_HLS=nexvision-hls
CLOUDFRONT_URL=https://d123.cloudfront.net
```

**Deploy CloudFront:**
```bash
# Use Terraform or AWS Console
# Create S3 bucket + CloudFront distribution
# Update .env with CloudFront domain name
```

### Example 4: Azure Blob + CDN

```bash
STORAGE_BACKEND=azure
AZURE_STORAGE_ACCOUNT=mystorageaccount
AZURE_STORAGE_KEY=...
AZURE_CDN_URL=https://mycdn.azureedge.net
```

### Example 5: Hybrid (NAS + S3 Archive)

```bash
# Primary: NAS for hot content
STORAGE_BACKEND=nas
VOD_DATA_DIR=/mnt/nas/vod

# Archive: S3 for cold storage (implemented separately)
# Cron job: Move videos >90 days old to Glacier
```

## Testing & Validation

### Test Script

```bash
# Run storage backend tests
python3 storage_backends.py
```

### Manual Testing with curl

```bash
# 1. Check health
curl http://localhost:5000/api/admin/storage/info

# 2. Upload test video
curl -X POST -F "video=@test.mp4" \
  http://localhost:5000/api/vod/upload

# 3. Check HLS URL
curl http://localhost:5000/api/vod/video/1/master.m3u8

# 4. Play in video client
# Update TV interface to use returned HLS URL
```

## Migration Guide: Local → NAS → Cloud

### Step 1: Verify Current Setup

```bash
# Check current VOD data
du -sh /opt/nexvision/vod_data

# List videos
ls -la /opt/nexvision/videos/
```

### Step 2: Add NAS (Dual-write Phase)

```bash
# 1. Mount NAS
sudo mount -t nfs 192.168.1.10:/export/vod /mnt/nas/vod

# 2. Copy current data to NAS
rsync -avz /opt/nexvision/vod_data/ /mnt/nas/vod/

# 3. Update .env to use NAS
STORAGE_BACKEND=nas
VOD_DATA_DIR=/mnt/nas/vod

# 4. Restart Flask app
sudo systemctl restart nexvision

# 5. Verify health
curl http://localhost:5000/api/admin/storage/info

# 6. Keep local disk as backup for 1 week
# Then: rm -rf /opt/nexvision/vod_data
```

### Step 3: Add S3 for New Content

```bash
# 1. Create S3 buckets + CloudFront in AWS

# 2. Update .env with S3 credentials

# 3. Implement dual-write (NAS + S3):
# - Store in NAS for immediate playback (CDN)
# - Upload to S3 for archive/DR

# 4. For old content: Use Migration tool
# boto3 copy from NAS → S3

# 5. Update serving logic:
# - If video in NAS: return NAS URL
# - Else: return S3 CloudFront URL
```

## Cost Estimation

For 100 hotel rooms, 500 video catalog:

| Backend | Monthly Cost | Bandwidth | Storage | Notes |
|---------|------|-----------|---------|-------|
| **Local Only** | $0 | Limited | 2TB | Hardware cost upfront |
| **NAS + Local** | $200 | 10Gbps | 24TB | CAPEX: $15k |
| **S3 + CloudFront** | $2,500 | Unlimited | Unlimited | Pay-as-you-go, global |
| **Hybrid (NAS + S3)** | $800 | 50Mbps avg | 12TB NAS + S3 | Best of both |

## Rollback Plan

If migration fails:

```bash
# Revert to local storage
STORAGE_BACKEND=local
VOD_DATA_DIR=/opt/nexvision/vod_data

# Restart
sudo systemctl restart nexvision

# Restore from backup
rsync -avz /backup/vod_data/ /opt/nexvision/vod_data/
```

## Support & Debugging

### Check logs

```bash
# Flask logs
tail -f /var/log/nexvision/app.log | grep storage

# Storage errors
tail -f /var/log/nexvision/app.log | grep "Storage\|S3\|Azure\|NAS"
```

### Test connectivity

```python
# Python shell
from storage_backends import get_storage_backend

storage = get_storage_backend()
print(storage.check_health())
print(storage.get_storage_stats())
```

### Monitoring

```bash
# Watch storage stats
watch 'curl -s http://localhost:5000/api/admin/storage/info | jq .'

# Monitor disk I/O (NAS)
iostat -x 1 | head -20
```

---

**Next Steps:**
1. Choose storage backend from Section 8 of VOD-Storage-Architecture.md
2. Configure environment variables
3. Integrate code snippets into app.py
4. Test with test script
5. Deploy to production using migration guide
