"""Tests for media upload utilities: file extension validation, safe filename generation, and DB persistence.

Protects the store's product image/video upload pipeline against invalid files and unsafe names.
"""
from app.utils.media import allowed_file, generate_safe_filename, save_media_to_db
from werkzeug.datastructures import FileStorage
from io import BytesIO


# Test class: verifies allowed_file() accepts only whitelisted image/video extensions.
# Prevents malicious uploads (scripts, archives) and enforces web-safe media types.
class TestAllowedFile:
    # Accepted image extensions: jpg, jpeg, png, webp (all web-browser compatible).
    # Product photos must use these formats for reliable display across devices.
    def test_valid_image_extensions(self):
        assert allowed_file('photo.jpg') is True
        assert allowed_file('photo.jpeg') is True
        assert allowed_file('photo.png') is True
        assert allowed_file('photo.webp') is True

    # Accepted video extensions: mp4, webm (HTML5 video standard formats).
    # Product demo videos must use these for browser playback without plugins.
    def test_valid_video_extensions(self):
        assert allowed_file('video.mp4') is True
        assert allowed_file('video.webm') is True

    # Rejects non-media extensions (pdf, zip) to block document/executable uploads.
    # Security: prevents attackers from uploading harmful file types.
    def test_invalid_extension(self):
        assert allowed_file('document.pdf') is False
        assert allowed_file('archive.zip') is False

    # Rejects filenames without extension, empty string, and None.
    # Edge-case hardening: ensures malformed uploads are caught early.
    def test_no_extension(self):
        assert allowed_file('noextension') is False
        assert allowed_file('') is False
        assert allowed_file(None) is False


# Test class: verifies generate_safe_filename() produces collision-resistant names.
# Uses 32-char random hex + lowercase extension to avoid overwrites and path traversal.
class TestGenerateSafeFilename:
    # Output preserves extension (lowercased) and prepends 32-char random prefix.
    # Ensures unique filenames for concurrent uploads of same original name.
    def test_preserves_extension(self):
        filename = generate_safe_filename('test.PNG')
        assert filename.endswith('.png')
        parts = filename.split('.')
        assert len(parts) == 2
        assert len(parts[0]) == 32

    # No extension input -> 32-char random name with no dot.
    # Handles edge case where uploaded file lacks extension.
    def test_no_extension(self):
        filename = generate_safe_filename('noextension')
        assert '.' not in filename
        assert len(filename) == 32


# Test class: verifies save_media_to_db() validates, saves, and returns Media record or error.
# Covers the full upload flow: extension check, empty file check, MIME type verification.
class TestSaveMediaToDb:
    # None file -> returns (None, 'No file provided.').
    # Guards against missing file in multipart request.
    def test_no_file(self):
        result, error = save_media_to_db(None)
        assert result is None
        assert error == 'No file provided.'

    # Invalid extension (.txt) -> returns (None, error mentioning 'Extension').
    # Blocks non-media files before any disk/DB write.
    def test_invalid_extension(self):
        file = FileStorage(stream=BytesIO(b'hello'), filename='test.txt')
        result, error = save_media_to_db(file)
        assert result is None
        assert 'Extension' in error

    # Empty file (0 bytes) -> returns (None, 'File is empty.').
    # Prevents zero-byte placeholder files from cluttering storage.
    def test_empty_file(self):
        file = FileStorage(stream=BytesIO(b''), filename='test.png', content_type='image/png')
        result, error = save_media_to_db(file)
        assert result is None
        assert error == 'File is empty.'

    # Mismatched MIME (text/plain for .png) -> returns (None, 'MIME type does not match').
    # Defense-in-depth: validates content-type matches extension for media_type='image'.
    def test_wrong_mime_type(self):
        file = FileStorage(stream=BytesIO(b'hello'), filename='test.png', content_type='text/plain')
        result, error = save_media_to_db(file, media_type='image')
        assert result is None
        assert 'MIME type does not match' in error
