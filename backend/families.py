"""Persistent roller families and bounded, transactional batch generation."""
import copy
import hashlib
import json
import logging
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .geometry import roller
from .geometry.validation import export_validated
from .imaging.segment import InputError, segment
from .library import Identity, PRESETS, artwork_notes
from .models import Settings

FAMILY_ROOT = Path(__file__).resolve().parents[1] / 'roller-families'
CODES = {'standard': 'S', 'mini': 'M', 'extended': 'E'}
router = APIRouter(prefix='/api/families')
_lock = threading.RLock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='roller-family')
_jobs = {}


class FamilyItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset: Literal['standard', 'mini', 'extended']
    settings: Settings
    variants: list[Literal['F', 'H']] = Field(default_factory=lambda: ['F'], min_length=1, max_length=2)
    hole_diameter: float = Field(8, ge=.1, le=180)

    @model_validator(mode='after')
    def validate_geometry(self):
        diameter, length, _, _ = PRESETS[self.preset]
        if self.settings.mode != 'roller' or self.settings.diameter != diameter or self.settings.length != length or self.settings.proportions:
            raise ValueError('Family members must use their exact roller preset dimensions and fixed length.')
        if len(set(self.variants)) != len(self.variants):
            raise ValueError('Choose each body variant only once.')
        for variant in self.variants:
            variant_settings(self, variant)
        return self


def variant_settings(item, variant):
    return Settings.model_validate({**item.settings.model_dump(), 'bore': item.hole_diameter if variant == 'H' else 0})


class FamilyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line: str = Field('A', pattern='^[A-Z]$')
    line_name: str = Field('', max_length=80)
    number: int | None = Field(None, ge=1, le=99999)
    title: str = Field('', max_length=100)
    base_revision: int | None = Field(None, ge=1)
    items: list[FamilyItem] = Field(min_length=1, max_length=3)

    @model_validator(mode='after')
    def unique_sizes(self):
        if len({i.preset for i in self.items}) != len(self.items):
            raise ValueError('Use only one image per size in a family.')
        if self.base_revision and self.number is None:
            raise ValueError('An existing family number is required to revise a family.')
        return self


def family_dir(family_id):
    if not re.fullmatch(r'[A-Z]\d{5}', family_id):
        raise HTTPException(422, 'Family ID must be one letter and five digits.')
    return FAMILY_ROOT / family_id[0] / family_id


def latest_revision(folder):
    revisions = folder / 'revisions'
    return max([int(p.name[1:]) for p in revisions.iterdir() if p.is_dir() and re.fullmatch(r'r\d+', p.name)] or [0]) if revisions.is_dir() else 0


def read_family(family_id, revision=None):
    folder = family_dir(family_id)
    revision = revision or latest_revision(folder)
    path = folder / 'revisions' / f'r{revision:03d}' / 'family.json'
    if not revision or not path.is_file():
        raise HTTPException(404, 'Saved family revision was not found.')
    return json.loads(path.read_text(encoding='utf-8'))


def public_family(manifest):
    result = copy.deepcopy(manifest)
    base = f'/api/families/{manifest["id"]}/revisions/{manifest["revision"]}/files/'
    for item in result['items']:
        item['source_url'] = base + item['source_file']
        for variant in item['outputs']:
            for kind in ['stl', 'png', 'json']:
                variant[kind + '_url'] = base + variant[kind]
    return result


@router.get('')
def list_families():
    families = []
    if FAMILY_ROOT.is_dir():
        for folder in sorted(FAMILY_ROOT.glob('[A-Z]/[A-Z][0-9][0-9][0-9][0-9][0-9]')):
            try:
                manifest = read_family(folder.name)
                families.append({key: manifest[key] for key in ['id', 'line', 'line_name', 'number', 'title', 'revision', 'created_utc'] } | {'sizes': [i['preset'] for i in manifest['items']]})
            except (HTTPException, ValueError, OSError, KeyError):
                logging.exception('Cannot read family %s', folder.name)
    return {'families': families}


@router.get('/jobs/{job_id}')
def job_status(job_id: str):
    with _lock:
        if job_id not in _jobs:
            raise HTTPException(404, 'Batch job not found. Reopen the saved family from the library if the server restarted.')
        return copy.deepcopy(_jobs[job_id])


