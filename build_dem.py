#!/usr/bin/env python3
"""
build_dem.py  --  Build dem.bin (offline ground-elevation grid) for LSD Patrol Nav.

FAST + NO RATE LIMITS. Instead of asking an elevation API for one point at a time (which
gets rate-limited after ~5,000 points), this downloads a few hundred free public terrain
tiles from AWS Open Data (no key, no sign-up, no limit) and reads elevation from them
locally. The whole job is one clean run of a few minutes -- no restarting.

It reads the pipeline lines LIVE from the app, samples ground elevation ALONG your patrol
corridors, and writes a compact "DEM1" file the app loads as dem.bin. Once dem.bin is in
the repo, ground/AGL work fully offline everywhere you patrol -- forever.

HOW TO USE (Google Colab)
-------------------------
1.  https://colab.research.google.com  ->  File -> New notebook.
2.  Paste this whole file into a cell.
3.  Runtime -> Run all.  It downloads ~700 tiles and samples (progress shown), ~3-5 min.
4.  When it finishes it downloads  dem.bin  to your computer.
5.  Send that dem.bin back in the chat -- it gets committed and the app picks it up.

Nothing to configure. If tiles ever fail, just Run all again.
"""

import struct, time, math, sys, os, json, io, urllib.request
import numpy as np
from PIL import Image

# ----------------------------------------------------------------- configuration
LINES_BASE = "https://raw.githubusercontent.com/shenherm/SurveyLSD/main/lines"
RADIUS_KM  = 3.0        # cover this far each side of every line (>= app's 2 km + margin)
CELL_DEG   = 0.004      # output grid spacing (~445 m) -- plenty for AGL
BLOCK_DEG  = 0.1        # storage block size (keeps the file compact)
ZOOM       = 11         # terrain-tile zoom (~46 m/pixel -- finer than the output grid)
TILE_URL   = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OUT        = "dem.bin"
ND         = -32768

def fetch_json(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if a == tries-1: raise
            time.sleep(2*(a+1))

# ------------------------------------------------------- 1) read the live lines
print("Reading pipeline lines from the app ...")
man = fetch_json(LINES_BASE + "/manifest.json")
segs = []
for L in man["lines"]:
    g = fetch_json(LINES_BASE + "/" + L["file"])
    for ln in g.get("lines", []):
        if len(ln.get("p", [])) >= 1: segs.append(ln["p"])
print(f"  {len(man['lines'])} lines, {len(segs)} segments")

# --------------------------------------- 2) which output cells the corridors need
CELL = CELL_DEG
BC   = int(round(BLOCK_DEG / CELL))
cells = set()
def stamp(lat, lon):
    rr = RADIUS_KM/111.0; rc = RADIUS_KM/(111.0*math.cos(lat*math.pi/180.0))
    for gr in range(int(round((lat-rr)/CELL)), int(round((lat+rr)/CELL))+1):
        fr = (gr*CELL-lat)/rr
        if abs(fr) > 1: continue
        span = math.sqrt(max(0.0,1.0-fr*fr))*rc
        for gc in range(int(round((lon-span)/CELL)), int(round((lon+span)/CELL))+1):
            cells.add((gr, gc))
print("Mapping corridors ...")
for p in segs:
    for i in range(len(p)):
        stamp(p[i][0], p[i][1])
        if i > 0:
            la,lo = p[i]; la0,lo0 = p[i-1]
            d = math.hypot((la-la0)*111.0,(lo-lo0)*111.0*math.cos(la*math.pi/180.0))
            n = int(d/0.3)
            for s in range(1, n): f=s/n; stamp(la0+(la-la0)*f, lo0+(lo-lo0)*f)
print(f"  {len(cells):,} cells needed")

# --------------------------------- 3) which terrain tiles cover those cells
NP = (2**ZOOM) * 256
def to_px(lat, lon):
    x = (lon + 180.0)/360.0 * NP
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1+s)/(1-s))/(4*math.pi)) * NP
    return x, y

