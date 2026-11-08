"""Explicit, versioned local archives. Inputs never supply filesystem paths."""
import hashlib
import io
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from .imaging.segment import InputError

LIBRARY_ROOT = Path(__file__).resolve().parents[1] / 'library'
PRESETS = {'standard': (40, 100, 1257, 1000), 'mini': (25, 70, 785, 700), 'extended': (30, 150, 942, 1500)}
_lock = threading.Lock()


class Identity(BaseModel):
    pattern_number: int = Field(1, ge=1, le=999999)
    title: str = Field('pattern', max_length=100)
    preset: str = Field('custom', pattern='^(standard|mini|extended|custom)$')


def slug(title):
    return re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60] or 'pattern'


def artwork_notes(data, settings, identity):
    if settings.mode != 'roller':
        return []
    notes = []
    with Image.open(io.BytesIO(data)) as image:
        if identity.preset in PRESETS:
            diameter, length, width, height = PRESETS[identity.preset]
            if settings.diameter != diameter or settings.length != length or settings.proportions:
                raise InputError('Preset dimensions must match the selected roller size. Choose Custom for other dimensions or proportional sizing.')
            if image.size != (width, height):
                notes.append(f'{identity.preset.title()} artwork should be {width} × {height} px; uploaded {image.width} × {image.height}. The full image maps to the selected cylinder; no resizing or cropping of the source file is performed.')
        if image.mode != 'L' or 'transparency' in image.info:
            notes.append('Project artwork specification requires an 8-bit grayscale L PNG without transparency. This input is accepted by the general importer but does not meet that file-format specification.')
    return notes


def file_stem(settings, identity, dimensions, revision):
    def num(value):
        return f'{value:g}'.replace('.', 'p')
    prefix = f'P{identity.pattern_number:04d}_{slug(identity.title)}'
    if settings.mode == 'roller':
        shape = f'ROLLER_{identity.preset.upper()}_L{num(dimensions["length"])}_D{num(settings.diameter)}_DEP{num(settings.depth)}_B{num(settings.bore)}'
    else:
        shape = f'CUTTER_{settings.size_axis.upper()}{num(settings.size)}'
    return f'{prefix}_{shape}_r{revision:03d}'


def archive(data, stl, settings, identity, stats, warnings, source_filename=None):
    """Publish complete revisions under a lock; never overwrite an existing one."""
    with _lock:
        folder = LIBRARY_ROOT / ('rollers' if settings.mode == 'roller' else 'cutters') / f'P{identity.pattern_number:04d}' / (identity.preset if settings.mode == 'roller' else 'cookie')
        folder.mkdir(parents=True, exist_ok=True)
        revision = max([int(p.name[1:]) for p in folder.iterdir() if p.is_dir() and re.fullmatch(r'r\d+', p.name)] or [0]) + 1
        while (folder / f'r{revision:03d}').exists():
            revision += 1
        final = folder / f'r{revision:03d}'
        temporary = folder / f'.pending-{uuid.uuid4().hex}'
        temporary.mkdir()
        stem = file_stem(settings, identity, stats['dimensions'], revision)
        try:
            (temporary / f'{stem}_source.png').write_bytes(data)
            (temporary / f'{stem}.stl').write_bytes(stl)
            metadata = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'source_filename': source_filename, 'identity': identity.model_dump(), 'settings': settings.model_dump(), 'stats': stats, 'warnings': warnings, 'source_sha256': hashlib.sha256(data).hexdigest(), 'stl_sha256': hashlib.sha256(stl).hexdigest()}
            (temporary / f'{stem}.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            temporary.rename(final)
        except Exception:
            shutil.rmtree(temporary)
            raise
        return {'filename': f'{stem}.stl', 'saved_to': str(final), 'revision': revision}
