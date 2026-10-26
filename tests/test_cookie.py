import numpy as np
import pytest
from PIL import Image
from backend.models import Settings
from backend.imaging.segment import InputError, segment
from backend.geometry.cookie import build
from backend.geometry.validation import export_validated
from .samples import cookie, encoded


def make(kind='smile', **kwargs):
    s = Settings(**kwargs)
    masks, _ = segment(encoded(cookie(kind)), 'cookie', s.tolerance)
    return build(masks, s)


@pytest.mark.parametrize('kind', ['smile', 'star', 'loop'])
def test_closed_connected_export(kind):
    mesh, warnings, dimensions = make(kind)
    restored, data = export_validated(mesh)
    assert len(data) == 84 + len(restored.faces) * 50
    assert restored.body_count == 1
    assert np.all(restored.area_faces > 1e-12)
    assert dimensions['cutting_width'] == pytest.approx(80)
    assert restored.bounds[0, 2] == pytest.approx(-2)
    assert restored.bounds[1, 2] == pytest.approx(7)
    assert restored.extents[0] == pytest.approx(86, abs=.02)
    assert np.any(np.isclose(restored.vertices[:, 2], 5))
    assert np.any(np.isclose(restored.vertices[:, 2], -1))


def test_vertical_ray_heights_and_frame():
    mesh, _, _ = make()
    # Check actual flat surfaces in known green, blue, red, frame positions.
    # This verifies geometry, rather than checking metadata.
    triangles = mesh.triangles
    def flat_z_at(x, y):
        found = []
        for triangle in triangles:
            if np.ptp(triangle[:, 2]) > 1e-5:
                continue
            a, b, c = triangle[:, :2]
            v0, v1, v2 = b-a, c-a, np.array([x, y])-a
            cross = v0[0]*v1[1] - v0[1]*v1[0]
            if abs(cross) < 1e-10:
                continue
            u = (v2[0]*v1[1] - v2[1]*v1[0])/cross
            v = (v0[0]*v2[1] - v0[1]*v2[0])/cross
            if u >= -1e-6 and v >= -1e-6 and u+v <= 1+1e-6:
                found.append(triangle[0, 2])
        return sorted(set(round(float(z), 4) for z in found))
    scale = 80/216
    assert flat_z_at((84-128)*scale, -(88-128)*scale) == [-1, 5]
    assert flat_z_at(0, 0) == [-1, 0]
    assert flat_z_at(39.5, 0) == [-1, 7]
    assert flat_z_at(41.5, 0) == [-2, 0]


@pytest.mark.parametrize('kind,match', [('open', 'open'), ('outside', 'outside')])
def test_invalid(kind, match):
    with pytest.raises(InputError, match=match) as exc:
        make(kind)
    assert exc.value.preview.startswith('data:image/png')


def test_size_by_height_and_custom_parameters():
    mesh, _, dimensions = make(size_axis='height', size=100, red_height=9, green_height=6, backing=1.4, frame_height=3, frame_offset=4)
    export_validated(mesh)
    assert dimensions['cutting_height'] == pytest.approx(100)
    assert mesh.bounds[:, 2] == pytest.approx([-3, 9])
    assert mesh.extents[0] == pytest.approx(108, abs=.02)


def test_antialias_and_white_not_blue():
    masks, _ = segment(encoded(cookie(antialias=True)), 'cookie', 30)
    assert masks[1][0, 0] == 0
    export_validated(build(masks, Settings())[0])


def test_invalid_colour_and_transparency():
    image = cookie(); image.putpixel((1, 1), (128, 0, 128))
    with pytest.raises(InputError, match='invalid colour'):
        segment(encoded(image), 'cookie', 30)
    transparent = cookie().convert('RGBA'); transparent.putpixel((0, 0), (0, 0, 255, 0))
    masks, _ = segment(encoded(transparent), 'cookie', 30)
    assert masks[1][0, 0] == 0


def test_multiple_boundaries_rejected():
    from PIL import ImageDraw
    image = cookie(); ImageDraw.Draw(image).ellipse((1, 1, 10, 10), outline='red', width=2)
    with pytest.raises(InputError, match='exactly one'):
        build(segment(encoded(image), 'cookie', 30)[0], Settings())


def test_rectangular_aspect_ratio_and_minimum_wall():
    from PIL import ImageDraw
    image = Image.new('RGB', (256, 160), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 220, 120), fill='blue', outline='red', width=2)
    masks, _ = segment(encoded(image), 'cookie', 30)
    mesh, warnings, dimensions = build(masks, Settings(size=100, min_wall=1.5))
    export_validated(mesh)
    assert dimensions['cutting_width'] == pytest.approx(100)
    assert dimensions['cutting_height'] == pytest.approx(100 * 100.5 / 200.5)
    assert any('thickened inward' in w for w in warnings)
