# NexVision VOD Storage Architecture Guide

## Executive Summary

VOD systems require scalable, reliable, and cost-effective storage solutions. This guide presents a **multi-tier hybrid storage approach** supporting local, NAS, cloud, and distributed file servers—enabling you to scale from 10 to 10,000 concurrent viewers.

---

## 1. Current VOD Architecture (Single Server)

### Current Setup
```
NexVision Server (Flask)
├── /videos/           ← Original uploaded MP4 files
├── /hls/              ← Transcoded HLS segments (master.m3u8 + .ts chunks)
├── /thumbnails/       ← Video preview images
├── /uploads/          ← UI assets, images, logos
└── vod.db            ← Video metadata (SQLite or MySQL)
```

### Current Flow
1. **Upload** → `/videos/myfilm.mp4`
2. **Transcode** → FFmpeg generates `/hls/VIDEO_ID/{360p,480p,720p,1080p}/`
3. **Serve** → Nginx X-Accel-Redirect returns `/vod/hls/{id}/master.m3u8`
4. **Play** → HLS.js requests `*.ts` segments sequentially

### Limitations
- Single point of failure (server crash = downtime)
- Limited to local disk capacity (~2TB max cost-effective)
- No regional CDN distribution
- Transcoding couples upload + storage
- Difficult to add concurrent transcoders

---

## 2. Industry Standard VOD Topologies

### 2A. Netflix Model (Distributed Transcoding + CDN)
```
Upload Queue (S3)
    ↓
Transcoding Workers (Lambda/EC2 fleet) → Output to S3
    ↓
CloudFront CDN (edge caching)
    ↓
Client HLS playback
```
**Best for:** >5000 concurrent users, enterprise budgets

---

### 2B. YouTube/Vimeo Model (Primary + Secondary Storage)
```
Upload → Primary Storage (GCS/S3)
    ↓
Transcode Farm (dedicated VMs)
    ↓
Primary HLS Output (GCS/S3)
    ↓
CDN Cache Layer (CloudFlare/Cloudfront)
    ↓
Client playback
```
**Best for:** 100-10,000 concurrent users, mid-market

---

### 2C. Local Enterprise Model (NAS + File Server)
```
Upload → Local NAS (fast I/O, RAID-6)
    ↓
Transcode (local CPU + GPU)
    ↓
HLS Output → NAS + File Server (rsync/NFS replication)
    ↓
Nginx reverse proxy + X-Accel-Redirect
    ↓
Client playback
```
**Best for:** Hotels, broadcasters, <500 concurrent users, on-prem only, low latency

---

## 3. Recommended Hybrid Architecture (NexVision Optimized)

### 3A. Multi-Tier Storage Design

```
┌─────────────────────────────────────────────────────────┐
│ TIER 1: UPLOAD INGEST (NAS or Cloud)                    │
│ • Receives user uploads via /api/upload                 │
│ • Atomic commit to storage                              │
│ • Backup-friendly format (original files)               │
└─────────────┬───────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────┐
│ TIER 2: TRANSCODE WORKER (local or cloud)               │
│ • Reads from Tier 1                                     │
│ • Generates HLS segments (360p→1080p)                   │
│ • Writes output to Tier 3                               │
│ • Generates thumbnails → Tier 3                         │
└─────────────┬───────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────┐
│ TIER 3: HLS DELIVERY (fast read, replicated)            │
│ • Master m3u8 + .ts segment files                       │
│ • Replicated across multiple nodes (HA)                 │
│ • Served via CDN or direct HTTP                         │
│ • Archived to cold storage (optional)                   │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Storage Backend Options

### Option A: Local Server + NAS (Hotel/On-Prem)

#### Architecture
```
Nginx (HTTP)
    ↓
Flask App (app.py)
    ↓
NAS (via NFS/SMB mount)
├── /mnt/nas/vod/videos/     ← Original uploads
├── /mnt/nas/vod/hls/        ← HLS segments
├── /mnt/nas/vod/thumbnails/ ← Previews
└── /mnt/nas/vod/vod.db      ← Metadata