samples = []            # (gr, gc, gx, gy)
tiles_needed = set()
for (gr, gc) in cells:
    gx, gy = to_px(gr*CELL, gc*CELL)
    samples.append((gr, gc, gx, gy))
    px0, py0 = int(math.floor(gx)), int(math.floor(gy))
    for dx in (0,1):
        for dy in (0,1):
            tiles_needed.add(((px0+dx)//256, (py0+dy)//256))
tiles_needed = sorted(tiles_needed)
print(f"  {len(tiles_needed)} terrain tiles to fetch (~{len(tiles_needed)*20/1024:.1f} MB)\n")

# --------------------------------- 4) download + decode tiles (terrarium RGB)
def fetch_tile(tx, ty, tries=5):
    url = TILE_URL.format(z=ZOOM, x=tx, y=ty)
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                img = Image.open(io.BytesIO(r.read())).convert("RGB")
                arr = np.asarray(img, dtype=np.float64)
                return (arr[:,:,0]*256.0 + arr[:,:,1] + arr[:,:,2]/256.0 - 32768.0).astype(np.float32)
        except Exception:
            time.sleep(1.5*(a+1))
    return None

tiles = {}; miss_t = 0; t0 = time.time()
for i,(tx,ty) in enumerate(tiles_needed):
    a = fetch_tile(tx, ty)
    if a is not None: tiles[(tx,ty)] = a
    else: miss_t += 1
    if i % 50 == 0 or i == len(tiles_needed)-1:
        print(f"  tiles {i+1}/{len(tiles_needed)}  ({time.time()-t0:.0f}s)")
if miss_t: print(f"  ({miss_t} tiles failed -- Run all again to retry if AGL has gaps)")

# --------------------------------- 5) sample every cell from the tiles (local, instant)
def px_elev(px, py):
    t = tiles.get((px//256, py//256))
    if t is None: return None
    return float(t[py%256, px%256])

done = {}
for (gr, gc, gx, gy) in samples:
    px0, py0 = int(math.floor(gx)), int(math.floor(gy)); fx, fy = gx-px0, gy-py0
    v00, v10 = px_elev(px0,py0),   px_elev(px0+1,py0)
    v01, v11 = px_elev(px0,py0+1), px_elev(px0+1,py0+1)
    if None in (v00,v10,v01,v11):
        got = [v for v in (v00,v10,v01,v11) if v is not None]
        if not got: continue
        e = got[0]
    else:
        e = (v00*(1-fx)+v10*fx)*(1-fy) + (v01*(1-fx)+v11*fx)*fy
    done[(gr,gc)] = max(-32000, min(32000, int(round(e))))
print(f"\nSampled {len(done):,}/{len(cells):,} cells")

# --------------------------------- 6) write dem.bin (DEM1, block regions)
region = {}
def grid(bkey):
    if bkey not in region: region[bkey] = [ND]*((BC+1)*(BC+1))
    return region[bkey]
def put(gr, gc, v):
    bR, bC = gr//BC, gc//BC
    grid((bR,bC))[(gr-bR*BC)*(BC+1)+(gc-bC*BC)] = v
    if gr-bR*BC == 0: grid((bR-1,bC))[BC*(BC+1)+(gc-bC*BC)] = v
    if gc-bC*BC == 0: grid((bR,bC-1))[(gr-bR*BC)*(BC+1)+BC] = v
    if gr-bR*BC == 0 and gc-bC*BC == 0: grid((bR-1,bC-1))[BC*(BC+1)+BC] = v
for (gr,gc),v in done.items(): put(gr,gc,v)

regs = sorted(region.keys())
buf = bytearray(b"DEM1"); buf += struct.pack("<H", len(regs))
for (bR,bC) in regs:
    buf += struct.pack("<i", int(round(bR*BC*CELL*1e6)))
    buf += struct.pack("<i", int(round(bC*BC*CELL*1e6)))
    buf += struct.pack("<i", int(round(CELL*1e6)))
    buf += struct.pack("<i", int(round(CELL*1e6)))
    buf += struct.pack("<H", BC+1); buf += struct.pack("<H", BC+1)
    g = region[(bR,bC)]; buf += struct.pack("<%dh" % len(g), *g)
open(OUT, "wb").write(buf)
print(f"*** COMPLETE ***  {OUT}: {len(regs)} regions, {len(buf)/1e6:.2f} MB")
try:
    from google.colab import files; files.download(OUT)
    print("Downloading dem.bin -- send it back in the chat.")
except Exception:
    print(f"Saved {OUT} in {os.getcwd()}")
