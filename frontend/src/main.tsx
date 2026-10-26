import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Preview, type MeshData } from './Preview';
import './style.css';

const initial = { mode: 'cookie', tolerance: 30, size: 80, size_axis: 'width', red_height: 7, green_height: 5, backing: 1, frame_offset: 3, frame_height: 2, min_wall: 0.8, diameter: 40, length: 100, depth: 1, bore: 0, quality: 'standard', smoothing: 0.06, invert: false, seamless: false, proportions: false };
type Settings = typeof initial;
type Result = MeshData & { stl: string; segmented: string; warnings: string[]; stats: { triangles: number; size: number[]; bounds: number[][]; volume_mm3: number; watertight: boolean; manifold: boolean; components: number; dimensions: Record<string, number> } };
function App() {
  const [settings, setSettings] = useState<Settings>({ ...initial });
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [segmented, setSegmented] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [wireframe, setWireframe] = useState(false);
  const [grid, setGrid] = useState(true);
  const [ortho, setOrtho] = useState(false);
  const [action, setAction] = useState(0);
  const [name, setName] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => { if (!file) { setImageUrl(''); return; } const url = URL.createObjectURL(file); setImageUrl(url); return () => URL.revokeObjectURL(url); }, [file]);
  useEffect(() => () => abort.current?.abort(), []);
  function invalidate() { abort.current?.abort(); abort.current = null; setBusy(false); setResult(null); setSegmented(''); setError(''); }
  function update<K extends keyof Settings>(key: K, value: Settings[K]) { invalidate(); setSettings(s => ({ ...s, [key]: value })); }
  function choose(candidate?: File) { if (!candidate) return; invalidate(); if (!candidate.name.toLowerCase().endsWith('.png')) { setFile(null); setError('Choose a PNG file.'); return; } setFile(candidate); }
  function number(key: keyof Settings, label: string, min = 0.4, max = 500, step = 0.1) {
    return <label className="field" key={key}><span>{label}</span><div><input type="number" value={String(settings[key])} min={min} max={max} step={step} required onChange={e => update(key, e.target.value === '' ? NaN : Number(e.target.value))} /><span>{key === 'tolerance' ? 'RGB' : 'mm'}</span></div></label>;
  }
  async function generate(e: React.FormEvent) {
    e.preventDefault(); if (!file || busy) return;
    setError(''); setResult(null); setBusy(true);
    const controller = new AbortController(); abort.current = controller;
    try {
      const form = new FormData(); form.append('image', file); form.append('settings', JSON.stringify(settings));
      const response = await fetch('/api/generate', { method: 'POST', body: form, signal: controller.signal });
      const data = await response.json();
      if (controller.signal.aborted) return;
      setSegmented(data.segmented || '');
      if (!response.ok) throw new Error(data.error || 'Generation failed.');
      setResult(data);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Cannot reach backend. Check that the local server is running.'); }
    finally { if (abort.current === controller) { setBusy(false); abort.current = null; } }
  }
  function download() {
    if (!result) return;
    const bytes = Uint8Array.from(atob(result.stl), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'model/stl' }));
    const a = document.createElement('a'); a.href = url;
    a.download = `${name.trim().replace(/[^a-z0-9_-]/gi, '_') || `ShapeHappens_${settings.mode === 'cookie' ? 'CookieCutter' : 'TextureRoller'}`}.stl`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const cookie = settings.mode === 'cookie';
  return <><header><div><span className="brand-icon">S</span><div><h1>ShapeHappens <span>Generator</span></h1><p>From your artwork to a printable solid.</p></div></div><span className="local">● LOCAL WORKSPACE</span></header>
    <main><div className="intro"><div><p className="eyebrow">IMAGE → GEOMETRY → STL</p><h2>Make your next impression.</h2><p>Upload a drawing, set its dimensions, and inspect the actual printable mesh.</p></div><nav aria-label="Generator mode">{[['cookie', 'Cookie Cutter'], ['roller', 'Texture Roller']].map(([mode, label]) => <button key={mode} className={settings.mode === mode ? 'selected' : ''} onClick={() => { invalidate(); setSettings({ ...initial, mode }); setFile(null); if (input.current) input.current.value = ''; }}>{label}</button>)}</nav></div>
    <div className="workspace"><form className="panel controls" onSubmit={generate}><div className="section-title"><span>01</span><h3>Artwork & dimensions</h3></div>
      <div className="dropzone" role="button" tabIndex={0} onClick={() => input.current?.click()} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') input.current?.click(); }} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); choose(e.dataTransfer.files[0]); }}>
        <input ref={input} type="file" accept="image/png" hidden onChange={e => choose(e.target.files?.[0])} />
        {imageUrl ? <img src={imageUrl} alt="Uploaded artwork" /> : <><strong className="upload-icon">↑</strong><strong>Drop your PNG here</strong><span>or click to browse · up to 12 MB</span></>}
        {file && <span>{file.name} · Click to replace</span>}
      </div>
      <div className="legend">{(cookie ? [['#ff0000', 'Cutting wall'], ['#0000ff', 'Backing fill'], ['#00ff00', 'Embossed detail']] : [['#111111', 'Black: full depth'], ['#808080', 'Gray: partial depth'], ['#ffffff', 'White: no recess']]).map(([color, label]) => <span key={color}><i style={{ background: color }} />{label}</span>)}</div>
      <p className="hint">{cookie ? 'One closed red outer ring per image. White / transparent pixels are ignored. All internal details connect through a solid backing.' : 'Grayscale PNG: darker pixels recess deeper. White = 0 depth; black = the specified radial depth. Artwork wraps left to right around 360°. Transparent pixels act as white.'}</p>
      {number('tolerance', 'Colour tolerance', 0, 100, 1)}
      {cookie ? <><div className="subhead">Cutting outline size</div><label className="field"><span>Size by</span><select value={settings.size_axis} onChange={e => update('size_axis', e.target.value)}><option value="width">Width · aspect locked</option><option value="height">Height · aspect locked</option></select></label>{number('size', `Nominal ${settings.size_axis}`, 5, 500)}<p className="hint">Support flange extends beyond this size. The other dimension is calculated from the red outline.</p><div className="subhead">Extrusions & support</div>{number('red_height', 'Cutting wall height', 0.4, 50)}{number('green_height', 'Detail height', 0.4, 50)}{number('backing', 'Backing thickness', 0.4, 10)}{number('frame_offset', 'Frame outward offset', 0.4, 20)}{number('frame_height', 'Reverse frame height', 0.4, 20)}</> : <><div className="subhead">Cylinder dimensions</div>{number('diameter', 'Outer diameter', 8, 200)}{!settings.proportions && number('length', 'Roller length', 5, 500)}{number('depth', 'Radial recess depth', 0.1, 20)}{number('bore', 'Bore diameter · 0 = solid', 0, 180)}{number('smoothing', 'Surface smoothing · 0 = off', 0, 1, 0.01)}<label className="field"><span>Mesh quality</span><select value={settings.quality} onChange={e => update('quality', e.target.value)}><option value="draft">Draft · 0.4 mm cells</option><option value="standard">Standard · 0.12 mm cells</option><option value="fine">Fine · 0.08 mm cells</option></select></label>{[['proportions', 'Maintain pattern proportions (calculate length)'], ['invert', 'Invert grayscale depths'], ['seamless', 'Seamless mirror tiling']].map(([key, label]) => <label className="check" key={key}><input type="checkbox" checked={Boolean(settings[key as keyof Settings])} onChange={e => update(key as keyof Settings, e.target.checked)} />{label}</label>)}<p className="hint">Depth = radial recess depth × (255 − gray) / 255. Gray 128 uses about half depth. Bilinear sampling removes pixel steps. Smoothing (mm) reduces source noise; 0 preserves source texture. Fine uses 0.08 mm mesh cells and can produce large STLs.</p></>}
      {number('min_wall', 'Minimum printable feature', 0.4, 5)}
      <div className="form-actions"><button className="primary" type="submit" disabled={!file || busy}>{busy ? 'Building & validating…' : 'Generate 3D model →'}</button><button type="button" onClick={() => { invalidate(); setSettings({ ...initial, mode: settings.mode }); setFile(null); setName(''); if (input.current) input.current.value = ''; }}>Reset</button></div>
      {error && <div className="error" role="alert">{error}</div>}
      {segmented && <div className="segmented"><h4>{error ? 'Validation / highlighted image' : 'Interpreted colours'}</h4><img src={segmented} alt="Segmented artwork, magenta highlights validation problems" /><p className="hint">{error ? 'Magenta identifies invalid colours or detected problem regions.' : 'Palette validation passed. This interpretation was used for geometry.'}</p></div>}
    </form><section className="panel preview-panel"><div className="preview-heading"><div className="section-title"><span>02</span><h3>Model preview</h3></div><span className={result ? 'status ready' : 'status'}>{busy ? 'Generating…' : result ? 'Validated solid' : 'Awaiting artwork'}</span></div>
      <div className="viewport"><Preview data={result} wireframe={wireframe} grid={grid} orthographic={ortho} action={action} />{!result && <div className="empty"><span>◇</span><strong>{busy ? 'Constructing your geometry' : 'Your model starts here'}</strong><p>{busy ? 'Meshing, solid checks, and STL round-trip validation.' : 'Upload artwork and generate to explore it in 3D.'}</p></div>}</div>
      <div className="toolbar"><button onClick={() => setAction(x => x + 1)}>Reset camera</button><button onClick={() => setAction(x => x + 1)}>Fit model</button><select aria-label="Camera projection" value={ortho ? 'ortho' : 'perspective'} onChange={e => setOrtho(e.target.value === 'ortho')}><option value="perspective">Perspective</option><option value="ortho">Orthographic</option></select><label><input type="checkbox" checked={wireframe} onChange={e => setWireframe(e.target.checked)} />Wireframe</label><label><input type="checkbox" checked={grid} onChange={e => setGrid(e.target.checked)} />Grid & axes</label></div>
      <p className="navigation">Left drag: rotate <b>·</b> Scroll: zoom <b>·</b> Right drag: pan <b>·</b> Units: millimetres</p>
      {result && <><div className="metrics"><div><span>Bounding box · X × Y × Z</span><strong>{result.stats.size.map(v => v.toFixed(2)).join(' × ')} <small>mm</small></strong></div><div><span>Triangles</span><strong>{result.stats.triangles.toLocaleString()}</strong></div><div><span>Model volume</span><strong>{(result.stats.volume_mm3 / 1000).toFixed(2)} <small>cm³</small></strong></div></div><div className="integrity">✓ Watertight & manifold · one connected solid · STL reloaded and verified</div><details><summary>Physical dimensions & mesh precision</summary><dl>{Object.entries(result.stats.dimensions).map(([key, value]) => <React.Fragment key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value.toFixed(4)}</dd></React.Fragment>)}<dt>Bounds min</dt><dd>{result.stats.bounds[0].map(v => v.toFixed(3)).join(', ')}</dd><dt>Bounds max</dt><dd>{result.stats.bounds[1].map(v => v.toFixed(3)).join(', ')}</dd></dl></details>{result.warnings.length > 0 && <div className="warnings">{result.warnings.map(w => <p key={w}>△ {w}</p>)}</div>}<div className="download-row"><label><span>File name (optional)</span><input value={name} onChange={e => setName(e.target.value)} placeholder={`ShapeHappens_${cookie ? 'CookieCutter' : 'TextureRoller'}`} /></label><button className="primary" onClick={download}>↓ Download STL</button></div><p className="hint footer-note">Preview colours identify features only. STL contains the same solid geometry without colour. Print with a flat support side on the build plate.</p></>}
    </section></div><footer>ShapeHappens Generator <span>Local processing · Millimetre geometry · Real STL export</span></footer></main></>;
}
createRoot(document.getElementById('root')!).render(<App />);