File Server (rsync/iSCSI backup)
└── /storage/vod/hls/        ← HLS content mirror
```

#### Setup: Mount NAS via NFS
```bash
# Install NFS client
sudo apt-get install nfs-common

# Create mount point
sudo mkdir -p /mnt/nas/vod
sudo chown nexvision:nexvision /mnt/nas/vod

# Mount NAS (persistent in /etc/fstab)
echo "YOUR_NAS_SERVER_IP:/export/vod /mnt/nas/vod nfs defaults,vers=4.1,soft,timeo=600 0 0" | sudo tee -a /etc/fstab
sudo mount -a

# Test mount
df -h /mnt/nas/vod
```

#### Update app.py Environment
```bash
# .env
VOD_DATA_DIR=/mnt/nas/vod
TRANSCODE_WORKER_THREADS=4
```

#### Python wrapper for NAS storage
```python
import os
from pathlib import Path
from shutil import copy2

class NASStorage:
    def __init__(self, base_path='/mnt/nas/vod'):
        self.base_path = Path(base_path)
        self.videos_dir = self.base_path / 'videos'
        self.hls_dir = self.base_path / 'hls'
        self.thumbs_dir = self.base_path / 'thumbnails'
        
    def save_upload(self, video_id: int, file_path: str):
        """Copy uploaded file to NAS"""
        dest = self.videos_dir / f"{video_id}_{Path(file_path).name}"
        copy2(file_path, dest)
        os.chmod(dest, 0o644)
        return str(dest)
    
    def get_hls_url(self, video_id: int) -> str:
        """Return HTTP URL for HLS master.m3u8"""
        return f"/vod/hls/{video_id}/master.m3u8"
    
    def check_bandwidth(self) -> dict:
        """Monitor NAS I/O health"""
        import subprocess
        iostat = subprocess.check_output(
            ['iostat', '-x', '1', '2'], 
            text=True
        ).split('\n')
        return {'io_util': iostat}
```

#### Pros & Cons
| Pros | Cons |
|------|------|
| ✅ Low latency (LAN) | ❌ Capital expense (NAS hardware) |
| ✅ Fast transcoding | ❌ Limited scaling beyond 1-2 servers |
| ✅ No bandwidth costs | ❌ Power/cooling costs |
| ✅ Full data control | ❌ Manual HA setup |
| ✅ Suitable for <500 concurrent users | ❌ Regional distribution requires replication |

#### Recommended NAS Specs
- **Model:** QNAP TS-432PXU / Synology RS1220+
- **Capacity:** 12TB-48TB (Raid-6 protection)
- **Network:** 10GbE or dual Gigabit for bonding
- **Cost:** $3,000-$15,000 + disks

---

### Option B: AWS S3 + CloudFront CDN

#### Architecture
```
Flask App
    ↓ boto3
AWS S3 Buckets
├── nexvision-uploads/   ← Original video uploads
├── nexvision-hls/       ← HLS segments
└── nexvision-thumbs/    ← Thumbnails
    ↓
CloudFront Distribution (CDN)
    ↓
Client playback (multi-region)
```

#### Setup: S3 Client in Python
```python
import boto3
from pathlib import Path
import os

