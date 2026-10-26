import math
import base64
import io
import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError
from backend.models import Settings
from backend.imaging.segment import segment
from backend.geometry.roller import build, sample_relief
from backend.geometry.validation import export_validated
from .samples import roller, encoded


@pytest.mark.parametrize('kind', ['diagonal', 'squares', 'seam'])
@pytest.mark.parametrize('bore', [0, 8])
def test_roller_geometry(kind, bore):
    s = Settings(mode='roller', bore=bore, quality='draft')
    masks, _ = segment(encoded(roller(kind)), 'roller', 30)
    mesh, _, dimensions = build(masks, s)
    restored, _ = export_validated(mesh)
    assert restored.body_count == 1
    assert restored.extents[2] == pytest.approx(100)
    assert np.all(restored.extents[:2] <= np.array([40.001, 40.001]))
    assert max(restored.extents[:2]) > 39.9
    radius = np.linalg.norm(restored.vertices[:, :2], axis=1)
    assert np.any(np.isclose(radius, 20, atol=1e-5))
    assert np.any(np.isclose(radius, 19, atol=1e-5))
    outer = radius > 10
    assert radius[outer].min() == pytest.approx(19, abs=1e-5)
    assert dimensions['recess_depth'] == 1
    assert mesh.volume < math.pi * (20**2 - (bore/2)**2) * 100
    assert mesh.volume > math.pi * (19**2 - (bore/2)**2) * 100 * .99
    assert np.all(mesh.area_faces > 1e-12)


def test_seam_connectivity_and_depth():
    s = Settings(mode='roller', quality='draft')
    mesh, _, _ = build(segment(encoded(roller('seam')), 'roller', 30)[0], s)
    # Both sides of seam must be recessed at the middle of the roller.
    vertices = mesh.vertices
    seam = (abs(vertices[:, 1]) < 1.0) & (vertices[:, 0] > 0) & (vertices[:, 2] > 40) & (vertices[:, 2] < 60)
    assert seam.sum() > 5
    assert np.linalg.norm(vertices[seam, :2], axis=1) == pytest.approx(np.full(seam.sum(), 19))
    assert np.all(mesh.edges_unique_inverse >= 0)
    assert np.all(np.bincount(mesh.edges_unique_inverse) == 2)


def test_seamless_proportions_invert_and_resolution():
    masks, _ = segment(encoded(roller()), 'roller', 30)
    s = Settings(mode='roller', seamless=True, proportions=True, invert=True, quality='draft')
    mesh, warnings, dims = build(masks, s)
    export_validated(mesh)
    assert dims['length'] == pytest.approx(math.pi * 40 * 96 / 256)
    assert dims['axial_cell_mm'] <= .8
    assert any('mirror' in w for w in warnings)


def test_bore_wall_limits():
    with pytest.raises(ValidationError, match='minimum wall'):
        Settings(mode='roller', diameter=40, depth=2, bore=36)


@pytest.mark.parametrize('invert', [False, True])
@pytest.mark.parametrize('bore', [0, 8])
def test_grayscale_depths_survive_stl(invert, bore):
    # Axial bands ensure every expected gray level is sampled at every angle.
    tones = np.repeat(np.array([0, 64, 128, 192, 255], dtype='uint8'), 16)
    image = Image.fromarray(np.repeat(tones[:, None], 64, axis=1))
    masks, preview = segment(encoded(image), 'roller', 0)
    interpreted = np.array(Image.open(io.BytesIO(base64.b64decode(preview.split(',')[1]))))
    assert np.array_equal(interpreted[:, :, 0], np.array(image))
    s = Settings(mode='roller', depth=2, length=40, quality='draft', bore=bore, invert=invert)
    restored, _ = export_validated(build(masks, s)[0])
    radius = np.linalg.norm(restored.vertices[:, :2], axis=1)
    exterior = radius > 10
    expected = 20 - 2 * (tones[::16] / 255 if invert else 1 - tones[::16] / 255)
    # Interpolation adds valid transition depths; verify plateau depths using
    # actual STL vertices well inside each band, rather than forbidding ramps.
    for index, expected_radius in enumerate(expected):
        center_z = (index * 16 + 7.5) / 79 * 40
        band = exterior & (abs(restored.vertices[:, 2] - center_z) < 1)
        assert band.any()
        assert radius[band] == pytest.approx(np.full(band.sum(), expected_radius), abs=1e-4)
    assert restored.is_watertight and restored.body_count == 1


def test_grayscale_seam_and_transparency():
    image = roller('grayscale').convert('RGBA')
    image.putpixel((40, 40), (0, 0, 0, 0))
    masks, _ = segment(encoded(image), 'roller', 0)
    assert masks[0][40, 40] == 0
    assert np.unique(masks[0]).size > 100
    mesh, _, dims = build(masks, Settings(mode='roller', quality='draft'))
    export_validated(mesh)
    assert dims['seam_mismatch_fraction'] == 0


def test_grayscale_colour_validation():
    from backend.imaging.segment import InputError
    image = Image.new('RGB', (16, 16), (120, 128, 124))
    masks, _ = segment(encoded(image), 'roller', 8)
    assert masks[0][0, 0] == pytest.approx((255 - 124) / 255)
    with pytest.raises(InputError, match='non-grayscale'):
        segment(encoded(image), 'roller', 0)


def test_bilinear_sampling_reproduces_linear_ramp_without_stairs():
    source = np.tile(np.linspace(0, 1, 16)[:, None], (1, 12))
    sampled = sample_relief(source, 48, 120, 40, 30, 0)
    assert sampled[:, 10] == pytest.approx(np.linspace(0, 1, 121), abs=1e-12)
    # Nearest-pixel sampling produced only 16 levels and repeated flat steps.
    assert np.unique(sampled[:, 10]).size == 121


def test_periodic_interpolation_and_antialias_filter():
    source = np.zeros((16, 16)); source[:, -1] = 1
    sampled = sample_relief(source, 64, 32, 40, 20, 0)
    assert sampled[10, -1] == pytest.approx(.25)
    assert sampled[10, -2] == pytest.approx(.5)
    # A high-frequency checker used to alias into large wrong-height patches.
    checker = np.indices((256, 256)).sum(axis=0) % 2
    filtered = sample_relief(checker.astype(float), 32, 32, 40, 20, 0)
    assert np.max(abs(filtered[2:-2] - .5)) < .01


def test_smoothing_is_optional_and_reduces_source_noise():
    source = np.full((64, 64), .5); source[32, 32] = 1
    raw = sample_relief(source, 128, 128, 40, 20, 0)
    smooth = sample_relief(source, 128, 128, 40, 20, .2)
    assert np.std(smooth) < np.std(raw)
    assert smooth.min() >= 0 and smooth.max() <= 1


@pytest.mark.parametrize('quality,spacing', [('draft', .4), ('standard', .12), ('fine', .08)])
def test_requested_mesh_quality_is_honoured(quality, spacing):
    mesh, _, dims = build(segment(encoded(roller('grayscale')), 'roller', 0)[0], Settings(mode='roller', diameter=12, length=10, quality=quality))
    export_validated(mesh)
    assert dims['axial_cell_mm'] <= spacing
    assert dims['circumference_cell_mm'] <= spacing


def test_quality_budget_never_silently_reduces_resolution():
    from backend.imaging.segment import InputError
    with pytest.raises(InputError, match='resolution has not been reduced silently'):
        build([np.zeros((16, 16))], Settings(mode='roller', diameter=200, length=500, quality='fine'))
