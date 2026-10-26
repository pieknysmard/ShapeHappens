# ShapeHappens Generator

A local React / TypeScript / Three.js application backed by FastAPI, OpenCV,
Pillow, Shapely, Trimesh and Manifold3D. Converts PNG artwork to millimetre STL
geometry. No accounts or hosted services. Uploaded artwork stays in memory on
the local server; generated files are downloaded directly by the browser.

## Windows setup

Install Python **3.11–3.13** (with pip and the Python launcher) and Node.js
**20.19+** (with npm). Open PowerShell in this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Or double-click `setup.cmd`, then `start.cmd`. Open **http://127.0.0.1:8000**.
The first setup downloads dependencies; subsequent starts work offline.
The server stays in the terminal; press Ctrl+C to stop it. It binds only to
the local computer. No global execution-policy change is required.

To choose an installed Python or pnpm:

```powershell
.\setup.ps1 -Python 'C:\Path\To\python.exe' -PackageManager pnpm
```

For frontend development, run the backend with `start.ps1`, and in another
terminal run `npm run dev` in `frontend`; Vite proxies `/api` to port 8000.
After changing frontend code run `npm run build` and restart the backend.

## Cookie cutter

Upload a PNG with exactly one connected, closed **red (#FF0000) ring**.
Use **blue (#0000FF)** inside the ring, **green (#00FF00)** for embossed
details, and white or transparent pixels outside. Green islands and enclosed
green loops are supported. White interior areas still receive a backing;
the backing fills the entire red outer contour by design.

Set nominal cutting width or height; aspect ratio is locked. Padding around
the artwork is excluded. The support flange adds to the nominal dimensions.
By default red reaches **Z=+7**, green reaches **Z=+5**, the backing fills
**Z=-1…0**, and the outward **3 mm** flange fills **Z=-2…0**. These six
parameters, including the **0.8 mm** minimum red wall, are adjustable.
Thinner red ink is thickened inward; thicker ink is preserved. All components
are joined with a real solid boolean union. Green is never automatically
thickened or discarded; small-feature warnings are advisory.

Open rings are rejected. The validation image highlights candidate gaps
identified by diagnostic morphological closing (never used for geometry).
If no local gap can be identified, it marks interior-colour pixels reachable
from the exterior in magenta. Large gaps without interior colour may have no
localized highlight. Multiple outer rings, multiple
enclosed red regions, red self-touching boundaries, and green/blue outside
the ring are rejected with an explanation. A red band with a local gap that
still contains a continuous closed path is considered closed.

## Texture roller

Upload a grayscale PNG (black/white artwork remains supported). **White stays
at the outer radius; black recesses by the full radial recess depth; gray
recesses proportionally** (default diameter 40 mm, length 100 mm, depth 1 mm).
For an 8-bit gray value `g`, depth = `recess_depth × (255 - g) / 255`.
For example, at 2 mm maximum depth, black is 2 mm deep, gray 128 is about
0.996 mm deep, and white is 0 mm deep. Gray values are mapped linearly without
gamma correction or a black/white threshold. Both grayscale and RGB PNGs with
equal channels are supported. Inversion reverses this depth scale.
Horizontal image position maps around 360°, vertical position maps along Z.
There are closed end caps and optionally a through-bore. The minimum material
below a recess is checked against the configured minimum wall.

The pattern is a periodic, triangulated radial height field, **not a texture
or colour effect**. Bilinear interpolation reconstructs intermediate heights
between image pixels, removing nearest-pixel terraces. Gaussian filtering in
physical millimetres reduces source noise (Surface smoothing, default **0.06 mm
sigma**, adjustable **0–1 mm**). Set smoothing to 0 for exact source texture;
antialias filtering is still applied when downsampling to prevent skipped-pixel
noise. Uniform black and white regions keep their full/zero-depth values;
smoothing and interpolation blend boundaries and isolated pixels.

Quality selects maximum surface-cell spacing: **Draft 0.4 mm**, **Standard
0.12 mm**, **Fine 0.08 mm**, in both axial and circumferential directions.
A default 40 × 100 mm Fine roller has approximately **3.93 million triangles**
and a **197 MB binary STL**. Meshing is vectorized for these larger models.
The preview loads the exact binary STL instead of a duplicate JSON triangle
array; shading is neutral to reveal actual surface geometry.

The local limit is 2.2 million surface vertices. Jobs exceeding it are rejected
with an explanation; resolution is never silently coarsened. Effective mesh
spacing, smoothing, and source pixel dimensions in mm are displayed. Small
features remain limited by source resolution, depth-map quality and FDM printing.
Interpreting a rendered image as a depth map also engraves its shadows and
highlights; this generator does not infer an object's true 3D shape from lighting.

Left/right seam vertices share topology. A mismatched image seam produces
a warning and a physical transition, never an open mesh. **Seamless mirror
tiling** wraps the original plus its horizontal reflection, making both
seams continuous while changing the pattern repetition. The proportions
option calculates length = circumference × image height / wrapped image
width; mirror tiling doubles wrapped width. Inversion reverses grayscale depths.
The bore is disabled at diameter 0; positive values create a real hole.

## Preview and export

Generate after each image or parameter change. The prior result is cleared so
an old STL cannot accidentally be downloaded with new settings. The rotatable
preview uses the **triangles from the reloaded STL**; Download STL saves those
same bytes. Left drag rotates, right drag pans, wheel zooms. Camera reset,
fit, projection, wireframe, grid and axes are implemented.

Cookie preview colours are red (wall), green (details), blue (backing) and
gold (reverse flange). Colours classify visible faces of the united solid;
buried joining surfaces do not exist in the final mesh. Rollers use neutral
shading to expose actual relief. Standard STL has no colours or unit metadata;
import into a slicer as **millimetres**. Final dimensions, bounds, triangle
count, volume and integrity checks are displayed before download.

Each model must be watertight, consistently wound, positive-volume and a
single connected body, with no degenerate triangles. The binary STL is loaded
back, checked again, and compared to original bounds and volume before it can
be returned to the UI. Manifold booleans construct cutter solids without
self-intersections. Rollers are constructed as nonintersecting radial surfaces
with positive material between the outer surface and axis/bore.

## Image interpretation and limits

PNG only, 8–2048 pixels per axis, up to 12 MB. Dimensions are limited to keep
the synchronous local MVP predictable. No automatic image downsampling.
Colour tolerance is measured per RGB channel. Antialias blends with white
are supported; blends between ink colours are accepted when the corresponding
pure colours are within three source pixels. Isolated non-palette colours
are highlighted magenta. Transparent pixels (alpha <128) are ignored;
partially opaque pixels use their uncomposited RGB values. Roller grayscale
preserves all 256 gray levels after checking channel agreement against
tolerance; nearly neutral RGB pixels use the mean of their three channels.
Colour tolerance only controls allowed channel differences, not depth levels.
The interpreted roller preview preserves the source gray levels.

Contours are traced on a nearest-neighbour 2× raster to retain area for narrow
pixel features. Vertices follow subpixel raster boundaries; no spline fitting
is applied. Collinear vertices are simplified without changing geometry.
Source detail and raster stair-stepping remain visible; supply sufficient
resolution for manufacturing. No CAD outline reconstruction or automatic gap
repair is attempted. The minimum-feature warning uses morphological analysis
and may flag sharp corners as well as thin lines.

The app verifies digital geometry, not the strength, food-contact suitability,
or print settings of a particular material. No G-code is generated. Place
the reverse flange face down for cookie cutters; the default backing is
1 mm above that build surface, so support may be needed beneath the backing.
Setting backing thickness equal to reverse-frame height gives a coplanar base.

## Tests and sample artwork

```powershell
.\.venv\Scripts\python.exe -m tests.samples
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m tests.export_samples
```

`samples/` includes smiling face, concave star, green loop, antialiased artwork,
open ring and outside-green rejection cases, diagonal stripes, repeating
squares, a seam-crossing pattern, and continuous grayscale waves. Geometry tests verify bounds, height
levels by actual surface intersections, relief radii, caps and bore, volume,
connectivity, nondegenerate faces, STL reload and preview/download identity.
The export command writes seven verified STLs and a JSON integrity report into
`test-output/` for manual inspection. `backend/requirements.lock.txt` records
the exact Python dependency versions used for verification; install it instead
of `requirements.txt` to reproduce that environment. The frontend pnpm lockfile
records the tested JavaScript dependency versions.

Manifold simplification removes numerical slivers with a 0.0001 mm tolerance
before STL float32 conversion. Every model is checked again after conversion;
failed precision or topology checks block download.

Structure:

```
backend/imaging/        palette classification and raster contours
backend/geometry/       cutter, roller, solid/export validation
backend/main.py         multipart API and static frontend serving
frontend/src/           React controls and Three.js preview
tests/                 generated fixtures and integration/geometry tests
samples/               ready-to-upload PNGs
```

API: `POST /api/generate` with multipart fields `image` (PNG) and `settings`
(JSON; defaults defined in `backend/models.py`). Success returns the STL as
base64, a preview mode, segmented PNG, warnings and stats. Cookie results also
include triangle positions and colours; rollers preview the exact STL bytes
directly to avoid duplicating high-resolution geometry in decimal JSON arrays.
Invalid inputs return HTTP 422 with an error and, where available, a highlighted
image. `/api/health` reports server readiness. No files are persisted by the API.