class S3Storage:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('AWS_SECRET_KEY')
        )
        self.bucket_uploads = os.getenv('S3_BUCKET_UPLOADS', 'nexvision-uploads')
        self.bucket_hls = os.getenv('S3_BUCKET_HLS', 'nexvision-hls')
        self.cloudfront_url = os.getenv('CLOUDFRONT_URL', 'https://d123.cloudfront.net')
    
    def upload_video(self, video_id: int, file_path: str) -> dict:
        """Upload original video to S3"""
        key = f"originals/{video_id}/{Path(file_path).name}"
        with open(file_path, 'rb') as f:
            self.s3.upload_fileobj(
                f, 
                self.bucket_uploads, 
                key,
                ExtraArgs={'ContentType': 'video/mp4'},
                Callback=self._upload_progress
            )
        return {
            'bucket': self.bucket_uploads,
            'key': key,
            's3_url': f"s3://{self.bucket_uploads}/{key}"
        }
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str):
        """Upload transcoded HLS segment to S3"""
        key = f"videos/{video_id}/{quality}/{Path(segment_file).name}"
        with open(segment_file, 'rb') as f:
            self.s3.upload_fileobj(
                f, 
                self.bucket_hls, 
                key,
                ExtraArgs={
                    'ContentType': 'video/MP2T',
                    'CacheControl': 'max-age=31536000'  # 1 year cache for .ts files
                }
            )
        return key
    
    def get_hls_url(self, video_id: int) -> str:
        """Return CDN URL for HLS master.m3u8"""
        # CloudFront origin: s3://nexvision-hls/
        return f"{self.cloudfront_url}/videos/{video_id}/master.m3u8"
    
    def generate_signed_url(self, video_id: int, expiration_hrs: int = 24) -> str:
        """Generate temporary signed URL (for geo-blocking)"""
        key = f"videos/{video_id}/master.m3u8"
        url = self.s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_hls, 'Key': key},
            ExpiresIn=expiration_hrs * 3600
        )
        return url
    
    def delete_video(self, video_id: int):
        """Delete video and all HLS segments"""
        # List all objects with prefix
        response = self.s3.list_objects_v2(
            Bucket=self.bucket_hls,
            Prefix=f"videos/{video_id}/"
        )
        
        if 'Contents' in response:
            objects = [{'Key': obj['Key']} for obj in response['Contents']]
            self.s3.delete_objects(
                Bucket=self.bucket_hls,
                Delete={'Objects': objects}
            )
    
    def get_storage_stats(self) -> dict:
        """Monitor S3 usage and costs"""
        from datetime import datetime, timedelta
        import json
        
        cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/S3',
            MetricName='BucketSizeBytes',
            Dimensions=[
                {'Name': 'BucketName', 'Value': self.bucket_hls},
                {'Name': 'StorageType', 'Value': 'Standard'}
            ],
            StartTime=datetime.now() - timedelta(days=1),
            EndTime=datetime.now(),
            Period=86400,
            Statistics=['Average']
        )
        return response['Datapoints']
    
    @staticmethod
    def _upload_progress(bytes_amount):
        """Callback for upload progress tracking"""
        print(f"Uploaded {bytes_amount / 1024 / 1024:.1f} MB")
```

#### Terraform: CloudFront + S3 Setup
```hcl
# variables.tf
variable "domain_name" {
  default = "vod.myhotel.com"
}

# main.tf
resource "aws_s3_bucket" "vod_hls" {
  bucket = "nexvision-hls-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "vod_hls" {
  bucket = aws_s3_bucket.vod_hls.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_cloudfront_distribution" "vod" {
  origin {
    domain_name = aws_s3_bucket.vod_hls.bucket_regional_domain_name
    origin_id   = "S3Origin"
    
    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.oai.cloudfront_access_identity_path
    }
  }

  enabled = true
  default_root_object = "master.m3u8"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Origin"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "https-only"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}
```

#### Cost Estimation
| Metric | Monthly Cost |
|--------|------|
| 1TB S3 Storage | $23 |
| 10TB data transfer out | $900 |
| CloudFront | ~$0.085/GB | 
| **Total (10TB/mo transfer)** | **$1,100-1,500** |

#### Pros & Cons
| Pros | Cons |
|------|------|
| ✅ Global CDN distribution | ❌ Vendor lock-in (AWS) |
| ✅ Fully managed (no ops) | ❌ Data egress costs ($0.085/GB) |
| ✅ Infinite scalability | ❌ Latency for uploads (~100ms) |
| ✅ Built-in HA/DR | ❌ Complexity (IAM, buckets, policies) |
| ✅ Auto-scaling transcoding (Lambda) | ❌ Learning curve (boto3, CloudFront) |

---

### Option C: Azure Blob + CDN

#### Similar to AWS S3 but:
- **Cheaper egress:** $0.08/GB (vs AWS $0.085/GB)
- **Blob Tiers:** Hot ($0.018/GB), Cool ($0.01/GB), Archive ($0.002/GB)
- **Syncing:** AzCopy for bulk transfers

```python
from azure.storage.blob import BlobServiceClient, ContentSettings
import os

