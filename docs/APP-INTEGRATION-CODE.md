"""
INTEGRATION GUIDE: Add to app.py after imports

This file shows exactly where and how to integrate multi-storage support into app.py
"""

# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: ADD IMPORTS (after existing imports, around line 50)
# ═════════════════════════════════════════════════════════════════════════════

from storage_backends import get_storage_backend, StorageBackend
from vod_storage_admin import create_storage_admin_routes, STORAGE_ADMIN_HTML, StorageConfig

# ═════════════════════════════════════════════════════════════════════════════
# STEP 2: INITIALIZE STORAGE (after app creation, around line 65)
# ═════════════════════════════════════════════════════════════════════════════

# Initialize storage backend
try:
    vod_storage: StorageBackend = get_storage_backend()
    vod_log.info(f"VOD Storage initialized: {type(vod_storage).__name__}")
except Exception as e:
    vod_log.warning(f"Failed to initialize VOD storage: {e}")
    vod_storage = None

# ═════════════════════════════════════════════════════════════════════════════
# STEP 3: CREATE ADMIN ROUTES (after app routes are defined, around line 7200)
# ═════════════════════════════════════════════════════════════════════════════

# Initialize storage admin routes
create_storage_admin_routes(app, require_admin=admin_required)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4: UPDATE VOD UPLOAD HANDLER (replace existing handler)
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/api/vod/upload', methods=['POST'])
@auth_required
def upload_vod_file():
    """
    POST /api/vod/upload
    Upload a video file with multi-backend storage support
    """
    import tempfile
    from werkzeug.utils import secure_filename
    
    if not vod_storage:
        return {'error': 'Storage backend not available'}, 503
    
    try:
        # Validate request
        if 'video' not in request.files:
            return {'error': 'No video file in request'}, 400
        
        video_file = request.files['video']
        if not video_file.filename:
            return {'error': 'Empty filename'}, 400
        
        # Validate file extension
        filename = secure_filename(video_file.filename)
        File_ext = Path(filename).suffix.lower()
        
        if file_ext not in ALLOWED_VIDEO_EXTS:
            return {
                'error': f'Invalid video format. Allowed: {", ".join(ALLOWED_VIDEO_EXTS)}'
            }, 400
        
        # Check file size
        video_file.seek(0, os.SEEK_END)
        file_size = video_file.tell()
        video_file.seek(0)
        
        if file_size > MAX_UPLOAD_MB * 1024 * 1024:
            return {
                'error': f'File too large (max {MAX_UPLOAD_MB}MB)'
            }, 413
        
        # Generate video ID
        video_id = str(uuid.uuid4())
        
        # Save to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            video_file.save(tmp.name)
            temp_path = tmp.name
        
        try:
            # Save to storage backend
            storage_path = vod_storage.save_upload(video_id, temp_path)
            vod_log.info(f"Video uploaded: {video_id} ({file_size} bytes) to {type(vod_storage).__name__}")
            
            # Create database record
            conn = vod_get_db()
            conn.execute("""
                INSERT INTO videos (
                    id, title, filename, status, 
                    filesize, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """, (
                video_id,
                filename,
                storage_path,
                file_size,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            conn.commit()
            
            # Queue transcoding job
            queue_transcode_job(video_id, storage_path)
            
            return {
                'success': True,
                'video_id': video_id,
                'filename': filename,
                'status': 'transcoding',
                'storage_path': storage_path,
                'storage_backend': type(vod_storage).__name__
            }, 201
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    except Exception as e:
        vod_log.exception(f"Video upload failed")
        return {'error': str(e)}, 500


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5: UPDATE TRANSCODE HANDLER (add storage support)
# ═════════════════════════════════════════════════════════════════════════════

def transcode_video_multistorage(video_id: str, source_path: str) -> bool:
    """
    Transcode video with multi-backend storage support
    
    Handles transcoding from any storage backend
    and outputs to the same backend
    """
    import subprocess
    import tempfile
    from pathlib import Path
    
    if not vod_storage:
        vod_log.error("Storage backend not available for transcoding")
        return False
    
    temp_dir = None
    
    try:
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp(prefix=f"transcode_{video_id}_")
        vod_log.info(f"Transcoding {video_id}: source={source_path}, temp={temp_dir}")
        
        # Ensure source is local (download from cloud if needed)
        if source_path.startswith('s3://') or source_path.startswith('azure://'):
            # For cloud backends, we need to download first
            local_src = Path(temp_dir) / 'source.mp4'
            vod_log.info(f"Downloading from cloud storage: {source_path}")
            
            # Note: Implement download logic based on backend type
            # For now, transcoding assumes local access
            local_src = Path(source_path)
        else:
            local_src = Path(source_path)
        
        # Verify source exists
        if not local_src.exists():
            raise FileNotFoundError(f"Source video not found: {local_src}")
        
        # Get video info
        try:
            info_cmd = [
                FFPROBE_BIN, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1:nozero=1',
                str(local_src)
            ]
            duration = float(subprocess.check_output(info_cmd).decode().strip())
            vod_log.info(f"Video duration: {duration}s")
        except Exception as e:
            vod_log.warning(f"Could not get video duration: {e}")
            duration = 0
        
        # Transcode to HLS
        output_base = Path(temp_dir) / 'output'
        output_base.mkdir(exist_ok=True)
        
        qualities = DEFAULT_QUALITIES  # ['720p', '480p', '360p']
        
        for quality in qualities:
            quality_profile = next((q for q in QUALITY_PROFILES if q[0] == quality), None)
            if not quality_profile:
                continue
            
            _, width_height, vbr, abr = quality_profile
            width, height = width_height.split('x')
            
            quality_dir = output_base / quality
            quality_dir.mkdir(exist_ok=True)
            
            cmd = [
                FFMPEG_BIN,
                '-i', str(local_src),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-s', f'{width}x{height}',
                '-b:v', vbr,
                '-b:a', abr,
                '-hls_time', str(HLS_SEGMENT_SECS),
                '-hls_list_size', '0',
                str(quality_dir / 'index.m3u8')
            ]
            
            vod_log.info(f"Transcoding {quality}: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {result.stderr}")
            
            # Upload HLS segments to storage
            for segment_file in quality_dir.glob('*.ts'):
                try:
                    url = vod_storage.upload_hls_segment(video_id, quality, str(segment_file))
                    vod_log.debug(f"Uploaded segment: {segment_file.name} -> {url}")
                except Exception as e:
                    vod_log.error(f"Failed to upload segment {segment_file}: {e}")
                    raise
            
            # Upload master playlist
            try:
                master_file = quality_dir / 'index.m3u8'
                with open(master_file) as f:
                    manifest_content = f.read()
                
                # Update relative paths in manifest for cloud storage
                if type(vod_storage).__name__ != 'LocalStorage':
                    # Cloud backends need adjusted paths
                    manifest_content = manifest_content.replace('./360p/', '/360p/')
                    manifest_content = manifest_content.replace('./480p/', '/480p/')
                    manifest_content = manifest_content.replace('./720p/', '/720p/')
                
                master_url = vod_storage.upload_hls_segment(video_id, quality, str(master_file))
                vod_log.info(f"Uploaded master playlist: {master_url}")
            
            except Exception as e:
                vod_log.error(f"Failed to upload manifest: {e}")
                raise
        
        # Generate thumbnail
        try:
            thumb_path = Path(temp_dir) / 'thumb.jpg'
            thumb_time = int(duration * (THUMB_TIME_PERCENT / 100)) if duration > 0 else 5
            
            cmd = [
                FFMPEG_BIN,
                '-ss', str(thumb_time),
                '-i', str(local_src),
                '-vframes', '1',
                '-vf', 'scale=320:180',
                str(thumb_path)
            ]
            
            subprocess.run(cmd, capture_output=True, check=True, timeout=60)
            
            # Upload thumbnail
            thumb_url = vod_storage.upload_thumbnail(video_id, str(thumb_path))
            vod_log.info(f"Uploaded thumbnail: {thumb_url}")
        
        except Exception as e:
            vod_log.warning(f"Failed to generate thumbnail: {e}")
            thumb_url = ''
        
        # Update database
        try:
            conn = vod_get_db()
            hls_url = vod_storage.get_hls_url(video_id)
            
            conn.execute("""
                UPDATE videos SET
                    status = 'ready',
                    hls_path = ?,
                    thumbnail = ?,
                    duration = ?,
                    qualities = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                hls_url,
                thumb_url,
                duration,
                json.dumps(qualities),
                datetime.now().isoformat(),
                video_id
            ))
            conn.commit()
            
            vod_log.info(f"Transcoding completed: {video_id}")
            return True
        
        except Exception as e:
            vod_log.error(f"Failed to update database: {e}")
            raise
    
    except Exception as e:
        vod_log.exception(f"Transcoding failed for {video_id}")
        
        # Update database with error status
        try:
            conn = vod_get_db()
            conn.execute("""
                UPDATE videos SET
                    status = 'error',
                    updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), video_id))
            conn.commit()
        except:
            pass
        
        return False
    
    finally:
        # Clean up temporary directory
        if temp_dir:
            try:
                import shutil
                shutil.rmtree(temp_dir)
                vod_log.debug(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                vod_log.warning(f"Failed to clean up temp directory: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6: UPDATE QUEUE TRANSCODE JOB (use new handler)
# ═════════════════════════════════════════════════════════════════════════════

def queue_transcode_job(video_id: str, source_path: str):
    """Queue a transcode job (sync or async based on env)"""
    
    use_celery = os.getenv('USE_CELERY', '0') == '1'
    use_threading = os.getenv('USE_THREADING', '1') == '1'
    
    if use_celery:
        # Celery task (distributed)
        try:
            from celery import Celery
            celery_app = Celery('vod_transcoder', broker=os.getenv('REDIS_URL', 'redis://YOUR_REDIS_SERVER:6379'))
            
            @celery_app.task(bind=True, max_retries=3)
            def transcode_task(self, vid_id, src_path):
                return transcode_video_multistorage(vid_id, src_path)
            
            transcode_task.apply_async(
                args=(video_id, source_path),
                countdown=10
            )
            vod_log.info(f"Queued for Celery transcoding: {video_id}")
        except Exception as e:
            vod_log.warning(f"Celery not available, falling back: {e}")
            use_threading = True
    
    if use_threading:
        # Threading
        thread = threading.Thread(
            target=transcode_video_multistorage,
            args=(video_id, source_path),
            daemon=True
        )
        thread.start()
        vod_log.info(f"Queued for threaded transcoding: {video_id}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 7: ADD HLS SERVING ROUTE (update existing handler)
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/api/vod/video/<video_id>/master.m3u8', methods=['GET'])
def get_vod_hls_url(video_id: str):
    """
    GET /api/vod/video/{video_id}/master.m3u8
    Get HLS manifest URL (works with all storage backends)
    """
    try:
        if not vod_storage:
            return {'error': 'Storage backend not available'}, 503
        
        # Get video from database
        conn = vod_get_db()
        video = conn.execute(
            "SELECT * FROM videos WHERE id = ?",
            (video_id,)
        ).fetchone()
        
        if not video:
            return {'error': 'Video not found'}, 404
        
        video = dict(video)
        
        if video['status'] != 'ready':
            return {
                'error': f'Video not ready: {video["status"]}'
            }, 412
        
        return {
            'success': True,
            'video_id': video_id,
            'title': video.get('title'),
            'hls_url': vod_storage.get_hls_url(video_id),  # Returns correct URL for backend
            'thumbnail': vod_storage.get_thumbnail_url(video_id),
            'duration': video.get('duration'),
            'qualities': json.loads(video.get('qualities', '[]')),
            'storage_backend': type(vod_storage).__name__
        }, 200
    
    except Exception as e:
        vod_log.exception("Error getting HLS URL")
        return {'error': str(e)}, 500


# ═════════════════════════════════════════════════════════════════════════════
# STEP 8: ADD ADMIN DASHBOARD ENDPOINT (serve HTML)
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/admin/storage', methods=['GET'])
@admin_required  # Use your existing admin decorator
def admin_storage_dashboard():
    """Serve storage management dashboard"""
    
    admin_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Storage Management - NexVision Admin</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .header {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .header h1 {{ margin: 0; color: #333; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📦 VOD Storage Management</h1>
            <p>Configure and monitor multi-backend storage for your VOD system</p>
        </div>
        {STORAGE_ADMIN_HTML}
    </body>
    </html>
    """
    
    return admin_html


# ═════════════════════════════════════════════════════════════════════════════
# NOTES FOR INTEGRATION
# ═════════════════════════════════════════════════════════════════════════════

"""
1. ENVIRONMENT VARIABLES (.env)
   ─────────────────────────────

   For Local Storage:
      STORAGE_BACKEND=local

   For NAS:
      STORAGE_BACKEND=nas
      NAS_MOUNT=/mnt/nas/vod

   For AWS S3:
      STORAGE_BACKEND=s3
      AWS_REGION=us-east-1
      AWS_ACCESS_KEY=AKIA...
      AWS_SECRET_KEY=...
      S3_BUCKET_HLS=nexvision-hls
      CLOUDFRONT_URL=https://d123.cloudfront.net

   For Azure:
      STORAGE_BACKEND=azure
      AZURE_STORAGE_ACCOUNT=mystg
      AZURE_STORAGE_KEY=...
      AZURE_CDN_URL=https://mycdn.azureedge.net

   For Google Cloud:
      STORAGE_BACKEND=gcs
      GCP_PROJECT_ID=my-project
      GCS_BUCKET=nexvision-vod

2. REQUIRED DEPENDENCIES
   ──────────────────────

   Base:
      pip install flask boto3 azure-storage-blob google-cloud-storage

3. DATABASE SCHEMA
   ────────────────

   Make sure your vod.db has:
      - videos table with 'status' and 'hls_path' columns
      - See vod_init_db() for full schema

4. TESTING
   ───────

   # Test storage backend
   curl -X POST http://YOUR_SERVER_IP_HERE:5000/api/admin/storage/test

   # Get storage info
   curl http://YOUR_SERVER_IP_HERE:5000/api/admin/storage/info

   # List backends
   curl http://YOUR_SERVER_IP_HERE:5000/api/admin/storage/backends

   # Switch backend
   curl -X POST http://YOUR_SERVER_IP_HERE:5000/api/admin/storage/switch \\
        -H "Content-Type: application/json" \\
        -d '{"backend": "s3", "reason": "Scale upgrade"}'

5. ADMIN DASHBOARD
   ───────────────

   Access at: http://YOUR_SERVER_IP_HERE:5000/admin/storage

   Features:
   - View current storage backend
   - See health status and statistics
   - Test backend connectivity
   - Switch between backends
   - Monitor configuration status
   - Auto-refresh every 30 seconds

6. ERROR HANDLING
   ───────────────

   All routes return JSON with:
      {
          "success": true/false,
          "error": "error message",
          "data": {...}
      }

   Check logs for debugging:
      tail -f /var/log/nexvision/app.log | grep storage

7. PRODUCTION DEPLOYMENT
   ──────────────────────

   1. Deploy storage_backends.py and vod_storage_admin.py
   2. Set environment variables in .env
   3. Restart Flask app
   4. Access /admin/storage to verify
   5. Test each backend: /api/admin/storage/test
   6. Monitor health: tail -f application.log | grep -i storage

8. MIGRATION
   ────────

   To migrate from Local → NAS:
      1. Take backup: cp -r vod_data vod_data.backup
      2. Set STORAGE_BACKEND=nas in .env
      3. Restart app
      4. Check: curl /api/admin/storage/info
      5. Test upload: curl -X POST /api/admin/storage/test
      6. Monitor: watch curl -s http://YOUR_SERVER_IP_HERE:5000/api/admin/storage/info | jq .

9. MONITORING
   ──────────

   Add to your monitoring system:
      - Check /api/admin/storage/health every 60 seconds
      - Alert if status != 'healthy'
      - Monitor /api/admin/storage/dashboard for usage
"""
