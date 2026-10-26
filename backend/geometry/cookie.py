import cv2
import numpy as np
import trimesh
import manifold3d
from shapely import affinity
from shapely.geometry import Polygon

from ..imaging.segment import InputError, contours, png_url


def extrude(shape, bottom, top):
    parts = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
    meshes = []
    for polygon in parts:
        if polygon.is_empty:
            continue
        rings = [np.array(polygon.exterior.coords)[:-1]] + [np.array(r.coords)[:-1] for r in polygon.interiors]
        solid = manifold3d.CrossSection(rings, manifold3d.FillRule.EvenOdd).extrude(top - bottom)
        meshes.append(solid.translate((0, 0, bottom)))
    return meshes


def build(masks, settings):
    red, blue, green, _ = masks
    components, _ = cv2.connectedComponents(red, connectivity=8)
    if components != 2:
        raise InputError('Require exactly one connected red cutting outline per image.')
    # Flood the complement from a padded exterior; a closed ring must enclose
    # exactly one region. Do not close gaps automatically.
    padded = np.pad(red, 1)
    exterior = (1 - padded).astype('uint8')
    cv2.floodFill(exterior, None, (0, 0), 2)
    inside = (exterior[1:-1, 1:-1] == 1).astype('uint8')
    count, _ = cv2.connectedComponents(inside, connectivity=4)
    if count != 2:
        overlay = np.full((*red.shape, 3), 255, dtype='uint8')
        overlay[red > 0] = [255, 0, 0]
        reachable = (exterior[1:-1, 1:-1] == 2) & ((blue | green) > 0)
        highlight = cv2.dilate(reachable.astype('uint8'), np.ones((5, 5), np.uint8)) > 0
        # Try closing only to LOCATE the gap in the error overlay. The closed
        # mask is never used to generate geometry or silently repair artwork.
        for kernel in [3, 5, 9, 17, 31]:
            closed = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
            probe = 1 - np.pad(closed, 1)
            cv2.floodFill(probe, None, (0, 0), 2)
            if np.any(probe == 1) and not inside.any():
                highlight = cv2.dilate(((closed > 0) & (red == 0)).astype('uint8'), np.ones((5, 5), np.uint8)) > 0
                break
        overlay[highlight & (red == 0)] = [255, 0, 255]
        raise InputError('Red outline is open or encloses multiple regions. Magenta highlights a candidate gap, or interior-colour pixels leaking to the exterior if the gap cannot be localized. Close the ring; exactly one enclosed region is required.', png_url(overlay))
    if np.any((green > 0) & (inside == 0)):
        overlay = np.full((*red.shape, 3), 255, dtype='uint8')
        overlay[red > 0] = [255, 0, 0]
        overlay[green > 0] = [0, 255, 0]
        overlay[(green > 0) & (inside == 0)] = [255, 0, 255]
        raise InputError('Green details extend outside the red boundary (magenta).', png_url(overlay))
    if np.any((blue > 0) & (inside == 0)):
        raise InputError('Blue fill must lie inside the red cutting outline.')
    red_shape = contours(red)
    if red_shape.geom_type != 'Polygon':
        raise InputError('Red must form a single continuous ring.')
    outer = Polygon(red_shape.exterior)
    x0, y0, x1, y1 = outer.bounds
    scale = settings.size / ((x1 - x0) if settings.size_axis == 'width' else (y1 - y0))

    def transform(shape):
        shape = affinity.translate(shape, -(x0 + x1) / 2, -(y0 + y1) / 2)
        return affinity.scale(shape, xfact=scale, yfact=-scale, origin=(0, 0))

    outer = transform(outer)
    red_shape = transform(red_shape)
    details = transform(contours(green))
    # Preserve original red ink; only thicken inward where the ink is too thin.
    wall = red_shape.union(outer.difference(outer.buffer(-settings.min_wall)))
    if not outer.buffer(-settings.min_wall).area:
        raise InputError('Minimum wall thickness consumes the entire interior. Reduce it or increase cutter size.')
    frame = outer.buffer(settings.frame_offset, quad_segs=24).difference(outer)
    meshes = (extrude(outer, -settings.backing, 0) +
              extrude(wall, 0, settings.red_height) +
              extrude(details, 0, settings.green_height) +
              extrude(frame, -settings.frame_height, 0))
    # Keep booleans in Manifold's native precision until the final mesh. A
    # float32 mesh round-trip of each touching component can create slivers.
    solid = manifold3d.Manifold.batch_boolean(meshes, manifold3d.OpType.Add)
    # Remove numerical slivers below 0.1 micrometre before STL's float32
    # quantization. All manufacturing surfaces move less than this tolerance.
    native = solid.simplify(0.0001).to_mesh64()
    mesh = trimesh.Trimesh(vertices=np.array(native.vert_properties)[:, :3], faces=np.array(native.tri_verts), process=True)
    warnings = []
    if not details.is_empty:
        # Morphological opening estimates whether any local feature is thin,
        # preserving all detail in the actual output.
        thin = details.difference(details.buffer(-settings.min_wall / 2).buffer(settings.min_wall / 2))
        if thin.area > details.area * 0.05:
            warnings.append('Some green details or corners are below the minimum printable feature size; retained unchanged. Thicken artwork or increase nominal size.')
    if (wall.area - red_shape.area) > 0.01:
        warnings.append('Thin red wall sections were thickened inward to the configured minimum; the outside cutting outline is unchanged.')
    return mesh, warnings, {'cutting_width': x1 * scale - x0 * scale, 'cutting_height': (y1 - y0) * scale,
                            'source_pixel_mm': scale, 'red_top': settings.red_height,
                            'green_top': settings.green_height, 'backing_bottom': -settings.backing,
                            'frame_bottom': -settings.frame_height, 'frame_offset': settings.frame_offset}
