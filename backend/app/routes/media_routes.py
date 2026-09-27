# -*- coding: utf-8 -*-
# =============================================================================
# media_routes.py — binary media delivery blueprint (mounted at the app root)
# -----------------------------------------------------------------------------
# Product images and videos are stored as BLOBs in MySQL rather than on a
# filesystem or object store (see app/utils/media.py and migration
# e46b016fb138). Because the bytes live in the database, this module is what
# actually streams them back to <img>/<video> tags in the storefront and admin
# templates.
#
# It also implements HTTP Range support, which is what lets a browser seek
# inside a stored video instead of forcing a full download before playback.
# =============================================================================

import re
from flask import Blueprint, Response, abort, request
from app import db
from app.models.product_media import ProductMedia
from app.models.category_media import CategoryMedia
from app.models.banner import Banner
from app.models.site_asset import SiteAsset
from app.models.page_media import PageMedia

media_bp = Blueprint('media', __name__)


# ---- Request helpers ---------------------------------------------------------

def _parse_range_header(range_header, file_size):
    """Parse a single-range `Range: bytes=start-end` header.

    Returns an inclusive (start, end) tuple, or None when the header is
    malformed, unsatisfiable, or falls outside the file - in which case the
    caller should simply serve the whole asset instead of failing the request.
    """
    # Only the single-range form is supported; multi-range is intentionally
    # rejected and treated as "no range".
    m = re.match(r'bytes=(\d*)-(\d*)', range_header)
    if not m:
        return None
    start_str, end_str = m.group(1), m.group(2)
    # An omitted start means "from the beginning"; an omitted end means
    # "through the last byte" (e.g. `bytes=1024-`).
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    # Reject out-of-bounds and inverted ranges so the caller can fall back.
    if start >= file_size or end >= file_size or start > end:
        return None
    return start, end


# ---- Endpoints ---------------------------------------------------------------

# GET /media/product/<product_id>/<media_id> - public. Streams one full-size
# gallery asset. The product_id is part of the URL and checked against the
# row, so a media id cannot be used to pull an asset off a different product.
@media_bp.route('/media/product/<int:product_id>/<int:media_id>')
def serve_product_media(product_id, media_id):
    media = ProductMedia.query.filter_by(
        id=media_id,
        product_id=product_id,
        is_active=True
    ).first()

    # Missing row, or a row whose BLOB was never populated, is a 404.
    if not media or not media.media_data:
        abort(404)

    # Fall back to the actual BLOB length if file_size was not recorded at upload.
    file_size = media.file_size or len(media.media_data)
    mime_type = media.mime_type or 'application/octet-stream'
    # The upload-time SHA-256 doubles as a strong ETag, giving clients cheap
    # conditional revalidation and making content immutable under one URL.
    etag = media.checksum or ''

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Cache-Control': 'public, max-age=31536000',
        'ETag': etag,
        # Declares range support, which is what triggers the browser to seek.
        'Accept-Ranges': 'bytes',
    }

    range_header = request.headers.get('Range')
    if range_header:
        parsed = _parse_range_header(range_header, file_size)
        if parsed:
            start, end = parsed
            # Slice the BLOB in memory; the response is only the requested span.
            chunk = media.media_data[start:end + 1]
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            headers['Content-Length'] = str(len(chunk))
            return Response(chunk, status=206, headers=headers)

    # No range requested (or an unusable one): send the whole asset with 200.
    return Response(media.media_data, headers=headers)


# GET /media/thumbnail/<media_id> - public. Streams the smaller derivative used
# in product grids and admin lists, so listings never download full-resolution
# images or videos. No Range support: thumbnails are small and always complete.
@media_bp.route('/media/thumbnail/<media_id>')
def serve_thumbnail(media_id):
    media = ProductMedia.query.filter_by(id=media_id).first()

    # 404 when the row is gone or the thumbnail was never generated.
    if not media or not media.thumbnail_data:
        abort(404)

    mime_type = media.mime_type or 'image/jpeg'

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(len(media.thumbnail_data)),
        'Cache-Control': 'public, max-age=31536000',
    }

    return Response(media.thumbnail_data, headers=headers)

