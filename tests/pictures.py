"""Pictures for the tests: one made from its pixels, and a JPEG file read
back to its pixels, both through Pillow."""
import io

from PIL import Image


def rgba_image(width: int, height: int, pixels) -> Image.Image:
    """Returns an RGBA image `width` by `height` of `pixels`, (red, green,
    blue, alpha) tuples, row by row from the top-left corner."""
    return Image.frombytes("RGBA", (width, height), bytes(value for pixel in pixels
                                                          for value in pixel))


def read_jpeg(data: bytes) -> tuple:
    """Returns (width, height, RGB bytes, row by row) of a JPEG file."""
    with Image.open(io.BytesIO(data)) as picture:
        rgb = picture.convert("RGB")
    return rgb.width, rgb.height, rgb.tobytes()
