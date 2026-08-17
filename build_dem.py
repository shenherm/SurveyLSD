#!/usr/bin/env python3
"""
build_dem.py  --  Build dem.bin (offline ground-elevation grid) for LSD Patrol Nav.

Run this in Google Colab (free, no install of anything special needed). It reads the
pipeline lines that are LIVE in the app, samples ground elevation ALONG those patrol
corridors from the free, keyless Open-Meteo elevation API (the same source the app uses
online, so offline readings match), and writes a compact "DEM1" file the app loads as
dem.bin. Once dem.bin is in the repo, ground/AGL work fully offline everywhere you patrol
-- no per-line downloading, forever.

HOW TO USE (Google Colab)
-------------------------
1.  Go to  https://colab.research.google.com  ->  File -> New notebook.
2.  Paste this whole file into a cell.
3.  Runtime -> Run all.  It prints an estimate, then samples (progress shown). ~15-25 min.
4.  When it finishes it downloads  dem.bin  to your computer.
5.  Send that dem.bin back in the chat -- it gets committed and the app picks it up
    automatically (the service worker already caches it).

You do NOT need to edit anything. To re-build later (e.g. after adding lines), just Run all
again. Coarser CELL_DEG = faster/smaller; finer = sharper but more API calls.
"""

import struct, time, math, sys, json, urllib.request

# ----------------------------------------------------------------- configuration
LINES_BASE = "https://raw.githubusercontent.com/shenherm/SurveyLSD/main/lines"
RADIUS_KM  = 3.0        # how far each side of a line to cover (>= the app's 2 km + margin)
CELL_DEG   = 0.004      # grid spacing (~445 m). 0.0025 (~280 m) is sharper but ~2.5x calls.
BLOCK_DEG  = 0.1        # storage block size (keeps the file compact for spread-out lines)
BATCH      = 100        # Open-Meteo points per request (max 100)
PAUSE      = 0.4        # seconds between requests (stay under the free rate limit)
OUT        = "dem.bin"
ND         = -32768     # nodata sentinel

def fetch_json(url, tries=4):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if a == tries-1: raise
            time.sleep(2*(a+1))

# ------------------------------------------------------- 1) read the live lines
print("Reading pipeline lines from the app ...")
man = fetch_json(LINES_BASE + "/manifest.json")
lines = man["lines"]
print(f"  {len(lines)} built-in lines (manifest v{man.get('version')})")

segs = []   # list of polylines, each [[lat,lon],...]
for L in lines:
    g = fetch_json(LINES_BASE + "/" + L["file"])
    for ln in g.get("lines", []):
        p = ln.get("p", [])
        if len(p) >= 1: segs.append(p)
print(f"  {len(segs)} line segments loaded")

# --------------------------------------- 2) stamp corridor cells (global grid)
CELL = CELL_DEG
BC   = int(round(BLOCK_DEG / CELL))     # cells per storage block side
cells = set()                           # global (gr, gc) integer grid indices to sample

def stamp(lat, lon):
    rr = RADIUS_KM / 111.0
    rc = RADIUS_KM / (111.0 * math.cos(lat*math.pi/180.0))
    gr0 = int(round((lat-rr)/CELL)); gr1 = int(round((lat+rr)/CELL))
    for gr in range(gr0, gr1+1):
        fr = (gr*CELL - lat) / rr
        if abs(fr) > 1: continue
        span = math.sqrt(max(0.0, 1.0-fr*fr)) * rc
        gc0 = int(round((lon-span)/CELL)); gc1 = int(round((lon+span)/CELL))
        for gc in range(gc0, gc1+1):
            cells.add((gr, gc))

print("Stamping corridors ...")
for p in segs:
    for i in range(len(p)):
        la, lo = p[i][0], p[i][1]
        stamp(la, lo)
        if i > 0:                      # densify along each segment so the corridor is continuous
            la0, lo0 = p[i-1][0], p[i-1][1]
            d = math.hypot((la-la0)*111.0, (lo-lo0)*111.0*math.cos(la*math.pi/180.0))
            steps = int(d/0.3)
            for s in range(1, steps):
                f = s/steps
                stamp(la0+(la-la0)*f, lo0+(lo-lo0)*f)

if not cells:
    print("No cells to sample -- aborting."); sys.exit(1)

