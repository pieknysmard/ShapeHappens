"""Palette segmentation; white and transparent pixels never become fill."""
import base64
import io

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


class InputError(ValueError):
    def __init__(self, message, preview=None):
        super().__init__(message)
        self.preview = preview


def png_url(array):
    stream = io.BytesIO()
    Image.fromarray(array.astype('uint8')).save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def segment(data, mode, tolerance):
    try:
        source = Image.open(io.BytesIO(data))
        if source.format != 'PNG':
            raise InputError('Please upload a PNG image.')
        if max(source.size) > 2048 or min(source.size) < 8:
            raise InputError('Image dimensions must be between 8 and 2048 pixels. Resize explicitly before uploading.')
        rgba = np.array(source.convert('RGBA'))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InputError('Unable to read this PNG.') from exc
    rgb = rgba[:, :, :3].astype(float)
    visible = rgba[:, :, 3] >= 128
    palette = np.array([[255, 0, 0], [0, 0, 255], [0, 255, 0], [255, 255, 255]] if mode == 'cookie' else [[0, 0, 0], [255, 255, 255]])
    # Distance to each palette colour's antialias blend with white. White is
    # independently reserved first, so it can never classify as blue fill.
    if mode == 'cookie':
        distances = []
        for color in palette[:-1]:
            direction = color - 255.
            amount = np.clip(np.sum((rgb - 255) * direction, axis=2) / np.dot(direction, direction), 0, 1)
            projection = 255 + amount[:, :, None] * direction
            distances.append(np.max(np.abs(rgb - projection), axis=2))
        distance = np.stack(distances, axis=2)
        labels = np.argmin(distance, axis=2)
        invalid = (np.min(distance, axis=2) > tolerance) & visible
        # Antialiasing also blends adjacent ink colours. Accept an intermediate
        # only where BOTH endpoint colours occur nearby; an isolated purple
        # mark must still be reported as invalid.
        raw_dist = np.max(np.abs(rgb[:, :, None, :] - palette[None, None, :, :]), axis=3)
        nearby = [cv2.dilate((raw_dist[:, :, i] <= tolerance).astype('uint8'), np.ones((7, 7), np.uint8)) > 0 for i in range(4)]
        for a in range(3):
            for b in range(a + 1, 3):
                delta = palette[b] - palette[a]
                t = np.clip(np.sum((rgb - palette[a]) * delta, axis=2) / np.dot(delta, delta), 0, 1)
                residual = np.max(np.abs(rgb - (palette[a] + t[:, :, None] * delta)), axis=2)
                blend = invalid & (residual <= tolerance) & nearby[a] & nearby[b]
                labels[blend] = np.where(t[blend] <= .5, a, b)
                invalid[blend] = False
        white = np.max(np.abs(rgb - 255), axis=2) <= tolerance
        labels[white | ~visible] = 3
        invalid[white] = False
    else:
        gray = rgb.mean(axis=2)
        invalid = (np.ptp(rgb, axis=2) > tolerance) & visible
        gray[~visible] = 255
        interpreted = np.repeat(np.rint(gray)[:, :, None], 3, axis=2).astype('uint8')
        interpreted[invalid] = [255, 0, 255]
        preview = png_url(interpreted)
        if invalid.any():
            raise InputError(f'{int(invalid.sum())} non-grayscale pixels (highlighted magenta). Use grayscale artwork or adjust colour tolerance.', preview)
        # Preserve continuous pixel intensity, rather than thresholding at gray.
        # Index 0 is the fractional radial depth; binary artwork stays 0 or 1.
        depth_fraction = (255 - gray) / 255
        return [depth_fraction, 1 - depth_fraction], preview
    interpreted = palette[labels].astype('uint8')
    interpreted[invalid] = [255, 0, 255]
    preview = png_url(interpreted)
    if invalid.any():
        raise InputError(f'{int(invalid.sum())} invalid colour pixels (highlighted magenta). Use the mode palette or adjust tolerance.', preview)
    masks = [(labels == i).astype('uint8') for i in range(len(palette))]
    return masks, preview


def contours(mask):
    """Pixel-centre contours, including holes; no area-based feature deletion."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    # Trace on a 2x grid so a one-pixel-wide spike has area, instead of an
    # invalid line dangling from a pixel-centre polygon. No ink is discarded.
    enlarged = cv2.resize(mask, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    found, hierarchy = cv2.findContours(enlarged, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    found = [(c.astype(float) - 0.5) / 2 for c in found]
    if hierarchy is None:
        return Polygon()
    shapes = []
    for i, contour in enumerate(found):
        if hierarchy[0, i, 3] != -1:
            continue
        if len(contour) < 3:
            raise InputError('A feature is only one pixel wide. Increase image resolution or thicken the feature.')
        holes = []
        child = hierarchy[0, i, 2]
        while child != -1:
            if len(found[child]) >= 3:
                holes.append(found[child][:, 0, :])
            child = hierarchy[0, child, 0]
        polygon = Polygon(contour[:, 0, :], holes)
        if not polygon.is_valid or polygon.area <= 0:
            raise InputError('A contour self-touches or has zero area. Separate diagonal-only pixel contacts or increase image resolution.')
        shapes.append(polygon)
    return unary_union(shapes)
