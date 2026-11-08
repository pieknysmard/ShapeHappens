import { useEffect, useRef, useState } from 'react';
import { Preview, type MeshData } from './Preview';

const sizes = {
  standard: { code: 'S', label: 'Standard', diameter: 40, length: 100, pixels: '1257 × 1000' },
  mini: { code: 'M', label: 'Mini', diameter: 25, length: 70, pixels: '785 × 700' },
  extended: { code: 'E', label: 'Extended', diameter: 30, length: 150, pixels: '942 × 1500' },
};
type Size = keyof typeof sizes;
type Parameters = { mode: 'roller'; diameter: number; length: number; bore: number; depth: number; quality: string; smoothing: number; min_wall: number; tolerance: number; invert: boolean; seamless: boolean; proportions: boolean };
type Slot = { enabled: boolean; file: File | null; sourceUrl: string; sourceName: string; settings: Parameters; holeDiameter: number; full: boolean; hole: boolean };
type Output = { body: 'H' | 'F'; prefix: string; stl_url: string; png_url: string; json_url: string; stl: string; stats: { triangles: number; size: number[] }; warnings: string[] };
type Member = { preset: Size; source_url: string; source_filename: string; settings: Parameters; hole_diameter: number; variants: string[]; outputs: Output[] };
type Family = { id: string; line: string; line_name: string; number: number; title: string; revision: number; revisions?: number[]; items: Member[] };
type Summary = { id: string; line_name: string; title: string; revision: number; sizes: string[] };
type Job = { job_id: string; family_id: string; state: string; completed: number; total: number; current: string; error?: string; saved_to?: string; family?: Family };
function defaults(): Record<Size, Slot> {
  return Object.fromEntries(Object.entries(sizes).map(([key, size]) => [key, { enabled: false, file: null, sourceUrl: '', sourceName: '', holeDiameter: 8, full: true, hole: false, settings: { mode: 'roller', diameter: size.diameter, length: size.length, bore: 0, depth: 1, quality: 'standard', smoothing: .06, min_wall: .8, tolerance: 30, invert: false, seamless: false, proportions: false } }])) as Record<Size, Slot>;
}
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : data.error || JSON.stringify(data.detail) || 'Request failed.'), { status: response.status });
  return data;
}

function Artwork({ slot, preset, onChange }: { slot: Slot; preset: Size; onChange: (file: File) => void }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!slot.file) { setUrl(slot.sourceUrl); return; }
    const objectUrl = URL.createObjectURL(slot.file); setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [slot.file, slot.sourceUrl]);
  return <><label className="family-upload"><span>{slot.sourceName || `Choose ${sizes[preset].label} PNG`}</span><input aria-label={`${sizes[preset].label} artwork`} type="file" accept="image/png" onChange={e => { if (e.target.files?.[0]) onChange(e.target.files[0]); }} /></label>{url && <img className="family-artwork" src={url} alt={`${sizes[preset].label} source artwork`} />}</>;
}

