"""Normalize an uploaded product picture into a small image stored in PostgreSQL.

Browsers upload arbitrary camera files, so every upload is decoded, bounded,
downscaled and re-encoded here. Only the re-encoded bytes reach the database;
the original file is never stored.
"""
from base64 import b64decode
from binascii import Error as DecodeError
from io import BytesIO

from PIL import Image, UnidentifiedImageError

# Bounds for the accepted upload, the stored picture, and the decoded pixel count.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 1024
MAX_DECODED_PIXELS = 40_000_000
MEDIA_TYPE = 'image/webp'
QUALITY = 80


def compress_upload(contents: str) -> tuple[bytes, str]:
    """Turn a dcc.Upload data URI into (bytes, media type); raise ValueError otherwise."""
    if not isinstance(contents, str) or ',' not in contents:
        raise ValueError('Upload an image file.')
    header, _, payload = contents.partition(',')
    if not header.startswith('data:') or ';base64' not in header:
        raise ValueError('Upload an image file.')
    try:
        raw = b64decode(payload, validate=True)
    except (DecodeError, ValueError):
        raise ValueError('That file could not be read. Upload a PNG, JPEG or WebP image.') from None
    if not raw:
        raise ValueError('That file is empty.')
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(f'Images must be smaller than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')
    try:
        with Image.open(BytesIO(raw)) as picture:
            width, height = picture.size
            # Reject decompression bombs before any full-size decoding happens.
            if width * height > MAX_DECODED_PIXELS:
                raise ValueError('That image has too many pixels.')
            # Palette and CMYK images have no direct WebP equivalent.
            transparent = picture.mode in ('RGBA', 'LA') or 'transparency' in picture.info
            picture = picture.convert('RGBA' if transparent else 'RGB')
            picture.thumbnail((MAX_PIXELS, MAX_PIXELS))
            stored = BytesIO()
            picture.save(stored, format='WEBP', quality=QUALITY, method=6)
    except (UnidentifiedImageError, OSError):
        raise ValueError('That file is not a readable image. Use PNG, JPEG or WebP.') from None
    return stored.getvalue(), MEDIA_TYPE
