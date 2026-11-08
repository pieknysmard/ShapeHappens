# Roller families: batch generation, naming and storage

The Texture Roller tab is now a family workspace. A family can include any of Standard, Mini and Extended, each with its own PNG and settings. Choose Solid F, Hole H, or both for each included size. One Generate action submits the entire batch and saves the result. Cookie Cutter remains available separately.

| Size | Code | Length × diameter | Artwork width × height |
| --- | --- | --- | --- |
| Standard | S | 100 × 40 mm | 1257 × 1000 px |
| Mini | M | 70 × 25 mm | 785 × 700 px |
| Extended | E | 150 × 30 mm | 942 × 1500 px |

## Naming convention

`A00001-SH_original-name.stl`

- A: one chosen uppercase letter identifying the roller line. Give it a label such as Botanical, Christmas or Geometric. Letters are user-assigned; no category mapping is imposed. A is the initial selection. Once named, a line keeps that category across its saved families; use another letter for another line.
- 00001: exactly five digits, the family order number within that line. Leave Family number blank for automatic allocation, or enter an unused number from 1 to 99999.
- S / M / E: Standard / Mini / Extended.
- H / F: through-hole / full solid body. The actual hole diameter is stored in settings; H alone does not encode it.
- Original name: the uploaded filename stem, with unsupported filename punctuation converted to underscores. Existing family prefixes are removed before applying the current one; very long stems are shortened.

Examples for one family: `A00001-SF_roses.png`, `A00001-SF_roses.stl`, `A00001-SH_roses.png`, `A00001-SH_roses.stl`, `A00001-MF_small-roses.stl`, `A00001-EH_tall-roses.stl`.

Each generated PNG/STL/settings-JSON triplet has the same stem. If both F and H are selected, both triplets include their own byte-for-byte copy of the same uploaded PNG. The app never invents a hole in the artwork. Rollers default to solid; H enables an editable 8 mm bore initially. Settings enforce the remaining wall below the deepest recess.

## Saved folders

```text
ShapeHappens/
  roller-families/
    A/
      A00001/
        revisions/
          r001/
            family.json
            A00001-SF_roses.png
            A00001-SF_roses.stl
            A00001-SF_roses.json
            A00001-SH_roses.png
            A00001-SH_roses.stl
            A00001-SH_roses.json
            A00001-MF_small-roses.png
            A00001-MF_small-roses.stl
            A00001-MF_small-roses.json
          r002/
            ...
```

Revision numbers live in folders so your required filename prefix stays unchanged. `family.json` is an internal family index, not a roller asset: it records family identity, source filenames, per-size settings, selected variants, statistics and warnings. Each prefixed JSON records exact generation settings and SHA-256 hashes of the PNG and verified STL.

This is a separate folder inside the local repository checkout. Generated binary files are excluded from Git, as the earlier library was; they are not automatically uploaded to GitHub. Back up `roller-families/` to retain images, meshes and revision history on another device. Keep the full family folder intact. Existing `library/` single-roller archives are preserved; no line or family IDs are guessed for those older files.

## Reopen and adjust

1. Upload a separate PNG to each required size card. Uploading selects that card; uncheck a card to omit it.
2. Choose a line letter and line label, optionally a family number, and a title.
3. Set recess depth, quality, F/H variants and hole diameter per size. Advanced controls retain smoothing, tolerance, minimum wall, inversion and mirror tiling.
4. Generate & save family. Progress shows completed model count. The batch builds models sequentially in the background to bound geometry memory; a single click still creates the whole selected family.
5. Use Saved families to search by ID, title or line name. Opening a family restores its PNGs and settings from disk, without requiring re-upload.
6. Change settings or replace selected PNGs and Generate & save new revision. Previous revisions remain intact. The revision selector lets you inspect and download earlier outputs; open the latest revision before editing.
7. Each saved model has PNG, STL and Settings download links and a Preview button. Preview loads that exact saved STL, one model at a time.

All selected models must pass geometry and STL-reload validation before a new revision is published. A failure removes temporary batch files and preserves previous revisions. Failed new-family attempts can leave gaps in automatic numbering. The app prevents two active updates to the same family and rejects saving against a stale revision. Up to three batches can be queued; one is processed at a time. Use one local server process for this library.

The browser can resume following a batch after a refresh. Completed families remain retrievable after server restarts. If the server is interrupted during a batch, the last completed revision stays valid; an unpublished `.pending-*` directory may remain and is not shown as a saved family.

## Artwork instruction compatibility

Your depth-map instructions remain compatible with the physical presets: white is zero recess, black is maximum recess, X wraps, Y does not. Preserve the original PNG for each separately composed size. The app warns about preset PNG dimensions and non-L/non-8-bit grayscale formats, but a valid mesh does not certify motif completeness, true depth semantics or a seamless composition. Keep inversion and mirror tiling off for compliant source artwork unless deliberately requested. PNG/STL pairs share the requested family prefix; manufacturing parameters and revisions are recorded in JSON and folders.

API: `POST /api/families/batch` accepts a JSON `config` multipart field and optional `standard`, `mini`, `extended` PNG uploads; it returns a job ID with HTTP 202. Poll `/api/families/jobs/{job_id}`. `GET /api/families` lists saved families; `GET /api/families/A00001` restores the latest revision, or use `?revision=1`. Saved files are served only when listed in that revision's manifest.
