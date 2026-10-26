"""Export verified fixtures for manual inspection in the browser or a slicer."""
import json
from pathlib import Path
from backend.models import Settings
from backend.imaging.segment import segment
from backend.geometry import cookie as cutter_geometry, roller as roller_geometry
from backend.geometry.validation import export_validated
from .samples import cookie, roller, encoded


def main():
    target = Path(__file__).resolve().parents[1] / 'test-output'
    target.mkdir(exist_ok=True)
    report = {}
    for mode, kinds, source, geometry in [('cookie', ['smile', 'star', 'loop'], cookie, cutter_geometry), ('roller', ['diagonal', 'squares', 'seam', 'grayscale'], roller, roller_geometry)]:
        for kind in kinds:
            settings = Settings(mode=mode)
            masks, _ = segment(encoded(source(kind)), mode, settings.tolerance)
            mesh, warnings, dims = geometry.build(masks, settings)
            mesh, stl = export_validated(mesh)
            name = f'{mode}_{kind}'
            (target / f'{name}.stl').write_bytes(stl)
            report[name] = {'triangles': len(mesh.faces), 'size_mm': mesh.extents.tolist(), 'volume_mm3': mesh.volume, 'watertight': mesh.is_watertight, 'components': mesh.body_count, 'dimensions': dims, 'warnings': warnings}
    (target / 'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: {'triangles': v['triangles'], 'watertight': v['watertight'], 'components': v['components']} for k, v in report.items()}, indent=2))


if __name__ == '__main__':
    main()
