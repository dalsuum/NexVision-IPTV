"""Serves the TV client shell — catch-all for / and /<path>."""
import os
from flask import send_from_directory, abort, request as flask_request
from ..config import TV_DIR


def serve(path: str, request_obj=None):
    req = request_obj or flask_request
    if path and (TV_DIR / path).exists():
        return send_from_directory(str(TV_DIR), path)
    # Return 404 for asset requests that don't exist — prevents returning HTML
    # for missing .js/.css files, which silently breaks the requesting page.
    if os.path.splitext(path)[1]:
        abort(404)
    return send_from_directory(str(TV_DIR), 'index.html')