class AzureStorage:
    def __init__(self):
        self.client = BlobServiceClient(
            account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT')}.blob.core.windows.net",
            credential=os.getenv('AZURE_STORAGE_KEY')
        )
        self.hls_container = self.client.get_container_client('vod-hls')
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str):
        """Upload to Azure Blob"""
        blob_name = f"videos/{video_id}/{quality}/{Path(segment_file).name}"
        
        with open(segment_file, 'rb') as data:
            self.hls_container.upload_blob(
                blob_name, 
                data,
                content_settings=ContentSettings(
                    content_type='video/MP2T',
                    cache_control='max-age=31536000'
                ),
                overwrite=True
            )
        
        return f"https://{os.getenv('AZURE_CDN_URL')}/{blob_name}"
```

---

### Option D: Google Cloud Storage (GCS) + CDN

#### Pros
- **Pricing:** $0.02/GB (cheaper than AWS for downloads)
- **Performance:** 0-RTT retrieval with Cloud CDN
- **Integration:** Seamless with BigQuery for analytics

```python
from google.cloud import storage
from pathlib import Path

class GCSStorage:
    def __init__(self):
        self.client = storage.Client(project=os.getenv('GCP_PROJECT_ID'))
        self.bucket = self.client.bucket(os.getenv('GCS_BUCKET', 'nexvision-vod'))
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str):
        """Upload to GCS"""
        blob_path = f"videos/{video_id}/{quality}/{Path(segment_file).name}"
        blob = self.bucket.blob(blob_path)
        
        blob.upload_from_filename(
            segment_file,
            content_type='video/MP2T'
        )
        
        blob.cache_control = 'public, max-age=31536000'
        blob.patch()
        
        return blob.public_url
```

---

### Option E: MinIO (Self-Hosted S3-Compatible)

#### For on-prem + cloud hybrid
```bash
# Deploy MinIO with Docker
docker run -d \
  --name minio \
  -p 9000:9000 -p 9001:9001 \
  -v /data/minio:/data \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=$(openssl rand -base64 32)" \
  minio/minio:latest \
  server /data --console-address ":9001"

# Client code (same as AWS S3!)
boto3_client = boto3.client(
    's3',
    endpoint_url='http://minioselfhosted:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='password'
)
```

**Advantage:** Write once, switch cloud providers later (S3 API compatibility)

---

## 5. Distributed Transcoding Farm

For high volume, separate transcoding from serving:

```python
# transcoder_worker.py
from celery import Celery
import subprocess
import json
from pathlib import Path

app = Celery('vod_transcoder', broker='redis://YOUR_REDIS_SERVER:6379')

@app.task(bind=True, max_retries=3)
def transcode_video(self, video_id: int, input_path: str, qualities: list):
    """
    Celery background worker for transcoding
    Fetches source from storage, transcodes, uploads output
    """
    try:
        storage = get_storage_backend()  # S3, NAS, GCS, etc.
        
        # Download from storage
        local_file = f"/tmp/source_{video_id}.mp4"
        storage.download_file(input_path, local_file)
        
        # Transcode to each quality
        output_base = f"/tmp/output_{video_id}"
        Path(output_base).mkdir(exist_ok=True)
        
        for quality in qualities:
            width, height, bitrate, audio_bitrate = QUALITY_PROFILES[quality]
            
            cmd = [
                'ffmpeg', '-i', local_file,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-s', f"{width}x{height}",
                '-b:v', bitrate,
                '-b:a', audio_bitrate,
                '-hls_time', '4',
                '-hls_list_size', '0',
                f"{output_base}/{quality}/index.m3u8"
            ]
            
            subprocess.run(cmd, check=True)
        
        # Upload results back to storage
        for quality in qualities:
            quality_dir = Path(output_base) / quality
            for segment_file in quality_dir.glob('*.ts'):
                storage.upload_hls_segment(
                    video_id, quality, str(segment_file)
                )
        
        # Cleanup
        import shutil
        shutil.rmtree(output_base)
        os.remove(local_file)
        
        return {'status': 'completed', 'video_id': video_id, 'qualities': qualities}
        
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

