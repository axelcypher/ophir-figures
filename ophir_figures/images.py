"""Figure pictures: downloaded from the link a figure names, or uploaded; thumbnails made from them.

Every picture is stored once under the SHA-256 of its bytes (figures.image_key = "<hash>.<ext>")
in IMAGE_DIR; thumbnails are WebP files in THUMB_DIR made on first use. A figure with an image_url
but no image_key yet has its picture fetched on first view; a failed fetch is not tried again for
MISS_RETRY_SECONDS, so a grid of figures with dead links does not hang on every visit.

Which pictures are taken is up to Pillow: what it opens as one of FORMATS. AVIF needs a Pillow
built with libavif; the wheels of the pinned version have it.
"""

import hashlib
import io
import os
import time

from flask import Response, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import IMAGE_DIR, THUMB_DIR, now_iso
from .fetch import FetchError, fetch
from .web import app, db, login_required

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
THUMB_WIDTH = 480
MISS_RETRY_SECONDS = 600
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp"), "GIF": ("gif", "image/gif"),
           "AVIF": ("avif", "image/avif")}
FORMAT_NAMES = "JPEG, PNG, WebP, GIF oder AVIF"
MIME_OF_EXTENSION = {extension: mime for extension, mime in FORMATS.values()}
_misses = {}

# A figure without a picture: a small silhouette in a grey that reads on the light and the dark
# appearance, on a transparent ground (the tile's own surface shows through), in the middle of the
# frame, so cropping it into a wider one (a group's mosaic) keeps it whole.
PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400" viewBox="0 0 300 400">
<g fill="none" stroke="#8c8679" stroke-opacity=".5" stroke-width="11" stroke-linecap="round" stroke-linejoin="round" transform="translate(150 205) scale(.6) translate(-150 -205)">
<circle cx="150" cy="118" r="38"/><path d="M96 300c4-62 22-110 54-110s50 48 54 110"/><path d="M82 330h136"/></g></svg>"""


class ImageError(Exception):
    pass


def store_image(payload):
    """Checks that the bytes are a picture and stores them; returns the image key."""
    if len(payload) > MAX_IMAGE_BYTES:
        raise ImageError("Das Bild ist größer als 15 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
        raise ImageError(f"Die Datei ist kein lesbares Bild ({FORMAT_NAMES}).")
    if image_format not in FORMATS:
        raise ImageError(f"Bilder bitte als {FORMAT_NAMES}.")
    key = f"{hashlib.sha256(payload).hexdigest()}.{FORMATS[image_format][0]}"
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = IMAGE_DIR / key
    if not target.exists():
        temporary = target.with_name(f"{key}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    return key


def download_image(url):
    """Fetches a picture from a link and stores it; returns the image key. Raises ImageError."""
    try:
        _, _, payload = fetch(url, MAX_IMAGE_BYTES, accept="image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8")
    except FetchError as error:
        raise ImageError(str(error))
    return store_image(payload)


def ensure_image(connection, figure):
    """The figure's image key, fetching its image_url first if that has not happened yet."""
    if figure["image_key"] and (IMAGE_DIR / figure["image_key"]).exists():
        return figure["image_key"]
    url = figure["image_url"]
    if not url:
        return None
    if time.time() - _misses.get(url, 0) < MISS_RETRY_SECONDS:
        return None
    try:
        key = download_image(url)
    except ImageError:
        _misses[url] = time.time()
        return None
    connection.execute("UPDATE figures SET image_key=? WHERE id=?", (key, figure["id"]))
    connection.commit()
    return key


def thumbnail_path(key):
    target = THUMB_DIR / f"{key.rsplit('.', 1)[0]}-{THUMB_WIDTH}.webp"
    if target.exists():
        return target
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(IMAGE_DIR / key) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("LA", "P") else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=82, method=4)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_bytes(buffer.getvalue())
    os.replace(temporary, target)
    return target


def placeholder():
    response = Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")
    response.cache_control.max_age = 300
    return response


def serve_figure_image(figure_id, size):
    figure = db().execute("SELECT id,image_key,image_url FROM figures WHERE id=?", (figure_id,)).fetchone()
    if not figure:
        return Response(status=404)
    key = ensure_image(db(), figure)
    if not key:
        return placeholder()
    try:
        path = thumbnail_path(key) if size == "thumb" else IMAGE_DIR / key
    except (OSError, Image.DecompressionBombError):
        return placeholder()
    mimetype = "image/webp" if size == "thumb" else MIME_OF_EXTENSION.get(key.rsplit(".", 1)[-1], "application/octet-stream")
    response = send_file(path, mimetype=mimetype, conditional=True, etag=True, max_age=0)
    # The URL carries the key (?v=), so a changed picture is a new URL: kept for a year.
    if request.args.get("v") == key[:12]:
        response.cache_control.public = True
        response.cache_control.max_age = 31_536_000
        response.cache_control.immutable = True
    return response


@app.get("/images/figures/<int:figure_id>")
@login_required
def figure_image(figure_id):
    return serve_figure_image(figure_id, "full")


@app.get("/images/figures/<int:figure_id>/thumb")
@login_required
def figure_thumbnail(figure_id):
    return serve_figure_image(figure_id, "thumb")


@app.post("/api/figures/<int:figure_id>/image")
@login_required
def upload_figure_image(figure_id):
    if not db().execute("SELECT 1 FROM figures WHERE id=?", (figure_id,)).fetchone():
        return jsonify({"error": "Figur nicht gefunden."}), 404
    file = request.files.get("file")
    try:
        if file and file.filename:
            key = store_image(file.read(MAX_IMAGE_BYTES + 1))
        else:
            url = str((request.get_json(silent=True) or {}).get("url") or "").strip()
            if not url:
                return jsonify({"error": "Kein Bild übermittelt."}), 400
            key = download_image(url)
            db().execute("UPDATE figures SET image_url=? WHERE id=?", (url, figure_id))
    except ImageError as error:
        return jsonify({"error": str(error)}), 400
    db().execute("UPDATE figures SET image_key=?, updated_at=? WHERE id=?", (key, now_iso(), figure_id))
    db().commit()
    return jsonify({"image_key": key, "image_version": key[:12]})


@app.delete("/api/figures/<int:figure_id>/image")
@login_required
def remove_figure_image(figure_id):
    if not db().execute("UPDATE figures SET image_key='', image_url='', updated_at=? WHERE id=?", (now_iso(), figure_id)).rowcount:
        return jsonify({"error": "Figur nicht gefunden."}), 404
    db().commit()
    return jsonify({"removed": True})
