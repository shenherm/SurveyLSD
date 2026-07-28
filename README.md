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

Everything needed to fly without a connection is stored **on the device**, in storage the
app reads directly (IndexedDB / localStorage) — *not* only in the service-worker cache. This
is deliberate: it means offline works the same in the browser PWA and in a future native
(Capacitor) iPad app, where the service worker does not run.

- **Pipelines (KML/KMZ)** — imported geometry is stored in **IndexedDB** and reloaded on
  launch, so your lines persist across sessions with no re-import.
- **Pins** — saved to **localStorage** on drop and restored on launch.
- **Map imagery** — **downloaded in one tap** and stored as image blobs in **IndexedDB**.
  Open **Map key** and choose what to download:
  - **Along pipelines (corridor)** — *default.* Saves only tiles within a chosen radius
    (2 / 5 / 10 km each side) of the loaded, visible KML lines. A thin flight line no longer
    drags in a whole rectangle of imagery you'll never fly over — typically several times less
    data than the box for the same coverage. Toggle off any lines you're not flying first.
  - **Current view (box)** — the old behaviour: every tile in the current rectangle.

  Pick a detail level (z14–z17) and tap **Download**. Live tile/size/time estimate, progress
  bar and cancel. The limit is the device's **free storage**, not a fixed size: the estimate
  warns if a job wouldn't fit (leaving ~250 MB headroom), and a download that does hit the
  storage ceiling mid-run stops cleanly and reports how many tiles were saved. Multi-GB
  downloads are fine on a device with the room. A custom canvas tile layer reads stored tiles
  straight back when offline, falls through to the network when online, and — when you zoom in
  past the level you downloaded — **overzooms**: it scales up the best lower-zoom tile it has
  instead of going black (transparent only if nothing at all is stored there). The sheet shows
  how many tiles are saved and a **Clear saved imagery** button.
- **App shell** — `index.html`, the vendored libraries and icons are precached by the
  service worker so the PWA also *loads* offline. (In a native build the shell is bundled in
  the app instead.)
- **Elevation** — downloaded **together with the corridor imagery** and stored in
  **IndexedDB**, so ground/AGL read instantly from on-device terrain with no network, for
  whatever lines you're flying. Re-downloading for new lines refreshes it. Outside saved
  coverage it falls back to the online elevation API (service-worker-cached in the PWA). An
  optional pre-built `dem.bin` can still be bundled too (see *Elevation (DEM)*).

**Note:** the first load, the imagery download, and a first KML import must be online — the
device can only store what it has fetched at least once. Install, import lines, and
pre-download the area on wifi before a no-signal flight.

---

## Repository layout

```
index.html                  the entire app (HTML + CSS + JS in one file)
sw.js                       service worker (PWA only): app-shell offline + elevation cache
manifest.webmanifest        PWA manifest (standalone display, icons)

ats_grid.bin                Alberta ATS section grid   (binary, ~9 MB)
sk_grid.bin                 Saskatchewan section grid  (binary, ~2.9 MB)
dem.bin                     offline ground-elevation grid (optional; built in Colab)

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
  small metadata (name, colour, width, order) in `localStorage`. All layers draw on **one
  shared canvas renderer** (see the performance note) grouped by colour/width, with Douglas–
  Peucker simplification (~10 cm). Layers over ~3,000 points use **viewport culling** when
  zoomed in (only the on-screen geometry is drawn) and a light **decimated overview** when
  zoomed out (below z10), so the whole route stays visible at any zoom without drawing every
  vertex.
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

## Elevation (DEM)

Ground/AGL elevation runs **offline** from terrain stored on the device. There are two ways
terrain gets there; the app uses whatever is available (first match wins), and without either
it simply stays online-only — nothing breaks.

**1. Downloaded along the corridor (primary).** When you download corridor imagery, the app
also samples ground elevation over the *same* area and stores it in IndexedDB — so elevation
coverage tracks the lines you're flying that day and refreshes every time you re-download. It
samples a regular ~280 m grid masked to the corridor (only cells near the lines), from the
**same Open-Meteo source** the app uses online, in batches of 100 points. Storage is tiny
(tens to a few hundred KB per area). A safety cap (~60,000 points) skips elevation on an
oversized area without affecting the imagery. Because this lives in IndexedDB, it also works
in a **native build** with no service worker. Cleared by **Clear saved imagery**.

**2. Pre-built `dem.bin` (optional).** A static terrain file can also be bundled at the repo
root and is loaded alongside any downloaded regions. Useful for permanent base coverage. It
uses a compact multi-region binary (`DEM1`), little-endian:

```
'DEM1'                     4-byte magic
uint16  nRegions
per region:
  int32 lat0_e6            south edge   (microdegrees)
  int32 lon0_e6            west edge    (microdegrees)
  int32 dLat_e6            row spacing  (microdegrees)
  int32 dLon_e6            col spacing  (microdegrees)
  uint16 nRows, nCols      grid size (rows south→north, cols west→east)
  int16[nRows*nCols]       elevation, metres, row-major; -32768 = nodata
