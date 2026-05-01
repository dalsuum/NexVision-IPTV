"""VOD streaming server routes — HLS delivery, transcoding jobs, VOD admin UI."""
from flask import Blueprint, request, Response
from ..decorators import admin_required, require_api_key
from ..services import vod_server_service

vod_server_bp = Blueprint('vod_server', __name__, url_prefix='/vod')


# ── HLS delivery (no auth — Cast / ExoPlayer must reach these) ────────────────

@vod_server_bp.route('/hls/<video_id>/master.m3u8')
def serve_master(video_id):
    return vod_server_service.serve_master(video_id)


@vod_server_bp.route('/hls/<video_id>/<quality>/index.m3u8')
def serve_playlist(video_id, quality):
    return vod_server_service.serve_playlist(video_id, quality)


@vod_server_bp.route('/hls/<video_id>/<quality>/<segment>')
def serve_segment(video_id, quality, segment):
    return vod_server_service.serve_segment(video_id, quality, segment)


@vod_server_bp.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    return vod_server_service.serve_thumbnail(filename)


@vod_server_bp.route('/uploads/<filename>')
def serve_vod_upload(filename):
    return vod_server_service.serve_vod_upload(filename)


# ── Video catalogue API ────────────────────────────────────────────────────────

@vod_server_bp.route('/api/videos', methods=['GET'])
def list_videos():
    return vod_server_service.list_videos(
        search   = request.args.get('search', '').strip(),
        status   = request.args.get('status'),
        category = request.args.get('category'),
        limit    = request.args.get('limit', 50),
        offset   = request.args.get('offset', 0),
    )


@vod_server_bp.route('/api/videos/<vid>', methods=['GET'])
def get_video(vid):
    return vod_server_service.get_video(vid)


@vod_server_bp.route('/api/videos/<vid>', methods=['PUT'])
@require_api_key
def update_video(vid):
    return vod_server_service.update_video(vid, request.json or {})


@vod_server_bp.route('/api/videos/<vid>', methods=['DELETE'])
@require_api_key
def delete_video(vid):
    return vod_server_service.delete_video(vid)


# ── Ingest ────────────────────────────────────────────────────────────────────

@vod_server_bp.route('/api/upload', methods=['POST'])
@require_api_key
def upload_video():
    return vod_server_service.upload_video(request)


@vod_server_bp.route('/api/import', methods=['POST'])
@require_api_key
def import_from_url():
    return vod_server_service.import_from_url(request.json or {})


# ── Transcoding jobs ──────────────────────────────────────────────────────────

@vod_server_bp.route('/api/videos/<vid>/progress', methods=['GET'])
def get_progress(vid):
    return vod_server_service.get_progress(vid)


@vod_server_bp.route('/api/videos/<vid>/progress/stream', methods=['GET'])
def progress_stream(vid):
    return vod_server_service.progress_stream(vid)


@vod_server_bp.route('/api/videos/<vid>/retranscode', methods=['POST'])
@require_api_key
def retranscode(vid):
    return vod_server_service.retranscode(vid, request.json or {})


@vod_server_bp.route('/api/videos/<vid>/thumbnail', methods=['POST'])
@require_api_key
def regen_thumbnail(vid):
    return vod_server_service.regen_thumbnail(vid, request.json or {})


@vod_server_bp.route('/api/videos/<vid>/push-nexvision', methods=['POST'])
@require_api_key
def push_nexvision(vid):
    return vod_server_service.push_to_nexvision(vid)


@vod_server_bp.route('/api/jobs', methods=['GET'])
def list_jobs():
    return vod_server_service.list_jobs()


@vod_server_bp.route('/api/jobs/<vid>/cancel', methods=['POST'])
@require_api_key
def cancel_job(vid):
    return vod_server_service.cancel_job(vid)


# ── Settings & auth ───────────────────────────────────────────────────────────

@vod_server_bp.route('/api/auth/token', methods=['POST'])
def vod_auth_token():
    return vod_server_service.auth_token(request.json or {})


@vod_server_bp.route('/api/settings', methods=['GET'])
def vod_get_settings():
    return vod_server_service.get_settings()


@vod_server_bp.route('/api/settings', methods=['POST'])
@require_api_key
def vod_save_settings():
    return vod_server_service.save_settings(request.json or {})


@vod_server_bp.route('/api/analytics', methods=['GET'])
def vod_analytics():
    return vod_server_service.analytics(
        days = request.args.get('days', 7),
    )


@vod_server_bp.route('/api/health', methods=['GET'])
def vod_health():
    return vod_server_service.health()


# ── VOD admin UI (HTML) ───────────────────────────────────────────────────────

@vod_server_bp.route('/')
@vod_server_bp.route('')
def vod_dashboard():
    return vod_server_service.render_dashboard()


@vod_server_bp.route('/admin', methods=['GET'])
def vod_admin_hub():
    return vod_server_service.render_admin_hub()


@vod_server_bp.route('/admin/storage', methods=['GET'])
def vod_admin_storage():
    return vod_server_service.render_admin_storage()
