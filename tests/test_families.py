import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import families
from backend.main import app
from backend.models import Settings

client = TestClient(app)


class InlineExecutor:
    def submit(self, function, *args):
        function(*args)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(families, 'FAMILY_ROOT', tmp_path)
    monkeypatch.setattr(families, '_executor', InlineExecutor())
    monkeypatch.setattr(families, '_jobs', {})


def png(size=(785, 700), gray=255):
    output = io.BytesIO()
    Image.new('L', size, gray).save(output, 'PNG')
    return output.getvalue()


def item(preset='mini', variants=None, depth=1):
    diameter, length, _, _ = families.PRESETS[preset]
    return {'preset': preset, 'settings': Settings(diameter=diameter, length=length, depth=depth, quality='draft').model_dump(), 'hole_diameter': 8, 'variants': variants or ['F']}


def submit(items=None, files=None, **config):
    return client.post('/api/families/batch', data={'config': json.dumps({'line': 'A', 'line_name': 'Botanical', 'title': 'Roses', 'items': items or [item()], **config})}, files=files)


def test_three_size_batch_both_body_variants_exact_files_and_settings():
    sources = {p: png((values[2], values[3])) for p, values in families.PRESETS.items()}
    response = submit(items=[item(p, ['F', 'H']) for p in families.PRESETS], files={p: ('my artwork.png', data, 'image/png') for p, data in sources.items()})
    assert response.status_code == 202, response.text
    job = response.json()
    assert job['state'] == 'complete' and job['completed'] == job['total'] == 6
    family = client.get('/api/families/A00001').json()
    assert family['revisions'] == [1]
    for member in family['items']:
        assert member['source_filename'] == 'my artwork.png'
        for output in member['outputs']:
            prefix = f'A00001-{families.CODES[member["preset"]]}{output["body"]}'
            assert output['stl'] == prefix + '_my_artwork.stl'
            assert client.get(output['png_url']).content == sources[member['preset']]
            stl_response = client.get(output['stl_url'])
            assert stl_response.status_code == 200
            metadata = client.get(output['json_url']).json()
            assert metadata['source_sha256'] == hashlib.sha256(sources[member['preset']]).hexdigest()
            assert metadata['stl_sha256'] == hashlib.sha256(stl_response.content).hexdigest()
            assert metadata['settings']['bore'] == (8 if output['body'] == 'H' else 0)
            assert metadata['stats']['watertight'] and metadata['stats']['components'] == 1
    summary = client.get('/api/families').json()['families']
    assert len(summary) == 1 and summary[0]['id'] == 'A00001'


def test_reopen_reuses_sources_retains_old_revision_and_enforces_conflicts():
    source = png()
    first = submit(files={'mini': ('original.png', source, 'image/png')}).json()['family']
    old_stl = client.get(first['items'][0]['outputs'][0]['stl_url']).content
    revised = submit(items=[item(depth=2)], number=1, base_revision=1)
    assert revised.status_code == 202, revised.text
    second = revised.json()['family']
    assert second['revision'] == 2
    assert second['items'][0]['settings']['depth'] == 2
    assert client.get(second['items'][0]['source_url']).content == source
    assert client.get(first['items'][0]['outputs'][0]['stl_url']).content == old_stl
    assert client.get('/api/families/A00001?revision=1').json()['revision'] == 1
    assert client.get('/api/families/A00001').json()['revisions'] == [1, 2]
    assert submit(number=1, base_revision=1).status_code == 409
    assert submit(number=1).status_code == 409


def test_automatic_numbers_are_per_line_and_line_names_are_consistent():
    files = {'mini': ('source.png', png(), 'image/png')}
    assert submit(files=files).json()['family_id'] == 'A00001'
    assert submit(files=files).json()['family_id'] == 'A00002'
    assert submit(files=files, line='B', line_name='Christmas').json()['family_id'] == 'B00001'
    assert submit(files=files, line_name='Geometric').status_code == 409
    assert submit(files=files, line_name='').json()['family']['line_name'] == 'Botanical'


def test_invalid_second_image_does_not_publish_a_partial_revision():
    source = png()
    job = submit(items=[item(), item('standard')], files={'mini': ('valid.png', source, 'image/png'), 'standard': ('broken.png', b'not a PNG', 'image/png')}).json()
    assert job['state'] == 'failed'
    assert client.get('/api/families').json()['families'] == []
    assert client.get('/api/families/A00001').status_code == 404
    assert not list(families.FAMILY_ROOT.rglob('*.stl'))
    assert not list(families.FAMILY_ROOT.rglob('.pending-*'))


def test_invalid_new_revision_preserves_last_saved_family():
    submit(files={'mini': ('valid.png', png(), 'image/png')})
    response = submit(number=1, base_revision=1, files={'mini': ('broken.png', b'no', 'image/png')})
    assert response.json()['state'] == 'failed'
    assert client.get('/api/families/A00001').json()['revisions'] == [1]


@pytest.mark.parametrize('overrides', [{'line': '../A'}, {'number': 100000}, {'number': 0}, {'line': 'AB'}])
def test_invalid_identifiers(overrides):
    assert submit(files={'mini': ('x.png', png(), 'image/png')}, **overrides).status_code == 422


def test_size_hole_missing_images_and_duplicate_members_validation():
    bad = item(); bad['settings']['length'] = 75
    assert submit(items=[bad]).status_code == 422
    bad = item(variants=['H']); bad['hole_diameter'] = 25
    assert submit(items=[bad]).status_code == 422
    assert submit().status_code == 422
    assert submit(items=[item(), item()]).status_code == 422


def test_file_access_is_limited_to_published_manifest():
    submit(files={'mini': ('../../malicious:name.png', png(), 'image/png')})
    family = client.get('/api/families/A00001').json()
    assert family['items'][0]['outputs'][0]['stl'] == 'A00001-MF_malicious_name.stl'
    assert client.get('/api/families/A00001/revisions/1/files/family.json').status_code == 404
    assert client.get('/api/families/A00001/revisions/1/files/private.txt').status_code == 404
    assert client.get('/api/families/not-an-id').status_code == 422


def test_batch_is_queued_and_only_published_after_processing(monkeypatch):
    tasks = []
    class DeferredExecutor:
        def submit(self, function, *args):
            tasks.append((function, args))
    monkeypatch.setattr(families, '_executor', DeferredExecutor())
    response = submit(files={'mini': ('source.png', png(), 'image/png')})
    job = response.json()
    assert response.status_code == 202 and job['state'] == 'queued'
    assert client.get('/api/families').json()['families'] == []
    assert submit(number=1, files={'mini': ('source.png', png(), 'image/png')}).status_code == 409
    function, args = tasks[0]; function(*args)
    assert client.get('/api/families/jobs/' + job['job_id']).json()['state'] == 'complete'
    assert client.get('/api/families/A00001').status_code == 200


def test_replacing_source_does_not_duplicate_prefix_on_new_revision():
    submit(files={'mini': ('old.png', png(), 'image/png')})
    job = submit(number=1, base_revision=1, files={'mini': ('A00001-MF_new.png', png(gray=128), 'image/png')}).json()
    assert job['state'] == 'complete'
    assert job['family']['items'][0]['outputs'][0]['stl'] == 'A00001-MF_new.stl'