# ---------------------------------- 3) group into overlapping storage blocks
# Each block covers BC+1 cells (1-cell overlap) so interpolation is continuous across edges.
blocks = {}                             # (bR,bC) -> set of local (r,c) to sample
for (gr, gc) in cells:
    bR, bC_ = gr//BC, gc//BC
    for (bbR, bbC) in ((bR,bC_),):      # primary block
        blocks.setdefault((bbR,bbC), set()).add((gr-bbR*BC, gc-bbC*BC))
    # also register on lower-index neighbour blocks when on their shared (overlap) edge
    if gr - bR*BC == 0 and bR-1 is not None:
        blocks.setdefault((bR-1,bC_), set()).add((BC, gc-bC_*BC))
    if gc - bC_*BC == 0:
        blocks.setdefault((bR,bC_-1), set()).add((gr-bR*BC, BC))
    if gr - bR*BC == 0 and gc - bC_*BC == 0:
        blocks.setdefault((bR-1,bC_-1), set()).add((BC, BC))

ncells = sum(len(s) for s in blocks.values())
la_all = [gr for gr,gc in cells]; lo_all = [gc for gr,gc in cells]
print(f"\nCoverage: {len(cells):,} corridor cells in {len(blocks)} blocks")
print(f"  extent  lat {min(la_all)*CELL:.2f}..{max(la_all)*CELL:.2f}  "
      f"lon {min(lo_all)*CELL:.2f}..{max(lo_all)*CELL:.2f}")
print(f"  ~{math.ceil(ncells/BATCH):,} elevation requests, ~{ncells/BATCH*PAUSE/60:.0f} min\n")

# ---------------------------------- 4) sample elevations (Open-Meteo, paced+retried)
def elev_batch(lats, lons, tries=5):
    url = ("https://api.open-meteo.com/v1/elevation?latitude="
           + ",".join(f"{v:.5f}" for v in lats)
           + "&longitude=" + ",".join(f"{v:.5f}" for v in lons))
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                j = json.loads(r.read().decode("utf-8"))
                e = j.get("elevation")
                if e: return e
        except Exception:
            pass
        time.sleep(1.5*(a+1))           # back off on rate-limit / transient error
    return None

# collect every (bkey, local r,c, lat, lon) to sample, in one flat list
todo = []
for (bR,bC_), locs in blocks.items():
    for (r,c) in locs:
        gr = bR*BC + r; gc = bC_*BC + c
        todo.append((bR,bC_,r,c, gr*CELL, gc*CELL))

region_data = {}                        # (bR,bC) -> Int16 grid (list) filled with ND
def grid_for(bkey):
    if bkey not in region_data:
        region_data[bkey] = [ND]*((BC+1)*(BC+1))
    return region_data[bkey]

done = 0; miss = 0; t0 = time.time()
for i in range(0, len(todo), BATCH):
    chunk = todo[i:i+BATCH]
    lats = [t[4] for t in chunk]; lons = [t[5] for t in chunk]
    ev = elev_batch(lats, lons)
    if ev is None:
        miss += len(chunk)
    else:
        for k,(bR,bC_,r,c,la,lo) in enumerate(chunk):
            v = ev[k] if k < len(ev) else None
            if v is not None and math.isfinite(v):
                grid_for((bR,bC_))[r*(BC+1)+c] = max(-32000, min(32000, int(round(v))))
    done += len(chunk)
    if (i//BATCH) % 20 == 0 or done >= len(todo):
        el = time.time()-t0
        print(f"  {done:,}/{len(todo):,} sampled  ({done*100//max(1,len(todo))}%)  "
              f"{el:.0f}s elapsed  {miss} missed")
    time.sleep(PAUSE)

if miss:
    print(f"\nNote: {miss:,} points failed (rate limit / network). Re-run to fill gaps, "
          f"or the app will fall back near those spots.")

# ---------------------------------- 5) write DEM1 (matches the app's loadDEM)
regions = [k for k in region_data.keys()]
regions.sort()
buf = bytearray()
buf += b"DEM1"
buf += struct.pack("<H", len(regions))
for (bR,bC_) in regions:
    lat0 = bR*BC*CELL
    lon0 = bC_*BC*CELL
    buf += struct.pack("<i", int(round(lat0*1e6)))
    buf += struct.pack("<i", int(round(lon0*1e6)))
    buf += struct.pack("<i", int(round(CELL*1e6)))
    buf += struct.pack("<i", int(round(CELL*1e6)))
    buf += struct.pack("<H", BC+1)
    buf += struct.pack("<H", BC+1)
    g = region_data[(bR,bC_)]
    buf += struct.pack("<%dh" % len(g), *g)

open(OUT, "wb").write(buf)
print(f"\nWrote {OUT}: {len(regions)} regions, {len(buf)/1e6:.2f} MB")

try:
    from google.colab import files
    files.download(OUT)
    print("Downloading dem.bin to your computer -- send it back in the chat.")
except Exception:
    print(f"Saved {OUT} in the working directory.")
