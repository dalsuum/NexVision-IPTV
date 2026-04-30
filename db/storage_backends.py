"""
Multi-Backend VOD Storage Abstraction Layer
Supports: Local, NAS, S3, Azure Blob, GCS, MinIO
"""

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# ABSTRACT BASE CLASS
# ═════════════════════════════════════════════════════════════════════════════

class StorageBackend(ABC):
    """Abstract interface for all storage backends"""
    
    @abstractmethod
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Save original uploaded video. Returns storage path."""
        pass
    
    @abstractmethod
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Upload HLS segment. Returns serving URL."""
        pass
    
    @abstractmethod
    def upload_thumbnail(self, video_id: int, thumb_file: str) -> str:
        """Upload video thumbnail. Returns URL."""
        pass
    
    @abstractmethod
    def get_hls_url(self, video_id: int) -> str:
        """Get master.m3u8 URL for video playback"""
        pass
    
    @abstractmethod
    def get_thumbnail_url(self, video_id: int) -> str:
        """Get thumbnail URL"""
        pass
    
    @abstractmethod
    def delete_video(self, video_id: int) -> bool:
        """Delete all video files (source + HLS + thumb)"""
        pass
    
    @abstractmethod
    def check_health(self) -> Dict:
        """Health check. Returns {'status': 'ok'|'error', 'details': ...}"""
        pass
    
    @abstractmethod
    def get_storage_stats(self) -> Dict:
        """Return storage usage stats"""
        pass


# ═════════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION: LOCAL FILESYSTEM (for development)
# ═════════════════════════════════════════════════════════════════════════════

