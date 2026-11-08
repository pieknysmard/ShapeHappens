import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import library
from backend.geometry.roller import build
from backend.geometry.validation import export_validated
from backend.main import app
from backend.models import Settings
from tests.samples import encoded

client = TestClient(app)


@pytest.mark.parametrize('preset', library.PRESETS)
@pytest.mark.parametrize('bore', [0, 8])
def test_preset_geometry_and_real_through_hole(preset, bore):
    diameter, length, _, _ = library.PRESETS[preset]
    settings = Settings(diameter=diameter, length=length, bore=bore, quality='draft')
    mesh, _, _ = build([np.zeros((8, 8))], settings)
    mesh, _ = export_validated(mesh)
    assert mesh.is_watertight and mesh.body_count == 1
    assert mesh.extents[2] == pytest.approx(length)
    assert max(mesh.extents[:2]) == pytest.approx(diameter, abs=.01)
    # A bore changes topology and removes the full axial cylinder volume.
    assert mesh.euler_number == (0 if bore else 2)
    assert mesh.volume == pytest.approx(np.pi * ((diameter / 2)**2 - (bore / 2)**2) * length, rel=.002)
    assert np.min(np.linalg.norm(mesh.vertices[:, :2], axis=1)) == pytest.approx(bore / 2 if bore else 0, abs=1e-5)


def test_library_archives_exact_source_stl_and_settings_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'LIBRARY_ROOT', tmp_path)
    source = encoded(Image.new('L', (785, 700), 255))
    settings = {'mode': 'roller', 'diameter': 25, 'length': 70, 'bore': 8, 'quality': 'draft'}
    identity = {'pattern_number': 42, 'title': '../../Wild flowers', 'preset': 'mini'}
    results = []
    for revision in [1, 2]:
        response = client.post('/api/generate', files={'image': ('map.png', source, 'image/png')}, data={'settings': json.dumps(settings), 'identity': json.dumps(identity), 'save': 'true'})
        assert response.status_code == 200, response.text
        result = response.json()
        folder = tmp_path / 'rollers' / 'P0042' / 'mini' / f'r{revision:03d}'
        assert result['saved_to'] == str(folder)
        stem = f'P0042_wild-flowers_ROLLER_MINI_L70_D25_DEP1_B8_r{revision:03d}'
        assert result['filename'] == stem + '.stl'
        assert (folder / (stem + '_source.png')).read_bytes() == source
        stl = base64.b64decode(result['stl'])
        assert (folder / (stem + '.stl')).read_bytes() == stl
        metadata = json.loads((folder / (stem + '.json')).read_text())
        assert metadata['settings']['bore'] == 8
        assert metadata['source_filename'] == 'map.png'
        assert metadata['source_sha256'] == hashlib.sha256(source).hexdigest()
        assert metadata['stl_sha256'] == hashlib.sha256(stl).hexdigest()
        results.append(folder)
    assert all(p.is_dir() for p in results)
    assert not list(tmp_path.rglob('.pending-*'))


def test_default_mode_and_opt_out_do_not_write_files(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'LIBRARY_ROOT', tmp_path)
    assert Settings().mode == 'roller' and Settings().bore == 0
    response = client.post('/api/generate', files={'image': ('map.png', encoded(Image.new('L', (8, 8), 255)), 'image/png')}, data={'settings': '{"quality":"draft"}'})
    assert response.status_code == 200
    result = response.json()
    assert result['preview_mode'] == 'roller'
    assert result['filename'].endswith('_B0_r000.stl')
    assert 'saved_to' not in result
    assert not list(tmp_path.iterdir())


def test_preset_mismatch_and_format_advisories():
    source = encoded(Image.new('RGB', (8, 8), 'white'))
    identity = library.Identity(preset='mini')
    with pytest.raises(ValueError, match='Preset dimensions'):
        library.artwork_notes(source, Settings(), identity)
    notes = library.artwork_notes(source, Settings(diameter=25, length=70), identity)
    assert any('785 × 700' in n for n in notes)
    assert any('8-bit grayscale L' in n for n in notes)


def test_archive_write_failure_keeps_model_downloadable(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr('backend.main.archive', fail)
    response = client.post('/api/generate', files={'image': ('map.png', encoded(Image.new('L', (8, 8), 255)), 'image/png')}, data={'settings': '{"quality":"draft"}', 'save': 'true'})
    assert response.status_code == 200
    result = response.json()
    assert result['stl'] and 'saved_to' not in result
    assert any('saving to the local library failed' in w for w in result['warnings'])


def test_concurrent_saves_get_distinct_revisions(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'LIBRARY_ROOT', tmp_path)
    def save(_):
        return library.archive(b'png', b'stl', Settings(), library.Identity(), {'dimensions': {'length': 100}}, [])
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(save, range(3)))
    assert sorted(r['revision'] for r in results) == [1, 2, 3]