```

`demElev(lat,lon)` does a bilinear lookup within whichever region covers the point (returns
`null` outside coverage or on nodata → online fallback). Build `dem.bin` in Colab with
`build_dem.py` (same Open-Meteo source); point it at your pipeline `.kml` file(s) or list
bounding boxes, run all, and upload `dem.bin` to the repo root. The service worker precaches
it best-effort (its absence never breaks install).

---

## Deploying & updating

GitHub Pages serves `main`, so **commit to `main` and it's live** (give Pages a minute).

- Small text files (`index.html`, `sw.js`, manifest) commit via the GitHub Contents API.
- Large binaries (grids) commit via the Git Data API (blob → tree → commit → ref).
- `index.html` is served **network-first**, so devices pick up new versions automatically
  when online.

### Service-worker versioning (in `sw.js`)

The service worker now only handles the **PWA app shell** and elevation — imagery lives in
IndexedDB (above), not the worker.

- **`SHELL_VER`** — bump this when the app shell, vendored libraries or icons change. The old
  shell cache is cleared on activate. (Currently `v3`.)

Downloaded imagery is unaffected by shell updates because it's in IndexedDB
(`patrolTiles`), cleared only via the in-app **Clear saved imagery** button.

---

## Device / browser constraints

The fleet includes **older iPads**, so the code targets older Safari:

- **No ES2020+ syntax** (no optional chaining `?.`, nullish `??`). Arrow functions,
  `const`/`let`, template literals, `async`/`await`, spread, `for…of`, `Map`/`Set` are fine.
- **GPU-cheap UI** — no `backdrop-filter`/blur, minimal shadows; performance is tuned for
  old hardware (chunked grid parsing, canvas rendering, viewport culling, coalesced readouts).
- **Memory & responsiveness on A7/A8-class iPads** — the biggest lever is that **all KML
  layers share one canvas renderer**: a separate canvas per layer each allocates a full-screen
  Retina buffer (tens of MB), so loading many lines exhausted memory and iOS killed/reloaded
  the tab. One shared canvas keeps render memory flat no matter how many lines are on (extra
  lines cost draw time, not memory); the trade-off is that inter-layer paint order follows
  draw order rather than a per-layer z-index. Turning a layer **off frees its geometry and
  polylines from RAM** (the geometry stays in IndexedDB and reloads when turned back on), so
  memory scales with what's *visible*, not what's *loaded*. Layers over ~3,000 points draw only
  what's near the view (viewport-bounded), and on startup on-layers load one at a time.
  Pipeline geometry is stored as flat `Float32Array` runs rather than arrays of `[lat,lon]`
  pairs, cutting a large network file from ~80 MB to ~10 MB and iterating much faster; Leaflet
  is handed `[lat,lon]` pairs only for the on-screen points it draws. Coordinates simplify at
  full precision first, so the only loss is ~1 m Float32 rounding on the overlay (the
  authoritative LSD/coords come from the crosshair + survey grid, not the KML). Base tile
  layers use `updateWhenIdle`, `updateWhenZooming:false` and `keepBuffer:1`; marker/fade
  animations are off; downloaded-tile object URLs are revoked on load/unload. Low-core devices
  (`hardwareConcurrency`) ease back download concurrency (4 vs 8) and the heavy
  corridor/elevation loops yield periodically so they never freeze the UI. Progress updates are
  throttled (~4/s).
- All inline scripts are syntax-checked (`node --check`) before each deploy.

---

## Native iOS app (Capacitor)

This ships as a real native iPad app via **Capacitor**, which wraps the existing web app in
an Xcode project that builds to an `.ipa` for TestFlight / ad-hoc install. **The app is
prepared for this now** — see **[NATIVE_BUILD.md](NATIVE_BUILD.md)** for the full
step-by-step build, plus `capacitor.config.json` and `package.json` in the repo root.

Everything the app needs offline uses storage the native WebView reads directly, with **no
service worker** (which doesn't run in Capacitor):

- **Imagery** downloads to **IndexedDB** (`patrolTiles`), served by the custom canvas tile
  layer (with overzoom). Downloads use CORS fetches so the bytes are readable in the WebView.
- **Pipelines** import to **IndexedDB** (`patrolKml`); the file picker works from the iOS
  Files app (`accept="*/*"`), and geometry persists across launches.
- **Elevation** downloads along the corridor to **IndexedDB** (`patrolDem`) — no bundled file
  or service worker needed.
- **Pins** persist in **localStorage**.
- **Survey grids, optional DEM, and built-in lines** are bundled in the app, so LSD lookup and
  the pipeline overview work offline from first launch. Imagery/elevation need one online
  session to download, exactly like the PWA.

The service worker registration is skipped automatically on the native `capacitor://` scheme,
and all data paths are relative so they resolve against the bundled assets.

**To build you need:** a **Mac with Xcode**, **Node.js** + **CocoaPods**, and — for permanent
install / fleet distribution — an **Apple Developer account** ($99/yr). Full walkthrough in
[NATIVE_BUILD.md](NATIVE_BUILD.md).

The tradeoff is distribution and polish (TestFlight, durable storage, no data eviction) in
exchange for a Mac, the yearly fee and Xcode upkeep. The PWA already delivers the
core in-flight experience without any of that.

## Credits

Built for EnviroTech Aviation Inc. Mapping by [Leaflet](https://leafletjs.com/). Imagery:
Esri World Imagery, EOX Sentinel-2 cloudless, OpenStreetMap contributors. Elevation: Open-Meteo
(Copernicus DEM) and Esri Terrain. Survey data: Alberta ATS and Saskatchewan cadastral grids.
