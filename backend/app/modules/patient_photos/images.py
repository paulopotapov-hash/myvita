"""Checking and normalising an uploaded profile photo, before anything is stored.

- JPEG or PNG only, at most 5 MB, judged by the content: the file signature, then the
  image decoder itself (a renamed or corrupt file is refused), never the name or the
  declared type.
- Decompression bombs are refused (pixel limit, and Pillow's warning treated as an error).
- At least 200x200 pixels, and in colour ("A foto tem de ser a cores").
- The camera's orientation is applied, then the photo is cropped to a centred square,
  resized to 512x512 and re-encoded as a fresh JPEG: no EXIF (GPS location, device,
  dates), ICC, XMP or comment survives, because nothing of the original file is copied.

Error messages are for the patient and never echo anything from the file.
"""

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MIN_SIDE = 200
OUTPUT_SIDE = 512
MAX_PIXELS = 40_000_000  # far above any phone camera, far below a decompression bomb
# Average spread between a pixel's colour channels below which the photo is black and white.
MIN_COLOUR_SPREAD = 4.0
_SIGNATURES = {"JPEG": (b"\xff\xd8\xff",), "PNG": (b"\x89PNG\r\n\x1a\n",)}

NOT_AN_IMAGE = "Envia uma fotografia em JPEG ou PNG."
TOO_LARGE = "A foto não pode ter mais de 5 MB."
TOO_SMALL = "A foto tem de ter pelo menos 200 × 200 píxeis."
NOT_IN_COLOUR = "A foto tem de ser a cores."


class PhotoRejected(ValueError):
    """The upload is not an acceptable photo; the message is shown to the patient."""


def _is_grayscale(image: Image.Image) -> bool:
    """Black and white: every pixel's colour channels are (almost) equal."""
    pixels: list[tuple[int, int, int]] = list(image.convert("RGB").resize((64, 64)).get_flattened_data())  # type: ignore[arg-type]
    average = sum(max(pixel) - min(pixel) for pixel in pixels) / len(pixels)
    return average < MIN_COLOUR_SPREAD


def normalise(data: bytes) -> bytes:
    """The stored 512x512 JPEG for this upload, or PhotoRejected."""
    if len(data) > MAX_BYTES:
        raise PhotoRejected(TOO_LARGE)
    if not any(data.startswith(signature) for signatures in _SIGNATURES.values() for signature in signatures):
        raise PhotoRejected(NOT_AN_IMAGE)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        previous = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        try:
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format not in _SIGNATURES:
                    raise PhotoRejected(NOT_AN_IMAGE)
                probe.verify()  # structural check; the image cannot be used afterwards
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
        except PhotoRejected:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError, ValueError):
            raise PhotoRejected(NOT_AN_IMAGE) from None
        finally:
            Image.MAX_IMAGE_PIXELS = previous

    if min(image.size) < MIN_SIDE:
        raise PhotoRejected(TOO_SMALL)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    if _is_grayscale(image):
        raise PhotoRejected(NOT_IN_COLOUR)

    square = ImageOps.fit(image.convert("RGB"), (OUTPUT_SIDE, OUTPUT_SIDE), method=Image.Resampling.LANCZOS)
    out = io.BytesIO()
    # A new image: Pillow writes no EXIF, ICC or comment unless asked to.
    square.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()