# In app.py:
@app.route('/api/vod/video/upload', methods=['POST'])
def upload_video_handler():
    # Save to storage
    storage.save_upload(video_id, uploaded_file)
    
    # Queue transcoding job
    transcode_video.apply_async(
        args=(video_id, upload_path, ['360p', '480p', '720p']),
        countdown=10
    )
    
    return {'video_id': video_id, 'status': 'transcoding'}
```

**Horizontal Scaling:**
```bash
# Start multiple workers
celery -A transcoder_worker worker -n worker1.%h -Q transcode --concurrency=2
celery -A transcoder_worker worker -n worker2.%h -Q transcode --concurrency=2
celery -A transcoder_worker worker -n worker3.%h -Q transcode --concurrency=2

# Monitor queue
celery -A transcoder_worker inspect active
```

---

## 6. Multi-Storage Abstraction Layer

Create a storage abstraction layer to swap backends without code changes:

```python
# storage_interface.py
from abc import ABC, abstractmethod
from typing import Optional

class StorageBackend(ABC):
    """Abstract base for all storage backends"""
    
    @abstractmethod
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Save original video, return storage path"""
        pass
    
    @abstractmethod
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Upload HLS segment, return serving URL"""
        pass
    
    @abstractmethod
    def get_hls_url(self, video_id: int) -> str:
        """Return master.m3u8 URL"""
        pass
    
    @abstractmethod
    def delete_video(self, video_id: int):
        """Delete all video files"""
        pass
    
    @abstractmethod
    def check_health(self) -> bool:
        """Health check for storage"""
        pass

# In app.py initialization
def get_storage_backend() -> StorageBackend:
    backend_name = os.getenv('STORAGE_BACKEND', 'local')
    
    if backend_name == 'local':
        return LocalStorage()
    elif backend_name == 's3':
        return S3Storage()
    elif backend_name == 'azure':
        return AzureStorage()
    elif backend_name == 'gcs':
        return GCSStorage()
    elif backend_name == 'nas':
        return NASStorage()
    else:
        raise ValueError(f"Unknown storage backend: {backend_name}")

# Use anywhere in Flask
storage = get_storage_backend()
storage.upload_hls_segment(video_id, '720p', segment_file)
```

---

## 7. Comparison Matrix

| Feature | Local | NAS | S3 | Azure | GCS | MinIO |
|---------|-------|-----|----|----|-----|-------|
| **Setup Time** | 5 min | 30 min | 1 hr | 1 hr | 1 hr | 30 min |
| **Scalability** | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Data Egress Cost** | Free | Free | $0.085/GB | $0.08/GB | $0.02/GB | Free |
| **Max Concurrent Users** | 100 | 500 | 100k+ | 100k+ | 100k+ | 1k |
| **HA/Failover** | Manual | RAID-6 | Built-in | Built-in | Built-in | Manual |
| **Latency** | <1ms | <5ms | 100ms | 100ms | 80ms | <5ms |
| **Suitable For** | Dev/Demo | Hotels | Enterprise | Enterprise | Enterprise | Hybrid |
| **Provider Lockin** | None | Hardware | AWS | Azure | Google | None |

---

## 8. Recommended Setups by Use Case

### 8A: Small Hotel (1-5 rooms, <50 guests)
```
Recommended: Local storage + NAS backup
├── Primary: 2TB NAS (QNAP TS-432)
├── Backup: USB external drive (weekly rsync)
├── Cost: ~$4,000 one-time
├── Mgmt: 2 hours/month
└── Users: up to 100 concurrent
```
**Implementation:**
```bash
# Mount NAS
echo "YOUR_NAS_SERVER_IP:/vod /mnt/nas/vod nfs defaults" >> /etc/fstab

# app.py env
VOD_DATA_DIR=/mnt/nas/vod
```

---

### 8B: Medium Hotel (20-50 rooms, <500 guests)
```
Recommended: NAS + File Server + S3 Glacier Archive
├── Primary: 12TB NAS (hot content)
├── Secondary: 2x File Servers (HA replication)
├── Archive: S3 Glacier (old videos, $0.004/GB)
├── Cost: $15,000 CAPEX + $200/month OPEX
├── Mgmt: 4 hours/month
└── Users: up to 500 concurrent
```
**Implementation:**
```python
# Hybrid storage strategy
if video.age_days < 30:
    backend = NASStorage()  # Hot
