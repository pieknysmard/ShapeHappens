# Roller workflow and local library

The current Texture Roller UI uses [roller families](ROLLER_FAMILIES.md) and the
`A00001-SH` naming convention. This document describes the previous single-roller
workflow and legacy `/api/generate` archive. Existing files are preserved.

Texture Roller is the initial UI and API mode. Cookie Cutter remains available.

| Preset | Length × diameter | Source PNG width × height |
| --- | --- | --- |
| Standard | 100 × 40 mm | 1257 × 1000 px |
| Mini | 70 × 25 mm | 785 × 700 px |
| Extended | 150 × 30 mm | 942 × 1500 px |

Selecting a preset sets exact physical dimensions and disables image-ratio length calculation. Changing a dimension or enabling ratio calculation selects Custom. All three artwork sizes use approximately 10 px/mm. Author maps for the physical length × circumference (π × diameter), with horizontal wrapping. Rounded PNG widths are intentional; preset sizing keeps the physical dimensions exact rather than deriving a slightly different length from the rounded pixel ratio.

Rollers are solid by default. Enable “Through-hole for handle rod” to make an axial bore, initially 8 mm. The diameter can be changed. Turning the hole off sets the actual geometric bore to zero; turning it back on retains the edited diameter. Reset restores 8 mm for the next enabled hole. The bore and deepest recess must leave at least the configured minimum wall. A rod's nominal diameter and printable fit clearance are separate choices; the entered value is the modeled hole diameter.

## Pattern identity and filenames

Assign a stable pattern number to a design, starting at P0001. Reuse that number for all sizes of the same design; use a new number for a different design. Enter a short title, such as “wildflowers”. The app does not automatically allocate IDs or prevent you from reusing an ID for a different title. Pattern number and title are explicit form fields. The source filename is used as the title when the title field is blank.

Example saved STL:

`P0001_wildflowers_ROLLER_MINI_L70_D25_DEP1_B8_r001.stl`

- P0001: stable design identifier (at least four digits).
- MINI: preset; STANDARD, EXTENDED and CUSTOM are also supported.
- L70 / D25: actual roller length / outer diameter in mm.
- DEP1: maximum radial recess depth in mm.
- B8: axial bore diameter; B0 means solid.
- r001: saved revision. Decimal numbers use `p`, e.g. DEP1p5.

Download names come from the generated result, so editing settings or identity clears the previous result before another export. Unsaved results use r000 and have no reserved library revision. Saved revisions are allocated per pattern, generator and preset, across all titles and parameter combinations in that folder. Changing a title does not reset the revision sequence.

## Storage

“Save PNG, STL & settings to local library” is enabled initially in the UI. Successful generation creates:

```text
ShapeHappens/library/rollers/P0001/mini/r001/
  P0001_wildflowers_ROLLER_MINI_L70_D25_DEP1_B8_r001_source.png
  P0001_wildflowers_ROLLER_MINI_L70_D25_DEP1_B8_r001.stl
  P0001_wildflowers_ROLLER_MINI_L70_D25_DEP1_B8_r001.json
```

The PNG is the original upload, byte for byte, even when the general importer accepts a noncompliant format. The STL is the exact verified file displayed and downloaded. JSON records UTC save time, identity, complete settings, mesh statistics, warnings and SHA-256 hashes of both files. A complete revision is published together; existing revisions are never overwritten. Generation requests in one server process are serialized only for revision allocation and archive writing. Run one local server instance for this library.

Cookie cutter archives use `library/cutters/P0001/cookie/r001/`. The library is ignored by Git; back up this entire folder to your chosen backup storage. Do not keep the only copy in Downloads. Failed geometry is never archived. If disk storage fails, the app still offers the generated STL for download and shows a warning. API callers must explicitly send `save=true`; the API itself does not save by default.

Before changing a design, create a new revision. Keep prior revisions to reproduce earlier orders. Use the same ID when separately composing Standard, Mini and Extended artwork; do not resize one design into all three without adapting composition.

## Compatibility with Texture Roller Depth.txt

The uploaded document is artwork-generation guidance, not instructions to execute during installation or application development. Its request to output only one PNG applies to artwork creation, not this application change or its report.

Compatible: PNG dimensions all fit the 8–2048 px importer limits; 8-bit L PNG is supported; white 255 is zero recess, black 0 is maximum recess and gray maps linearly; X wraps and Y clamps; bore/handles must not be drawn in the depth map. The generator has a real optional through-bore; it does not generate separate shafts or handles.

Corrections and qualifications:

1. Mini is confirmed at 70 mm length × 25 mm diameter with 785 × 700 px artwork. This matches the uploaded document. Standard and Extended also match.
2. Keep Invert and Mirror tiling off for compliant artwork. Mirror tiling creates a reflected repetition and cannot repair the original composition. Presets keep ratio sizing off. Surface smoothing is 0.06 mm by default and changes transitions; choose zero for greatest source fidelity, while bilinear resampling and downsampling antialiasing still apply.
3. The general importer remains permissive: it also accepts neutral RGB and alpha inputs. The new advisory warns when a roller upload is not an 8-bit L PNG without transparency, or its dimensions differ from the selected preset. A warning is not project artwork certification; the app does not silently rewrite the PNG.
4. A closed, valid STL does not certify seamless artwork. The existing first/last-column comparison is only diagnostic: different adjacent periodic samples can be correct, and identical edge columns do not prove contour or gradient continuity. The warning now explains this. Repeated-tile visual review remains necessary.
5. Full-height coverage, complete motifs, intentional physical gradients, source anatomy and absence of lighting artifacts cannot be reliably certified by mesh checks. The document's visual review requirements remain necessary before uploading.
6. The app's minimum-feature warning is advisory. It does not thicken roller details or impose an invented artwork feature threshold. The minimum wall below a bore/recess is a separate structural constraint enforced by the generator.
7. The surface-vertex budget is now 2.25 million so Extended at Fine quality fits (2,211,804 outer surface vertices). Larger custom jobs still fail explicitly rather than being silently coarsened. Fine STLs are large; keep revision storage capacity in mind.

An amended copy of the artwork instructions is supplied separately. The original user file is preserved.
