import io
import numpy as np
import trimesh
from ..imaging.segment import InputError


def validate(mesh):
    if not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise InputError('Geometry contains empty or invalid vertices.')
    if not mesh.is_watertight or not mesh.is_winding_consistent or not mesh.is_volume:
        raise InputError('Geometry is not a closed, consistently oriented solid. Repair the artwork or adjust dimensions.')
    if mesh.body_count != 1:
        raise InputError('Geometry contains disconnected solids. Ensure every feature connects to the backing.')
    if np.any(mesh.area_faces < 1e-12):
        raise InputError('Geometry contains degenerate triangles. Increase image resolution or adjust dimensions.')


def export_validated(mesh):
    validate(mesh)
    data = mesh.export(file_type='stl')
    restored = trimesh.load(io.BytesIO(data), file_type='stl', force='mesh', process=True)
    validate(restored)
    if not np.allclose(mesh.bounds, restored.bounds, atol=1e-4) or not np.isclose(mesh.volume, restored.volume, rtol=1e-4):
        raise InputError('STL round-trip changed geometry beyond tolerance.')
    return restored, data