elif video.age_days < 365:
    backend = FileServerStorage()  # Warm
else:
    backend = S3GlacierStorage()  # Cold (archive)
```

---

### 8C: Broadcast / Large Chain (100+ hotels)
```
Recommended: All backends with orchestration
├── Upload Queue: S3
├── Transcoding: Lambda fleet (auto-scale)
├── Serving: CloudFront CDN (200+ edge)
├── Archive: Glacier for 1+ year old content
├── Failover: Multi-region S3 replica
├── Cost: $2,000-5,000/month
├── Mgmt: 10 hours/month + DevOps
└── Users: 10k+ concurrent globally
```

**Architecture Diagram:**
```
Broadcast Center
    ↓ (ingest)
S3 Upload Bucket
    ↓ (trigger)
Lambda Transcoder Farm (100+ concurrent)
    ↓ (output)
CloudFront Distribution (200+ edge nodes)
    ↓
400 Hotels Worldwide
    ├─ EU: 100 hotels
    ├─ APAC: 150 hotels
    ├─ Americas: 150 hotels
    └─ Each: 3,000 guests/month
```

---

## 9. Migration Path: Local → Hybrid → Cloud

### Phase 1: Local Only (Current)
```
app.py → /videos/ (local disk)
```

### Phase 2: Add NAS Mirror (Today)
```
app.py → /mnt/nas/vod  (NF S mount)
         + rsync to backup server nightly
```

### Phase 3: Separate Transcoding (Next)
```
Upload → S3 / NAS
Transcode → Celery workers (fleet)
Serve → NAS + CloudFront CDN
```

### Phase 4: Full Cloud (Scale)
```
Upload → S3
Transcode → Lambda
Serve → CloudFront
Archive → Glacier
```

---

## 10. Implementation Checklist

- [ ] **Assess current storage** → Run `du -sh /videos /hls /thumbnails`
- [ ] **Choose backend** → Based on section 8 (hotel size)
- [ ] **Deploy storage** → NAS, cloud account, MinIO, etc.
- [ ] **Create abstraction layer** → Implement `StorageBackend` interface
- [ ] **Add health checks** → Monitor storage availability
- [ ] **Setup replication** → rsync, S3 cross-region, etc.
- [ ] **Test failover** → Kill primary storage, verify fallback works
- [ ] **Document runbooks** → Backup, recovery, expansion procedures
- [ ] **Cost monitoring** → CloudWatch, Azure Monitor, etc.
- [ ] **Security audit** → Access control, encryption, data retention

---

## 11. Code Examples Summary

### Quick Start: NAS
```bash
# .env
STORAGE_BACKEND=nas
VOD_DATA_DIR=/mnt/nas/vod

# Mount
sudo mount -t nfs YOUR_NAS_SERVER_IP:/export/vod /mnt/nas/vod
```

### Quick Start: AWS S3
```bash
# .env
STORAGE_BACKEND=s3
AWS_REGION=us-east-1
AWS_ACCESS_KEY=AKIA...
AWS_SECRET_KEY=...
S3_BUCKET_HLS=nexvision-vod
CLOUDFRONT_URL=https://d123.cloudfront.net

# Install
pip install boto3 botocore
```

### Quick Start: Azure
```bash
# .env
STORAGE_BACKEND=azure
AZURE_STORAGE_ACCOUNT=mystorageaccount
AZURE_STORAGE_KEY=...
AZURE_CDN_URL=https://mycdn.azureedge.net

# Install
pip install azure-storage-blob
```

---

## References

- **AWS:** https://docs.aws.amazon.com/s3/latest/userguide/
- **Azure:** https://docs.microsoft.com/azure/storage/
- **GCS:** https://cloud.google.com/storage/docs
- **MinIO:** https://docs.min.io/
- **HLS Spec:** https://tools.ietf.org/html/rfc8216
- **FFmpeg HLS:** https://ffmpeg.org/ffmpeg-formats.html#hls-1
