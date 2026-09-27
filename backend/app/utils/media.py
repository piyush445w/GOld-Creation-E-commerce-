# -*- coding: utf-8 -*-
# =============================================================================
# media.py — Upload validation & in-database media storage
# -----------------------------------------------------------------------------
# Validates and stores product images/videos (and banner media) directly in
# MySQL as BLOBs rather than on a filesystem/S3. Enforces an allow-list of
# extensions, MIME-type consistency with the declared media type, per-type size
# caps, non-empty files, and computes a SHA-256 checksum for dedup/integrity.
# The returned dict is what callers persist into the *_data/*_size/checksum
# columns added by migration e46b016fb138.
# =============================================================================
import os
import hashlib
import uuid
import mimetypes
from werkzeug.utils import secure_filename

# Allow-list of upload extensions; images and videos only.
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'avif', 'mp4', 'webm'}
MAX_IMAGE_SIZE = 50 * 1024 * 1024
MAX_VIDEO_SIZE = 250 * 1024 * 1024


# Cheap extension check against ALLOWED_EXTENSIONS.
def allowed_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# Generate a collision-resistant storage name that preserves the original extension.
def generate_safe_filename(original_filename):
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    if ext:
        return f"{uuid.uuid4().hex}.{ext}"
    return uuid.uuid4().hex


# SHA-256 digest of the raw bytes, used for integrity checks and dedup.
def _compute_checksum(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()


# Per-type size cap; anything not recognised as image/video defaults to the video cap.
def _get_max_size(mime_type):
    if mime_type and mime_type.startswith('image/'):
        return MAX_IMAGE_SIZE
    if mime_type and mime_type.startswith('video/'):
        return MAX_VIDEO_SIZE
    return MAX_VIDEO_SIZE


# Extension-only validation returning a (ok, error_message) pair.
def _validate_extension(filename):
    if not filename or '.' not in filename:
        return False, 'Filename has no extension.'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f'Extension ".{ext}" is not allowed.'
    return True, ''


# Full validation pipeline for an uploaded file; returns (payload_dict, error_str).
# The payload is ready to insert into the media BLOB columns; error is None on success.
def save_media_to_db(file_storage, media_type='image'):
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None, 'No file provided.'

    filename = file_storage.filename
    ext_ok, ext_err = _validate_extension(filename)
    if not ext_ok:
        return None, ext_err

    # Resolve the MIME type from the upload hint, falling back to guessing from the filename.
    mime_type = file_storage.content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # Ensure the declared media_type matches the actual file kind.
    if media_type == 'image' and not mime_type.startswith('image/'):
        return None, 'MIME type does not match an image.'
    if media_type == 'video' and not mime_type.startswith('video/'):
        return None, 'MIME type does not match a video.'

    max_size = _get_max_size(mime_type)

    # Measure the file without consuming it: seek to end, read the position, rewind.
    file_storage.seek(0, os.SEEK_END)
    file_length = file_storage.tell()
    file_storage.seek(0)

    if file_length > max_size:
        max_mb = max_size // (1024 * 1024)
        return None, f'{media_type.capitalize()} exceeds maximum size of {max_mb}MB.'
    if file_length == 0:
        return None, 'File is empty.'

    file_bytes = file_storage.read()
    checksum = _compute_checksum(file_bytes)

    return {
        'data': file_bytes,
        'mime_type': mime_type,
        'file_size': file_length,
        'original_filename': secure_filename(filename),
        'checksum': checksum,
    }, None