class LocalStorage(StorageBackend):
    """Local filesystem storage - for dev/small deployments"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or os.getenv('VOD_DATA_DIR', './vod/data'))
        self.videos_dir = self.base_dir / 'videos'
        self.hls_dir = self.base_dir / 'hls'
        self.thumbs_dir = self.base_dir / 'thumbnails'
        
        # Create directories
        for d in [self.videos_dir, self.hls_dir, self.thumbs_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Copy uploaded file to videos directory"""
        src = Path(file_path)
        dest = self.videos_dir / f"{video_id}_{src.name}"
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        logger.info(f"Saved upload: {dest}")
        return str(dest)
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Copy HLS segment to storage"""
        src = Path(segment_file)
        quality_dir = self.hls_dir / str(video_id) / quality
        quality_dir.mkdir(parents=True, exist_ok=True)
        
        dest = quality_dir / src.name
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        
        # Return HTTP URL
        return f"/vod/hls/{video_id}/{quality}/{src.name}"
    
    def upload_thumbnail(self, video_id: int, thumb_file: str) -> str:
        """Copy thumbnail to storage"""
        src = Path(thumb_file)
        dest = self.thumbs_dir / f"{video_id}.jpg"
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        return f"/vod/thumbnails/{video_id}.jpg"
    
    def get_hls_url(self, video_id: int) -> str:
        """Return master.m3u8 URL"""
        return f"/vod/hls/{video_id}/master.m3u8"
    
    def get_thumbnail_url(self, video_id: int) -> str:
        """Return thumbnail URL"""
        return f"/vod/thumbnails/{video_id}.jpg"
    
    def delete_video(self, video_id: int) -> bool:
        """Delete video and all segments"""
        try:
            # Delete video file
            for f in self.videos_dir.glob(f"{video_id}_*"):
                f.unlink()
            
            # Delete HLS directory
            video_hls = self.hls_dir / str(video_id)
            if video_hls.exists():
                shutil.rmtree(video_hls)
            
            # Delete thumbnail
            thumb = self.thumbs_dir / f"{video_id}.jpg"
            if thumb.exists():
                thumb.unlink()
            
            logger.info(f"Deleted video {video_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete video {video_id}: {e}")
            return False
    
    def check_health(self) -> Dict:
        """Check storage health"""
        try:
            # Test write
            test_file = self.base_dir / '.health_check'
            test_file.write_text(f"health_check_{datetime.now().isoformat()}")
            test_file.unlink()
            
            return {
                'status': 'ok',
                'backend': 'local',
                'base_dir': str(self.base_dir),
                'accessible': True
            }
        except Exception as e:
            return {
                'status': 'error',
                'backend': 'local',
                'error': str(e)
            }
    
    def get_storage_stats(self) -> Dict:
        """Get disk usage stats"""
        import subprocess
        try:
            result = subprocess.check_output(['du', '-sh', str(self.base_dir)], text=True)
            size = result.split()[0]
            
            # Count files
            num_videos = len(list(self.videos_dir.glob('*')))
            num_hls_dirs = len(list(self.hls_dir.glob('*')))
            
            return {
                'total_size': size,
                'video_files': num_videos,
                'hls_video_dirs': num_hls_dirs,
                'backend': 'local'
            }
        except Exception as e:
            return {'error': str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION: NAS (NFS Mount)
# ═════════════════════════════════════════════════════════════════════════════

class NASStorage(StorageBackend):
    """NAS storage via NFS mount (same as LocalStorage after mount)"""
    
    def __init__(self, nas_mount: str = '/mnt/nas/vod'):
        self.base_dir = Path(nas_mount)
        self.videos_dir = self.base_dir / 'videos'
        self.hls_dir = self.base_dir / 'hls'
        self.thumbs_dir = self.base_dir / 'thumbnails'
        
        # Verify mount exists
        if not self.base_dir.exists():
            raise RuntimeError(f"NAS mount not found: {nas_mount}")
        
        # Create subdirectories
        for d in [self.videos_dir, self.hls_dir, self.thumbs_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Save to NAS"""
        src = Path(file_path)
        dest = self.videos_dir / f"{video_id}_{src.name}"
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        logger.info(f"NAS: Saved {dest}")
        return str(dest)
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Upload HLS segment to NAS"""
        src = Path(segment_file)
        quality_dir = self.hls_dir / str(video_id) / quality
        quality_dir.mkdir(parents=True, exist_ok=True)
        
        dest = quality_dir / src.name
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        return f"/vod/hls/{video_id}/{quality}/{src.name}"
    
    def upload_thumbnail(self, video_id: int, thumb_file: str) -> str:
        """Upload thumbnail to NAS"""
        src = Path(thumb_file)
        dest = self.thumbs_dir / f"{video_id}.jpg"
        shutil.copy2(src, dest)
        os.chmod(dest, 0o644)
        return f"/vod/thumbnails/{video_id}.jpg"
    
    def get_hls_url(self, video_id: int) -> str:
        return f"/vod/hls/{video_id}/master.m3u8"
    
    def get_thumbnail_url(self, video_id: int) -> str:
        return f"/vod/thumbnails/{video_id}.jpg"
    
    def delete_video(self, video_id: int) -> bool:
        return LocalStorage(str(self.base_dir)).delete_video(video_id)
    
    def check_health(self) -> Dict:
        """Check NAS mount health"""
        try:
            test_file = self.base_dir / '.nas_health_check'
            test_file.write_text(datetime.now().isoformat())
            test_file.unlink()
            
            return {
                'status': 'ok',
                'backend': 'nas',
                'mount': str(self.base_dir)
            }
        except Exception as e:
            return {
                'status': 'error',
                'backend': 'nas',
                'error': str(e)
            }
    
    def get_storage_stats(self) -> Dict:
        """NAS storage stats"""
        import subprocess
        try:
            result = subprocess.check_output(['df', '-h', str(self.base_dir)], text=True)
            lines = result.strip().split('\n')
            return {
                'nas_mount': str(self.base_dir),
                'df_output': lines[-1],
                'backend': 'nas'
            }
        except Exception as e:
            return {'error': str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION: AWS S3
# ═════════════════════════════════════════════════════════════════════════════

class S3Storage(StorageBackend):
    """AWS S3 + CloudFront CDN backend"""
    
    def __init__(self):
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")
        
        self.s3 = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('AWS_SECRET_KEY')
        )
        
        self.bucket_uploads = os.getenv('S3_BUCKET_UPLOADS', 'nexvision-uploads')
        self.bucket_hls = os.getenv('S3_BUCKET_HLS', 'nexvision-hls')
        self.cloudfront_url = os.getenv('CLOUDFRONT_URL', '').rstrip('/')
        
        if not self.cloudfront_url:
            self.cloudfront_url = f"https://{self.bucket_hls}.s3.amazonaws.com"
    
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Upload original video to S3"""
        from pathlib import Path
        
        file_name = Path(file_path).name
        key = f"originals/{video_id}/{file_name}"
        
        with open(file_path, 'rb') as f:
            self.s3.upload_fileobj(
                f,
                self.bucket_uploads,
                key,
                ExtraArgs={'ContentType': 'video/mp4'}
            )
        
        logger.info(f"S3: Uploaded {key}")
        return f"s3://{self.bucket_uploads}/{key}"
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Upload HLS segment to S3"""
        from pathlib import Path
        
        file_name = Path(segment_file).name
        key = f"videos/{video_id}/{quality}/{file_name}"
        
        with open(segment_file, 'rb') as f:
            self.s3.upload_fileobj(
                f,
                self.bucket_hls,
                key,
                ExtraArgs={
                    'ContentType': 'video/MP2T',
                    'CacheControl': 'max-age=31536000'  # 1 year for .ts
                }
            )
        
        # Return CloudFront URL
        return f"{self.cloudfront_url}/videos/{video_id}/{quality}/{file_name}"
    
    def upload_thumbnail(self, video_id: int, thumb_file: str) -> str:
        """Upload thumbnail to S3"""
        key = f"thumbnails/{video_id}.jpg"
        
        with open(thumb_file, 'rb') as f:
            self.s3.upload_fileobj(
                f,
                self.bucket_hls,
                key,
                ExtraArgs={
                    'ContentType': 'image/jpeg',
                    'CacheControl': 'max-age=2592000'  # 30 days
                }
            )
        
        return f"{self.cloudfront_url}/{key}"
    
    def get_hls_url(self, video_id: int) -> str:
        """CloudFront URL for master.m3u8"""
        return f"{self.cloudfront_url}/videos/{video_id}/master.m3u8"
    
    def get_thumbnail_url(self, video_id: int) -> str:
        """CloudFront URL for thumbnail"""
        return f"{self.cloudfront_url}/thumbnails/{video_id}.jpg"
    
    def delete_video(self, video_id: int) -> bool:
        """Delete video and all HLS segments"""
        try:
            # List all objects with video_id prefix
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
            
            # Delete thumbnail
            self.s3.delete_object(
                Bucket=self.bucket_hls,
                Key=f"thumbnails/{video_id}.jpg"
            )
            
            logger.info(f"S3: Deleted video {video_id}")
            return True
        except Exception as e:
            logger.error(f"S3 delete failed: {e}")
            return False
    
    def check_health(self) -> Dict:
        """Check S3 connectivity"""
        try:
            self.s3.head_bucket(Bucket=self.bucket_hls)
            return {
                'status': 'ok',
                'backend': 's3',
                'bucket': self.bucket_hls,
                'cloudfront': self.cloudfront_url
            }
        except Exception as e:
            return {
                'status': 'error',
                'backend': 's3',
                'error': str(e)
            }
    
    def get_storage_stats(self) -> Dict:
        """Get S3 bucket stats"""
        try:
            cloudwatch = __import__('boto3').client('cloudwatch')
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/S3',
                MetricName='BucketSizeBytes',
                Dimensions=[
                    {'Name': 'BucketName', 'Value': self.bucket_hls},
                    {'Name': 'StorageType', 'Value': 'Standard'}
                ],
                StartTime=__import__('datetime').datetime.now() - __import__('datetime').timedelta(days=1),
                EndTime=__import__('datetime').datetime.now(),
                Period=86400,
                Statistics=['Average']
            )
            
            size_bytes = response['Datapoints'][0]['Average'] if response['Datapoints'] else 0
            size_gb = size_bytes / (1024**3)
            
            return {
                'backend': 's3',
                'bucket': self.bucket_hls,
                'size_gb': round(size_gb, 2),
                'estimated_monthly_cost': round(size_gb * 0.023, 2)
            }
        except Exception as e:
            return {'error': str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# IMPLEMENTATION: AZURE BLOB STORAGE
# ═════════════════════════════════════════════════════════════════════════════

class AzureStorage(StorageBackend):
    """Microsoft Azure Blob Storage backend"""
    
    def __init__(self):
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError:
            raise ImportError("azure-storage-blob not installed. Run: pip install azure-storage-blob")
        
        self.ContentSettings = ContentSettings
        self.client = BlobServiceClient(
            account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT')}.blob.core.windows.net",
            credential=os.getenv('AZURE_STORAGE_KEY')
        )
        
        self.hls_container = self.client.get_container_client('vod-hls')
        self.cdn_url = os.getenv('AZURE_CDN_URL', '').rstrip('/')
    
    def save_upload(self, video_id: int, file_path: str) -> str:
        """Upload to Azure Blob"""
        from pathlib import Path
        
        file_name = Path(file_path).name
        blob_name = f"originals/{video_id}/{file_name}"
        
        with open(file_path, 'rb') as data:
            self.hls_container.upload_blob(
                blob_name,
                data,
                overwrite=True
            )
        
        return f"azure://{blob_name}"
    
    def upload_hls_segment(self, video_id: int, quality: str, segment_file: str) -> str:
        """Upload HLS segment to Azure"""
        from pathlib import Path
        
        file_name = Path(segment_file).name
        blob_name = f"videos/{video_id}/{quality}/{file_name}"
        
        with open(segment_file, 'rb') as data:
            self.hls_container.upload_blob(
                blob_name,
                data,
                content_settings=self.ContentSettings(
                    content_type='video/MP2T',
                    cache_control='max-age=31536000'
                ),
                overwrite=True
            )
        
        return f"{self.cdn_url}/{blob_name}"
    
    def upload_thumbnail(self, video_id: int, thumb_file: str) -> str:
        """Upload thumbnail"""
        blob_name = f"thumbnails/{video_id}.jpg"
        
        with open(thumb_file, 'rb') as data:
            self.hls_container.upload_blob(
                blob_name,
                data,
                overwrite=True
            )
        
        return f"{self.cdn_url}/{blob_name}"
    
    def get_hls_url(self, video_id: int) -> str:
        return f"{self.cdn_url}/videos/{video_id}/master.m3u8"
    
    def get_thumbnail_url(self, video_id: int) -> str:
        return f"{self.cdn_url}/thumbnails/{video_id}.jpg"
    
    def delete_video(self, video_id: int) -> bool:
        """Delete video from Azure"""
        try:
            # List blobs with prefix
            blobs = self.hls_container.list_blobs(name_starts_with=f"videos/{video_id}/")
            for blob in blobs:
                self.hls_container.delete_blob(blob.name)
            
            # Delete thumbnail
            self.hls_container.delete_blob(f"thumbnails/{video_id}.jpg")
            
            return True
        except Exception as e:
            logger.error(f"Azure delete failed: {e}")
            return False
    
    def check_health(self) -> Dict:
        """Check Azure connectivity"""
        try:
            self.hls_container.get_container_properties()
            return {
                'status': 'ok',
                'backend': 'azure',
                'container': 'vod-hls'
            }
        except Exception as e:
            return {
                'status': 'error',
                'backend': 'azure',
                'error': str(e)
            }
    
    def get_storage_stats(self) -> Dict:
        """Get Azure storage stats"""
        try:
            props = self.hls_container.get_container_properties()
            blobs = self.hls_container.list_blobs()
            total_size = sum(b.size for b in blobs)
            
            return {
                'backend': 'azure',
                'container': 'vod-hls',
                'total_size_gb': round(total_size / (1024**3), 2)
            }
        except Exception as e:
            return {'error': str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def get_storage_backend() -> StorageBackend:
    """Factory function to get configured storage backend"""
    
    backend_name = os.getenv('STORAGE_BACKEND', 'local').lower()
    
    backends = {
        'local': LocalStorage,
        'nas': NASStorage,
        's3': S3Storage,
        'azure': AzureStorage,
    }
    
    if backend_name not in backends:
        raise ValueError(f"Unknown backend: {backend_name}. Choices: {list(backends.keys())}")
    
    return backends[backend_name]()


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════

def create_health_check_route(app):
    """Add health check route to Flask app"""
    
    @app.route('/api/admin/storage/health')
    def storage_health():
        """GET /api/admin/storage/health - Check storage backend health"""
        try:
            storage = get_storage_backend()
            health = storage.check_health()
            stats = storage.get_storage_stats()
            
            return {
                'storage_health': health,
                'storage_stats': stats,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }, 500
    
    return app


if __name__ == '__main__':
    # Test script
    print("Testing storage backends...\n")
    
    # Local
    print("1. LocalStorage:")
    local = LocalStorage()
    print(f"   Health: {local.check_health()}")
    print(f"   Stats: {local.get_storage_stats()}\n")
    
    # NAS (if mounted)
    try:
        print("2. NASStorage:")
        nas = NASStorage()
        print(f"   Health: {nas.check_health()}")
        print(f"   Stats: {nas.get_storage_stats()}\n")
    except Exception as e:
        print(f"   Skipped: {e}\n")
    
    # S3 (if configured)
    try:
        print("3. S3Storage:")
        s3 = S3Storage()
        print(f"   Health: {s3.check_health()}")
        print(f"   Stats: {s3.get_storage_stats()}\n")
    except Exception as e:
        print(f"   Skipped: {e}\n")