export function Families() {
  const [slots, setSlots] = useState(defaults);
  const [line, setLine] = useState('A');
  const [lineName, setLineName] = useState('');
  const [number, setNumber] = useState('');
  const [title, setTitle] = useState('');
  const [families, setFamilies] = useState<Summary[]>([]);
  const [filter, setFilter] = useState('');
  const [saved, setSaved] = useState<Family | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(() => localStorage.getItem('shapehappens-family-job'));
  const [job, setJob] = useState<Job | null>(null);
  const [preview, setPreview] = useState<MeshData | null>(null);
  const [previewLabel, setPreviewLabel] = useState('');
  const [previewBusy, setPreviewBusy] = useState(false);
  const previewRequest = useRef<AbortController | null>(null);
  const activeLoad = useRef(0);
  const busy = submitting || loading || Boolean(jobId);
  const oldRevision = saved && saved.revision !== Math.max(...(saved.revisions || [saved.revision]));

  async function refresh() {
    try { setFamilies((await api<{ families: Summary[] }>('/api/families')).families); }
    catch (e) { setError(String(e instanceof Error ? e.message : e)); }
  }
  function clearPreview() { previewRequest.current?.abort(); setPreview(null); setPreviewLabel(''); setPreviewBusy(false); }
  async function openFamily(id: string, revision?: number) {
    const serial = ++activeLoad.current;
    setLoading(true); setError(''); clearPreview();
    try {
      const family = await api<Family>(`/api/families/${id}${revision ? `?revision=${revision}` : ''}`);
      if (serial !== activeLoad.current) return;
      const next = defaults();
      for (const item of family.items) next[item.preset] = { enabled: true, file: null, sourceUrl: item.source_url, sourceName: item.source_filename, settings: item.settings, holeDiameter: item.hole_diameter, full: item.variants.includes('F'), hole: item.variants.includes('H') };
      setSlots(next); setLine(family.line); setLineName(family.line_name); setNumber(String(family.number)); setTitle(family.title); setSaved(family); setDirty(false);
    } catch (e) { if (serial === activeLoad.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (serial === activeLoad.current) setLoading(false); }
  }
  useEffect(() => { void refresh(); return () => { activeLoad.current++; previewRequest.current?.abort(); }; }, []);
  useEffect(() => {
    if (!jobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await api<Job>(`/api/families/jobs/${jobId}`);
        if (disposed) return;
        setJob(state);
        if (state.state === 'complete' || state.state === 'failed') {
          localStorage.removeItem('shapehappens-family-job'); setJobId(null);
          if (state.state === 'failed') setError(state.error || 'Batch failed. No new revision was published.');
          else { await openFamily(state.family_id); await refresh(); }
        } else timer = setTimeout(poll, 1000);
      } catch (e) {
        if (disposed) return;
        if (e instanceof Error && 'status' in e && e.status === 404) {
          localStorage.removeItem('shapehappens-family-job'); setJobId(null);
          setError('This job is no longer available after a server restart. Refresh the library and reopen the last completed family revision.');
          await refresh(); return;
        }
        // Keep the job ID on transient network failures so polling can resume.
        setError(e instanceof Error ? e.message : String(e));
        timer = setTimeout(poll, 4000);
      }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId]);

  function change(preset: Size, values: Partial<Slot>) { clearPreview(); setDirty(true); setSlots(previous => ({ ...previous, [preset]: { ...previous[preset], ...values } })); }
  function parameter(preset: Size, key: keyof Parameters, value: number | string | boolean) { change(preset, { settings: { ...slots[preset].settings, [key]: value } }); }
  function numeric(preset: Size, key: keyof Parameters, label: string, min: number, max: number, step = .1) {
    return <label className="field"><span>{label}</span><input aria-label={`${sizes[preset].label} ${label}`} type="number" required min={min} max={max} step={step} value={Number.isFinite(slots[preset].settings[key]) ? String(slots[preset].settings[key]) : ''} onChange={e => parameter(preset, key, e.target.value === '' ? NaN : Number(e.target.value))} /></label>;
  }
  function newFamily() { activeLoad.current++; clearPreview(); setSlots(defaults()); setSaved(null); setNumber(''); setTitle(''); setJob(null); setError(''); setDirty(false); }
  async function generate(event: React.FormEvent) {
    event.preventDefault(); setError(''); clearPreview();
    const selected = (Object.keys(sizes) as Size[]).filter(p => slots[p].enabled);
    if (!selected.length) { setError('Choose at least one roller image.'); return; }
    for (const preset of selected) {
      if (!slots[preset].file && !slots[preset].sourceUrl) { setError(`Choose the ${sizes[preset].label} PNG.`); return; }
      if (!slots[preset].full && !slots[preset].hole) { setError(`Choose Solid F, Hole H, or both for ${sizes[preset].label}.`); return; }
    }
    setSubmitting(true); setJob(null);
    try {
      const form = new FormData();
      form.append('config', JSON.stringify({ line, line_name: lineName, number: number ? Number(number) : null, title, base_revision: saved?.revision || null, items: selected.map(preset => ({ preset, settings: slots[preset].settings, hole_diameter: slots[preset].holeDiameter, variants: [...(slots[preset].full ? ['F'] : []), ...(slots[preset].hole ? ['H'] : [])] })) }));
      for (const preset of selected) if (slots[preset].file) form.append(preset, slots[preset].file!);
      const state = await api<Job>('/api/families/batch', { method: 'POST', body: form });
      localStorage.setItem('shapehappens-family-job', state.job_id); setJob(state); setJobId(state.job_id);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSubmitting(false); }
  }
  async function showPreview(output: Output) {
    clearPreview(); const controller = new AbortController(); previewRequest.current = controller;
    setPreviewBusy(true); setPreviewLabel(`${output.prefix} · saved revision ${saved?.revision}`);
    try {
      const response = await fetch(output.stl_url, { signal: controller.signal });
      if (!response.ok) throw new Error('Saved STL could not be loaded.');
      const blob = await response.blob();
      const base64 = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('STL read failed.')); reader.readAsDataURL(blob); });
      if (!controller.signal.aborted) setPreview({ stl: base64, preview_mode: 'roller' });
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (!controller.signal.aborted) setPreviewBusy(false); }
  }

  return <section className="family-workspace">
    <div className="family-heading"><div><h2>Roller families</h2><p>Upload separate artwork for each size, generate one batch, then reopen any saved family to adjust it.</p></div><button disabled={busy} onClick={newFamily}>New family</button></div>
    <div className="family-layout"><aside className="panel family-library"><h3>Saved families</h3><input aria-label="Search families" placeholder="Search ID, line or title" value={filter} onChange={e => setFilter(e.target.value)} /><button onClick={() => void refresh()}>Refresh library</button>
      {!families.length && <p className="hint">Completed families will appear here. Previous single-roller archives remain in library/.</p>}
      {families.filter(f => `${f.id} ${f.line_name} ${f.title}`.toLowerCase().includes(filter.toLowerCase())).map(f => <button disabled={busy} className={saved?.id === f.id ? 'family-entry selected' : 'family-entry'} key={f.id} onClick={() => void openFamily(f.id)}><strong>{f.id} {f.title}</strong><span>{f.line_name || 'Unlabelled line'} · revision {f.revision}</span><span>{f.sizes.map(p => sizes[p as Size].label).join(' · ')}</span></button>)}
    </aside><div>
      {job && <div className="panel family-progress" role="status"><strong>{job.family_id}: {job.state} · {job.completed}/{job.total} models</strong><progress max={job.total} value={job.completed} /><span>{job.current || (job.state === 'complete' ? 'All PNGs, STLs and settings saved.' : 'One batch processes at a time to keep memory use predictable.')}</span></div>}
      {jobId && error && <button onClick={() => { localStorage.removeItem('shapehappens-family-job'); setJobId(null); setJob(null); void refresh(); }}>Stop following job and refresh library</button>}
      {error && <div className="error" role="alert">{error}</div>}
      {saved && <div className="panel family-loaded"><strong>{saved.id} · {dirty ? 'Unsaved changes' : 'Saved family'}</strong><label>Revision <select disabled={busy} aria-label="Family revision" value={saved.revision} onChange={e => void openFamily(saved.id, Number(e.target.value))}>{(saved.revisions || [saved.revision]).map(r => <option key={r} value={r}>{r}</option>)}</select></label>{oldRevision && <p>Older revisions are read-only. Open the latest revision to save adjustments.</p>}</div>}
      <form onSubmit={generate}><fieldset disabled={busy || Boolean(oldRevision)} className="family-fieldset">
        <div className="panel family-identity"><label>Line letter<select aria-label="Line letter" disabled={Boolean(saved)} value={line} onChange={e => { setLine(e.target.value); setLineName(families.find(f => f.id.startsWith(e.target.value) && f.line_name)?.line_name || ''); setDirty(true); }}>{'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(letter => <option key={letter}>{letter}</option>)}</select></label><label>Line name<input aria-label="Line name" value={lineName} maxLength={80} placeholder="e.g. Botanical" onChange={e => { setLineName(e.target.value); setDirty(true); }} /></label><label>Family number<input aria-label="Family number" disabled={Boolean(saved)} type="number" min={1} max={99999} step={1} value={number} placeholder="Automatic" onChange={e => setNumber(e.target.value)} /></label><label>Family title<input aria-label="Family title" value={title} maxLength={100} placeholder="e.g. Wildflowers" onChange={e => { setTitle(e.target.value); setDirty(true); }} /></label><p className="hint">{line}{number ? number.padStart(5, '0') : '#####'}-SF = Standard solid; -SH = Standard with hole. M = Mini, E = Extended. Original names follow the prefix. Family numbers are allocated within each line.</p></div>
        <div className="family-cards">{(Object.keys(sizes) as Size[]).map(preset => { const slot = slots[preset], size = sizes[preset]; return <section className="panel family-card" key={preset}><label className="family-card-heading"><input aria-label={`Include ${size.label}`} type="checkbox" checked={slot.enabled} onChange={e => change(preset, { enabled: e.target.checked })} /><strong>{size.label}</strong><span>{size.code}</span></label><p>{size.length} × Ø{size.diameter} mm · {size.pixels} px</p>
          <Artwork preset={preset} slot={slot} onChange={file => { if (!file.name.toLowerCase().endsWith('.png')) { setError('Choose a PNG file.'); return; } change(preset, { file, enabled: true, sourceName: file.name }); }} />
          <fieldset disabled={!slot.enabled} className="family-fieldset">{numeric(preset, 'depth', 'Recess depth (mm)', .1, 20)}<label className="field"><span>Mesh quality</span><select aria-label={`${size.label} mesh quality`} value={slot.settings.quality} onChange={e => parameter(preset, 'quality', e.target.value)}><option value="draft">Draft · 0.4 mm</option><option value="standard">Standard · 0.12 mm</option><option value="fine">Fine · 0.08 mm</option></select></label>
          <div className="body-options"><label><input aria-label={`${size.label} solid F`} type="checkbox" checked={slot.full} onChange={e => change(preset, { full: e.target.checked })} />Solid · F</label><label><input aria-label={`${size.label} hole H`} type="checkbox" checked={slot.hole} onChange={e => change(preset, { hole: e.target.checked })} />Hole · H</label></div>
          <label className="field"><span>Hole diameter (mm)</span><input aria-label={`${size.label} hole diameter`} type="number" disabled={!slot.hole} required min={.1} max={180} step={.1} value={Number.isFinite(slot.holeDiameter) ? slot.holeDiameter : ''} onChange={e => change(preset, { holeDiameter: e.target.value === '' ? NaN : Number(e.target.value) })} /></label>
          <details><summary>Surface & validation settings</summary>{numeric(preset, 'smoothing', 'Smoothing (mm)', 0, 1, .01)}{numeric(preset, 'min_wall', 'Minimum wall (mm)', .4, 5)}{numeric(preset, 'tolerance', 'Colour tolerance', 0, 100, 1)}<label className="check"><input type="checkbox" checked={slot.settings.invert} onChange={e => parameter(preset, 'invert', e.target.checked)} />Invert depth</label><label className="check"><input type="checkbox" checked={slot.settings.seamless} onChange={e => parameter(preset, 'seamless', e.target.checked)} />Mirror tiling (changes artwork)</label></details></fieldset>
        </section>; })}</div>
        <div className="family-submit"><button className="primary" type="submit">{busy ? 'Generating family…' : saved ? 'Generate & save new revision' : 'Generate & save family'}</button><p className="hint">One action generates every selected size/body combination. Each completed batch is saved inside roller-families/. Earlier revisions stay intact. A failed batch publishes no partial revision.</p></div>
      </fieldset></form>
      {saved && <section className="panel family-results"><h3>Saved files · {saved.id} / r{String(saved.revision).padStart(3, '0')}</h3><p className="hint">Folder: roller-families/{saved.line}/{saved.id}/revisions/r{String(saved.revision).padStart(3, '0')}/</p>{saved.items.flatMap(item => item.outputs.map(output => <div className="family-output" key={output.prefix}><strong>{output.prefix}</strong><span>{output.stl}</span><a href={output.png_url} download>PNG</a><a href={output.stl_url} download>STL</a><a href={output.json_url} download>Settings</a><button disabled={previewBusy} onClick={() => void showPreview(output)}>Preview</button>{output.warnings.length > 0 && <details><summary>{output.warnings.length} advisories</summary>{output.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details>}</div>))}</section>}
      {(preview || previewBusy) && <section className="panel family-preview"><h3>{previewLabel}</h3>{previewBusy && <p>Loading saved STL…</p>}<div className="viewport"><Preview data={preview} grid wireframe={false} orthographic={false} action={0} /></div></section>}
    </div></div>
  </section>;
}