# GET /media/category/<category_id>/<media_id> - public. Streams one full-size
# gallery asset for a category. The category_id is part of the URL and checked
# against the row, so a media id cannot be used to pull an asset off a
# different category.
@media_bp.route('/media/category/<int:category_id>/<int:media_id>')
def serve_category_media(category_id, media_id):
    media = CategoryMedia.query.filter_by(
        id=media_id,
        category_id=category_id,
        is_active=True
    ).first()
    if not media or not media.media_data:
        abort(404)
    file_size = media.file_size or len(media.media_data)
    mime_type = media.mime_type or 'application/octet-stream'
    etag = media.checksum or ''
    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Cache-Control': 'public, max-age=31536000',
        'ETag': etag,
        'Accept-Ranges': 'bytes',
    }
    range_header = request.headers.get('Range')
    if range_header:
        m = re.match(r'bytes=(\d*)-(\d*)', range_header)
        if m:
            start = int(m.group(1)) if m.group(1) else 0
            end = int(m.group(2)) if m.group(2) else file_size - 1
            if start < file_size and end < file_size and start <= end:
                chunk = media.media_data[start:end + 1]
                headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                headers['Content-Length'] = str(len(chunk))
                return Response(chunk, status=206, headers=headers)
    return Response(media.media_data, headers=headers)


# GET /media/banner/<banner_id> - public. Streams the inline BLOB for a banner.
# Supports HTTP Range requests so browsers can seek/display incrementally.
@media_bp.route('/media/banner/<int:banner_id>')
def serve_banner(banner_id):
    banner = Banner.query.get(banner_id)

    if not banner or not banner.banner_data:
        abort(404)

    file_size = banner.file_size or len(banner.banner_data)
    mime_type = banner.mime_type or 'application/octet-stream'
    etag = banner.checksum or ''

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Cache-Control': 'public, max-age=31536000',
        'ETag': etag,
        'Accept-Ranges': 'bytes',
    }

    range_header = request.headers.get('Range')
    if range_header:
        parsed = _parse_range_header(range_header, file_size)
        if parsed:
            start, end = parsed
            chunk = banner.banner_data[start:end + 1]
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            headers['Content-Length'] = str(len(chunk))
            return Response(chunk, status=206, headers=headers)

    return Response(banner.banner_data, headers=headers)


# GET /media/page/<page_id>/<media_id> - public. Streams one full-size
# gallery asset for a CMS page. The page_id is part of the URL and checked
# against the row, so a media id cannot be used to pull an asset off a
# different page.
@media_bp.route('/media/page/<int:page_id>/<int:media_id>')
def serve_page_media(page_id, media_id):
    media = PageMedia.query.filter_by(
        id=media_id,
        page_id=page_id,
        is_active=True
    ).first()
    if not media or not media.media_data:
        abort(404)

    file_size = media.file_size or len(media.media_data)
    mime_type = media.mime_type or 'application/octet-stream'
    etag = media.checksum or ''

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(file_size),
        'Cache-Control': 'public, max-age=31536000',
        'ETag': etag,
        'Accept-Ranges': 'bytes',
    }

    range_header = request.headers.get('Range')
    if range_header:
        parsed = _parse_range_header(range_header, file_size)
        if parsed:
            start, end = parsed
            chunk = media.media_data[start:end + 1]
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            headers['Content-Length'] = str(len(chunk))
            return Response(chunk, status=206, headers=headers)

    return Response(media.media_data, headers=headers)


# GET /media/site/logo - public. Streams the site-wide logo BLOB stored as a
# SiteAsset with asset_key == 'logo'. No Range support: the logo is small and
# always served in full.
@media_bp.route('/media/site/logo')
def serve_site_logo():
    asset = SiteAsset.query.filter_by(asset_key='logo').first()

    if not asset or not asset.data:
        abort(404)

    mime_type = asset.mime_type or 'image/png'

    headers = {
        'Content-Type': mime_type,
        'Content-Length': str(len(asset.data)),
        'Cache-Control': 'public, max-age=31536000',
    }

    return Response(asset.data, headers=headers)
