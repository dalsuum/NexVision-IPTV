"""
vod_server_service.py — VOD streaming server business logic.

During the initial blueprint extraction the VOD server functions still live
in main.py (because extracting ~2,000 lines of FFmpeg/HLS code in one pass
is risky for a live service).  Each function here delegates to the
corresponding handler already defined in main.py via a lazy import so that
main.py is not loaded at import time and circular imports are avoided.

Next step: move each function's implementation here and delete the delegation.
"""

from flask import request as _req


def _m():
    """Lazy import of the main module to avoid circular imports at load time."""
    from app import main as _main
    return _main


# HLS delivery ----------------------------------------------------------------

def serve_master(video_id):
    return _m().vod_serve_master(video_id)


def serve_playlist(video_id, quality):
    return _m().vod_serve_playlist(video_id, quality)


def serve_segment(video_id, quality, segment):
    return _m().vod_serve_segment(video_id, quality, segment)


def serve_thumbnail(filename):
    return _m().vod_serve_thumbnail(filename)


def serve_vod_upload(filename):
    return _m().vod_serve_upload(filename)


# Catalogue -------------------------------------------------------------------

def list_videos(**kwargs):
    return _m().vod_list_videos()


def get_video(vid):
    return _m().vod_get_video(vid)


def update_video(vid, d):
    return _m().vod_update_video(vid)


def delete_video(vid):
    return _m().vod_delete_video(vid)


# Ingest ----------------------------------------------------------------------

def upload_video(request):
    return _m().vod_upload_video()


def import_from_url(d):
    return _m().vod_import_from_url()


# Transcoding jobs ------------------------------------------------------------

def get_progress(vid):
    return _m().vod_get_progress(vid)


def progress_stream(vid):
    return _m().vod_progress_stream(vid)


def retranscode(vid, d):
    return _m().vod_retranscode(vid)


def regen_thumbnail(vid, d):
    return _m().vod_regen_thumbnail(vid)


def push_to_nexvision(vid):
    return _m().vod_push_nexvision(vid)


def list_jobs():
    return _m().vod_list_jobs()


def cancel_job(vid):
    return _m().vod_cancel_job(vid)


# Settings & auth -------------------------------------------------------------

def auth_token(d):
    return _m().vod_auth_token()


def get_settings():
    return _m().vod_get_settings()


def save_settings(d):
    return _m().vod_save_settings()


def analytics(**kwargs):
    return _m().vod_analytics()


def health():
    return _m().vod_health()


# Admin UI (HTML pages) -------------------------------------------------------

def render_dashboard():
    return _m().vod_dashboard()


def render_admin_hub():
    return _m().vod_admin_hub()


def render_admin_storage():
    return _m().vod_admin_storage()
