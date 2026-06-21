# LSD Patrol Nav (SurveyLSD)

Aerial pipeline-patrol navigation for **EnviroTech Aviation Inc.** (Edmonton). A moving
satellite map with a fixed crosshair that reads out the exact **Legal Subdivision (LSD)**
land description, decimal coordinates, and ground/AGL elevation under the aircraft, plus
KML pipeline overlays, GPS tracking, distance measuring, and full offline operation on
iPads.

**Live:** https://shenherm.github.io/SurveyLSD/

It is a single-file web app (a PWA) — no build step, no server. Deploying is just
committing to `main`; GitHub Pages serves it.

---

## What it does

- **Exact LSD readout** under the crosshair — e.g. `(SE) 07-23-52-14-W4M` — for Alberta
  (meridians W4/W5/W6) and Saskatchewan (W3), looked up from on-device survey-grid data.
  Falls back to a labelled approximation outside the loaded grid.
- **Coordinates** (decimal degrees, 6 dp) and **zoom** readout.
- **Ground & aircraft elevation** — ground MSL under the crosshair, GPS altitude, and AGL
  (turns red above 1000 ft).
- **Continuous GPS** with a follow/recenter toggle.
- **KML / KMZ pipeline overlays** — import your own route files; per-line colour, thickness
  and draw-order; viewport-culled canvas rendering that stays smooth on large networks.
- **Go-to pad** — jump to any LSD or lat/lon with big, turbulence-friendly touch targets.
- **Measure** — drop two points and read the distance between them.
- **Pin** — mark the point under the crosshair.
- **Offline** — runs with no signal once installed, including one-click imagery download
  for the patrol area (see below).

---

## Install on an iPad

1. On wifi, open **https://shenherm.github.io/SurveyLSD/** in Safari.
2. **Share → Add to Home Screen → Add.**
3. Launch from the home-screen icon. It runs full-screen and works offline.

This is the supported "local app" path — no Mac, Xcode or Apple Developer account needed.

---

## Offline use

A service worker (`sw.js`) caches everything needed to run without a connection:

- **App shell + survey grids** are precached on first load, so LSD lookup, coordinates,
  measure, pin and your imported lines all work offline immediately.
- **Map imagery** is cached as viewed, *and* can be **downloaded in one tap**: open
  **Map key**, frame the patrol area, choose a detail level (z14–z17), and tap
  **Download area**. It shows a live tile/size/time estimate, has a progress bar and
  cancel, and refuses areas over ~25,000 tiles (zoom in instead). Tiles are written to the
  same cache the worker serves from.
- **Elevation** readings are cached network-first, so seen areas keep showing ground/AGL
  offline.

**Note:** the very first load (and any imagery download) must be online — a service worker
can only cache what it has fetched at least once. Install and pre-download on wifi before a
no-signal flight.

---

## Repository layout

```
index.html                  the entire app (HTML + CSS + JS in one file)
sw.js                       service worker: offline shell + tile/grid/elevation caching
manifest.webmanifest        PWA manifest (standalone display, icons)

ats_grid.bin                Alberta ATS section grid   (binary, ~9 MB)
sk_grid.bin                 Saskatchewan section grid  (binary, ~2.9 MB)

vendor/leaflet/             Leaflet 1.9.4, vendored locally (js, css, marker images)
vendor/jszip.min.js         JSZip, vendored locally (for reading .kmz)

envirotech-logo.png         company logo (launch screen)
icon-192.png / icon-512.png PWA icons (reticle badge)
apple-touch-icon*.png       iOS home-screen icons

lines/                      prebuilt pipeline geometry (currently DORMANT — see below)
  manifest.json             built-in line manifest; empty {version:4, lines:[]}
  *.json                    compact geometry for regional + full-network routes
```

### About `lines/`

These are compact, pre-simplified pipeline geometries from an earlier "built-in library"
feature. That feature was **removed** in favour of manual KML import, so `lines/manifest.json`
is intentionally empty and **none of these files are loaded** by the app today. They're left
in place (harmless) so the built-ins can be re-enabled later by repopulating the manifest.
The live way to add pipelines is **Lines → Import** in the app.

---

## How it works

