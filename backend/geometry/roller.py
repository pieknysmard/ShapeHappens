"""Periodic radial height field. Transitions span one grid cell, never texture-only."""
import math
import cv2
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, map_coordinates
from ..imaging.segment import InputError


SPACING = {'draft': 0.4, 'standard': 0.12, 'fine': 0.08}
MAX_SURFACE_SAMPLES = 2_200_000


def sample_relief(relief, n, rows, circumference, length, smoothing):
    """Filter in physical units, then bilinearly sample a periodic depth map.

    Unlike nearest-pixel sampling this neither duplicates raster steps during
    upsampling nor aliases unsampled pixels when reducing source resolution.
    Horizontal filtering wraps; vertical filtering clamps at the end caps.
    """
    h, w = relief.shape
    sigma_x = math.hypot(smoothing * w / circumference, max(w / n - 1, 0) / 2)
    sigma_y = math.hypot(smoothing * (h - 1) / length, max((h - 1) / rows - 1, 0) / 2)
    filtered = gaussian_filter(relief, sigma=(sigma_y, sigma_x), mode=('nearest', 'wrap'))
    periodic = np.concatenate([filtered, filtered[:, :1]], axis=1)
    y, x = np.meshgrid(np.linspace(0, h - 1, rows + 1), np.arange(n) * w / n, indexing='ij')
    return np.clip(map_coordinates(periodic, [y, x], order=1, mode='nearest', prefilter=False), 0, 1)


def build(masks, s):
    relief = masks[0].astype(float)
    if s.invert:
        relief = 1 - relief
    warnings = []
    mismatch = float(np.mean(~np.isclose(relief[:, 0], relief[:, -1], atol=1e-6)))
    if mismatch:
        warnings.append(f'Source seam differs on {mismatch:.0%} of rows. The mesh stays closed; enable seamless mirror tiling to make the pattern continuous.')
    if s.seamless:
        relief = np.concatenate([relief, relief[:, ::-1]], axis=1)
        warnings.append('Seamless mirror tiling repeats the source plus its horizontal reflection around the circumference.')
    h, w = relief.shape
    length = math.pi * s.diameter * h / w if s.proportions else s.length
    if not 5 <= length <= 500:
        raise InputError(f'Proportional roller length would be {length:.2f} mm, outside the supported 5–500 mm range. Change diameter, image proportions, or disable proportional sizing.')
    spacing = SPACING[s.quality]
    n = max(64, math.ceil(math.pi * s.diameter / spacing))
    rows = max(8, math.ceil(length / spacing))
    # Never silently turn Fine back into a coarse mesh on a large roller.
    if n * (rows + 1) > MAX_SURFACE_SAMPLES:
        raise InputError(f'This quality and size require {n * (rows + 1):,} surface vertices, above the {MAX_SURFACE_SAMPLES:,} local memory limit. Choose a lower quality or smaller roller; resolution has not been reduced silently.')
    levels = sample_relief(relief, n, rows, math.pi * s.diameter, length, s.smoothing)
    radius = s.diameter / 2 - s.depth * levels
    theta = np.arange(n) * (2 * math.pi / n)
    z = np.linspace(0, length, rows + 1)
    vertices = np.stack([radius * np.cos(theta), radius * np.sin(theta), np.broadcast_to(z[:, None], radius.shape)], axis=-1).reshape(-1, 3)
    i = np.arange(n, dtype=np.int64)
    k = (i + 1) % n
    a = np.arange(rows, dtype=np.int64)[:, None] * n + i
    b = np.arange(rows, dtype=np.int64)[:, None] * n + k
    c, d = b + n, a + n
    sides = np.stack([np.stack([a, b, c], axis=-1), np.stack([a, c, d], axis=-1)], axis=2).reshape(-1, 3)
    face_parts = [sides]
    if s.bore:
        offset = len(vertices)
        inner = np.column_stack([s.bore / 2 * np.cos(theta), s.bore / 2 * np.sin(theta), np.zeros(n)])
        vertices = np.vstack([vertices, inner, inner + [0, 0, length]])
        a, b, c, d = offset + i, offset + k, offset + n + k, offset + n + i
        u, v = rows * n + i, rows * n + k
        face_parts.extend([np.column_stack(f) for f in [(a, c, b), (a, d, c), (i, a, b), (i, b, k), (u, v, c), (u, c, d)]])
    else:
        bottom, top = len(vertices), len(vertices) + 1
        vertices = np.vstack([vertices, [0, 0, 0], [0, 0, length]])
        face_parts.extend([np.column_stack([np.full(n, bottom), k, i]), np.column_stack([np.full(n, top), rows * n + i, rows * n + k])])
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.vstack(face_parts), process=False)
    warnings.append(f'Bilinear relief interpolation; maximum mesh spacing {spacing:g} mm. Surface smoothing is {s.smoothing:g} mm (Gaussian sigma). Set smoothing to 0 to retain all source texture; mesh antialias filtering still prevents downsampling noise.')
    pixel_mm = min(math.pi * s.diameter / w, length / h)
    distance = cv2.distanceTransform((relief > 0).astype('uint8'), cv2.DIST_L2, 5)
    if distance.max() > 0 and np.any((distance > 0) & (distance * 2 * pixel_mm < s.min_wall)):
        warnings.append('Some pattern edges or features are below the minimum printable feature size. Inspect the preview before printing.')
    return mesh, warnings, {'diameter': s.diameter, 'length': length, 'recess_depth': s.depth,
                            'bore': s.bore, 'circumference_cell_mm': math.pi * s.diameter / n,
                            'axial_cell_mm': length / rows, 'seam_mismatch_fraction': mismatch,
                            'smoothing_mm': s.smoothing, 'source_circumference_pixel_mm': math.pi * s.diameter / w,
                            'source_axial_pixel_mm': length / (h - 1)}