def safe_stem(filename):
    # Keep the source name after the prefix, without paths, existing family prefixes or Windows punctuation.
    stem = Path((filename or 'artwork.png').replace('\\', '/')).stem
    stem = re.sub(r'^[A-Z]\d{5}-[SME][HF][_-]?', '', stem)
    return re.sub(r'[^\w.-]+', '_', stem, flags=re.UNICODE).strip('._')[:48] or 'artwork'


def progress(job_id, **values):
    with _lock:
        _jobs[job_id].update(values)


def process_batch(job_id, request, family_id, revision, pending, sources):
    try:
        progress(job_id, state='running')
        manifest = {'schema_version': 1, 'id': family_id, 'line': request.line, 'line_name': request.line_name.strip(), 'number': int(family_id[1:]), 'title': request.title.strip(), 'revision': revision, 'created_utc': datetime.now(timezone.utc).isoformat(), 'items': []}
        completed = 0
        for item in request.items:
            data, filename = sources[item.preset]
            outputs = []
            for variant in item.variants:
                prefix = f'{family_id}-{CODES[item.preset]}{variant}'
                progress(job_id, current=prefix)
                settings = variant_settings(item, variant)
                masks, _ = segment(data, 'roller', settings.tolerance)
                notes = artwork_notes(data, settings, Identity(preset=item.preset))
                mesh, warnings, dimensions = roller.build(masks, settings)
                mesh, stl = export_validated(mesh)
                stats = {'triangles': len(mesh.faces), 'bounds': mesh.bounds.tolist(), 'size': mesh.extents.tolist(), 'volume_mm3': float(mesh.volume), 'watertight': True, 'manifold': True, 'components': int(mesh.body_count), 'dimensions': dimensions}
                stem = f'{prefix}_{safe_stem(filename)}'
                output = {'body': variant, 'prefix': prefix, 'stl': stem + '.stl', 'png': stem + '.png', 'json': stem + '.json', 'stats': stats, 'warnings': notes + warnings}
                (pending / output['png']).write_bytes(data)
                (pending / output['stl']).write_bytes(stl)
                metadata = {'family_id': family_id, 'revision': revision, 'preset': item.preset, 'source_filename': filename, 'settings': settings.model_dump(), 'stats': stats, 'warnings': output['warnings'], 'source_sha256': hashlib.sha256(data).hexdigest(), 'stl_sha256': hashlib.sha256(stl).hexdigest()}
                (pending / output['json']).write_text(json.dumps(metadata, indent=2), encoding='utf-8')
                outputs.append(output)
                completed += 1
                progress(job_id, completed=completed)
                del mesh, stl, masks
            manifest['items'].append({'preset': item.preset, 'source_filename': filename, 'source_file': outputs[0]['png'], 'settings': {**item.settings.model_dump(), 'bore': 0}, 'hole_diameter': item.hole_diameter, 'variants': item.variants, 'outputs': outputs})
        (pending / 'family.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        final = family_dir(family_id) / 'revisions' / f'r{revision:03d}'
        pending.rename(final)
        progress(job_id, state='complete', family=public_family(manifest), saved_to=str(final), current='')
    except Exception as exc:
        logging.exception('Roller batch %s failed', job_id)
        shutil.rmtree(pending, ignore_errors=True)
        error = str(exc) if isinstance(exc, (InputError, ValidationError)) else 'Batch generation or storage failed. Check disk space, permissions and server logs.'
        progress(job_id, state='failed', error=error, current='')
    finally:
        sources.clear()


@router.post('/batch', status_code=202)
def submit_batch(config: str = Form(...), standard: UploadFile | None = File(None), mini: UploadFile | None = File(None), extended: UploadFile | None = File(None)):
    try:
        request = FamilyRequest.model_validate_json(config)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    uploads = {'standard': standard, 'mini': mini, 'extended': extended}
    with _lock:
        # Bound queued uploads and geometry memory. One batch is meshed at a time.
        if sum(j['state'] in ['queued', 'running'] for j in _jobs.values()) >= 3:
            raise HTTPException(429, 'Three batches are already active or queued. Wait for one to finish.')
        line_folder = FAMILY_ROOT / request.line
        known_name = ''
        if line_folder.is_dir():
            for existing in sorted(line_folder.iterdir()):
                if re.fullmatch(request.line + r'\d{5}', existing.name) and latest_revision(existing):
                    known_name = read_family(existing.name)['line_name'].strip() or known_name
        if known_name and request.line_name.strip() and known_name.casefold() != request.line_name.strip().casefold():
            raise HTTPException(409, f'Line {request.line} is already designated {known_name}. Choose that name or another line letter.')
        if known_name:
            request.line_name = known_name
        numbers = [int(p.name[1:]) for p in line_folder.iterdir() if re.fullmatch(request.line + r'\d{5}', p.name)] if line_folder.is_dir() else []
        number = request.number or max(numbers or [0]) + 1
        if number > 99999:
            raise HTTPException(409, 'This line has no remaining five-digit family numbers.')
        family_id = f'{request.line}{number:05d}'
        folder = family_dir(family_id)
        current = latest_revision(folder)
        if any(j['family_id'] == family_id and j['state'] in ['queued', 'running'] for j in _jobs.values()):
            raise HTTPException(409, 'This family already has an active batch.')
        if current and request.base_revision != current:
            raise HTTPException(409, 'Reopen the latest family revision before saving changes. Existing files have not been overwritten.')
        if not current and request.base_revision:
            raise HTTPException(409, 'The family revision to update no longer exists.')
        previous = read_family(family_id, current) if current else None
        old_items = {i['preset']: i for i in previous['items']} if previous else {}
        if previous and not request.line_name.strip():
            request.line_name = previous['line_name']
        sources = {}
        for item in request.items:
            upload = uploads[item.preset]
            if upload:
                data = upload.file.read(12 * 1024 * 1024 + 1)
                if len(data) > 12 * 1024 * 1024:
                    raise HTTPException(422, f'{item.preset.title()} PNG exceeds 12 MB.')
                sources[item.preset] = (data, upload.filename)
            elif item.preset in old_items:
                old = old_items[item.preset]
                try:
                    sources[item.preset] = ((folder / 'revisions' / f'r{current:03d}' / old['source_file']).read_bytes(), old['source_filename'])
                except OSError as exc:
                    raise HTTPException(404, f'The saved {item.preset} source PNG is missing or unreadable. Upload a replacement.') from exc
            else:
                raise HTTPException(422, f'Upload an image for {item.preset}.')
        job_id = uuid.uuid4().hex
        pending = folder / 'revisions' / f'.pending-{job_id}'
        try:
            pending.mkdir(parents=True)
        except OSError as exc:
            raise HTTPException(507, 'Cannot create the family folder. Check disk space and permissions.') from exc
        # Retain only a bounded number of terminal job snapshots; families remain on disk.
        for old_id in list(_jobs):
            if len(_jobs) < 50:
                break
            if _jobs[old_id]['state'] in ['complete', 'failed']:
                del _jobs[old_id]
        _jobs[job_id] = {'job_id': job_id, 'state': 'queued', 'family_id': family_id, 'revision': current + 1, 'completed': 0, 'total': sum(len(i.variants) for i in request.items), 'current': ''}
        _executor.submit(process_batch, job_id, request, family_id, current + 1, pending, sources)
        return copy.deepcopy(_jobs[job_id])


@router.get('/{family_id}')
def get_family(family_id: str, revision: int | None = None):
    if revision is not None and revision < 1:
        raise HTTPException(422, 'Revision must be positive.')
    result = public_family(read_family(family_id, revision))
    result['revisions'] = sorted(int(p.name[1:]) for p in (family_dir(family_id) / 'revisions').iterdir() if re.fullmatch(r'r\d+', p.name) and p.is_dir())
    return result


@router.get('/{family_id}/revisions/{revision}/files/{filename}')
def get_file(family_id: str, revision: int, filename: str):
    manifest = read_family(family_id, revision)
    allowed = {output[kind] for item in manifest['items'] for output in item['outputs'] for kind in ['png', 'stl', 'json']}
    if filename not in allowed:
        raise HTTPException(404, 'Family file not found.')
    path = family_dir(family_id) / 'revisions' / f'r{revision:03d}' / filename
    if not path.is_file():
        raise HTTPException(404, 'Family file is missing from disk.')
    return FileResponse(path, filename=filename)