- **Single file.** `index.html` contains all markup, styles and logic. Leaflet and JSZip
  are vendored under `vendor/` so nothing loads from a CDN at runtime.
- **Exact LSD lookup.** The `.bin` grids hold every survey section's corner coordinates.
  At runtime they're parsed (in non-blocking chunks) into a spatial hash; the crosshair's
  lat/lon is located to a section, then to a quarter/LSD via an affine inverse. The reverse
  (LSD → lat/lon) is used by the Go-to pad. Until a grid finishes parsing, an approximate
  reading is shown and labelled.
- **KML rendering.** Imported geometry is stored in **IndexedDB** (`patrolKml`), with only
  small metadata (name, colour, width, order) in `localStorage`. Each layer draws on its own
  Leaflet canvas pane, grouped by colour/width, with **viewport culling** and Douglas–Peucker
  simplification (~10 cm) so big files stay responsive.
- **Imagery layers.** Esri World Imagery (sharpest; needs a free ArcGIS API key stored on
  the device), Sentinel-2 cloudless (EOX, keyless, ~10 m), or OpenStreetMap — switchable in
  the layers control.
- **Elevation.** Open-Meteo (keyless) for ground MSL, with an Esri Terrain fallback; cached
  on a coarse grid.

---

## Survey grids

Both grids share a simple binary format (`ATS1`):

```
header:  "ATS1" (4 bytes) + uint32 record count (little-endian)
record:  uint8  meridian
         uint16 range          (LE)
         uint16 township       (LE)
         uint8  section
         8 × int32 (LE)        section corner coords in microdegrees,
                               in order NE, NW, SW, SE  (lat,lon each)
```

Coordinates are `round(degrees × 1e6)`. The app merges multiple `ATS1` buffers, so Alberta
and Saskatchewan load side by side (no key collision: AB uses meridians W4/W5/W6, SK uses
W1/W2/W3).

**Rebuilding the grids** is done outside this repo, in **Google Colab**:

- **Alberta** — built from the Alberta ATS grid.
- **Saskatchewan** — built from the public federal cadastral mirror
  (`services.sac-isc.gc.ca`, layer `SaskGrid_2016_SECTION`), since the provincial service is
  token-gated. Current coverage is the western strip (W3M, ~49–59°N). To patrol east of
  ~106°W (W2M), widen the builder's bounding box and rebuild.

The builder scripts/notebooks live with the project's working files; run them in Colab and
upload the resulting `ats_grid.bin` / `sk_grid.bin` to the repo root.

---

## Deploying & updating

GitHub Pages serves `main`, so **commit to `main` and it's live** (give Pages a minute).

- Small text files (`index.html`, `sw.js`, manifest) commit via the GitHub Contents API.
- Large binaries (grids) commit via the Git Data API (blob → tree → commit → ref).
- `index.html` is served **network-first**, so devices pick up new versions automatically
  when online.

### Service-worker versioning (in `sw.js`)

- **`SHELL_VER`** — bump this when the app shell, vendored libraries or icons change. The old
  shell cache is cleared on activate.
- **`TILE_VER`** — kept **stable on purpose** so imagery a crew has already downloaded for
  offline use is **not** wiped by an app update. Only bump it if the tile sources change.

---

## Device / browser constraints

The fleet includes **older iPads**, so the code targets older Safari:

- **No ES2020+ syntax** (no optional chaining `?.`, nullish `??`). Arrow functions,
  `const`/`let`, template literals, `async`/`await`, spread, `for…of`, `Map`/`Set` are fine.
- **GPU-cheap UI** — no `backdrop-filter`/blur, minimal shadows; performance is tuned for
  old hardware (chunked grid parsing, canvas rendering, viewport culling, coalesced readouts).
- All inline scripts are syntax-checked (`node --check`) before each deploy.

---

## Credits

Built for EnviroTech Aviation Inc. Mapping by [Leaflet](https://leafletjs.com/). Imagery:
Esri World Imagery, EOX Sentinel-2 cloudless, OpenStreetMap contributors. Elevation: Open-Meteo
(Copernicus DEM) and Esri Terrain. Survey data: Alberta ATS and Saskatchewan cadastral grids.
