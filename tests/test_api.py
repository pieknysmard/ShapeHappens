import base64
import io
import json
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from backend.main import app
from .samples import cookie, roller, encoded

client = TestClient(app)


@pytest.mark.parametrize('mode,kind', [('cookie', 'smile'), ('roller', 'diagonal'), ('roller', 'grayscale')])
def test_actual_preview_matches_download(mode, kind):
    response = client.post('/api/generate', files={'image': ('input.png', encoded(cookie(kind) if mode == 'cookie' else roller(kind)), 'image/png')}, data={'settings': json.dumps({'mode': mode, 'quality': 'draft'})})
    assert response.status_code == 200, response.text
    result = response.json()
    stl = trimesh.load(io.BytesIO(base64.b64decode(result['stl'])), file_type='stl', force='mesh')
    if mode == 'cookie':
        positions = np.array(result['positions']).reshape(-1, 3, 3)
        assert np.array_equal(positions, stl.triangles)
        assert len(result['colors']) == len(result['positions'])
    else:
        # The preview loads the exact downloadable STL, without a proxy mesh
        # or a second enormous JSON triangle array.
        assert result['preview_mode'] == 'roller'
        assert 'positions' not in result and 'colors' not in result
        assert len(stl.faces) == result['stats']['triangles']
    assert result['stats']['watertight'] and result['stats']['manifold']


def test_invalid_has_highlight_and_no_stl():
    response = client.post('/api/generate', files={'image': ('open.png', encoded(cookie('open')), 'image/png')})
    assert response.status_code == 422
    assert response.json()['segmented'].startswith('data:image/png')
    assert 'stl' not in response.json()


def test_invalid_parameters_and_upload():
    response = client.post('/api/generate', files={'image': ('x.png', b'not a png', 'image/png')})
    assert response.status_code == 422
    response = client.post('/api/generate', files={'image': ('x.png', encoded(cookie()), 'image/png')}, data={'settings': '{"backing":0}'})
    assert response.status_code == 422
