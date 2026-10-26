import base64
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import Settings
from .imaging.segment import InputError, segment
from .geometry import cookie, roller
from .geometry.validation import export_validated

app = FastAPI(title='ShapeHappens Generator')


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.post('/api/generate')
def generate(image: UploadFile = File(...), settings: str = Form('{}')):
    preview = None
    try:
        s = Settings.model_validate_json(settings)
        data = image.file.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            raise InputError('PNG file must be no larger than 12 MB.')
        masks, preview = segment(data, s.mode, s.tolerance)
        mesh, warnings, dimensions = (cookie if s.mode == 'cookie' else roller).build(masks, s)
        mesh, stl = export_validated(mesh)
        result = {'stl': base64.b64encode(stl).decode(), 'segmented': preview, 'warnings': warnings,
                  'stats': {'triangles': len(mesh.faces), 'bounds': mesh.bounds.tolist(),
                            'size': mesh.extents.tolist(), 'volume_mm3': mesh.volume,
                            'watertight': True, 'manifold': True, 'components': mesh.body_count,
                            'dimensions': dimensions}}
        if s.mode == 'roller':
            # Preview decodes these exact STL bytes. Avoid millions of decimal
            # JSON positions/colours that made high-quality meshes impractical.
            return {**result, 'preview_mode': 'roller'}
        # Triangle positions and colours refer to the reloaded final STL only.
        centers = mesh.triangles_center
        colors = np.full((len(mesh.faces), 3), [0.68, 0.72, 0.77])
        if s.mode == 'cookie':
            colors[:] = [0.25, 0.45, 0.95]
            colors[centers[:, 2] < -s.backing - 1e-4] = [0.9, 0.65, 0.2]
            positive = centers[:, 2] > 1e-4
            colors[positive] = [0.95, 0.16, 0.2]
            # Classify against actual green planar regions, including side faces.
            from shapely import contains_xy
            from .imaging.segment import contours
            from shapely import affinity
            from shapely.geometry import Polygon
            outer = Polygon(contours(masks[0]).exterior)
            x0, y0, x1, y1 = outer.bounds
            factor = s.size / ((x1 - x0) if s.size_axis == 'width' else (y1 - y0))
            green = affinity.scale(affinity.translate(contours(masks[2]), -(x0+x1)/2, -(y0+y1)/2), xfact=factor, yfact=-factor, origin=(0, 0))
            inside_green = contains_xy(green.buffer(0.001), centers[:, 0], centers[:, 1])
            colors[positive & inside_green & (centers[:, 2] <= s.green_height + 1e-4)] = [0.13, 0.75, 0.36]
            world_outer = affinity.scale(affinity.translate(outer, -(x0+x1)/2, -(y0+y1)/2), xfact=factor, yfact=-factor, origin=(0, 0))
            colors[(~contains_xy(world_outer.buffer(0.001), centers[:, 0], centers[:, 1])) & ~positive] = [0.9, 0.65, 0.2]
        return {**result, 'positions': mesh.triangles.reshape(-1).tolist(),
                'colors': np.repeat(colors, 3, axis=0).reshape(-1).round(3).tolist(),
                'preview_mode': 'cookie'}
    except (InputError, ValidationError, json.JSONDecodeError) as exc:
        return JSONResponse(status_code=422, content={'error': str(exc), 'segmented': getattr(exc, 'preview', None) or preview})
    except Exception:
        import logging
        logging.exception('Geometry generation failed')
        return JSONResponse(status_code=500, content={'error': 'Geometry generation failed integrity checks. Try higher-resolution artwork or less extreme dimensions.', 'segmented': preview})


dist = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
