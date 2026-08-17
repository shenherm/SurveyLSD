#!/usr/bin/env python3
"""
build_dem.py  --  Build dem.bin (offline ground-elevation grid) for LSD Patrol Nav.
RESUMABLE: saves progress to your Google Drive after every batch, so if Colab
disconnects you just Run all again and it continues where it stopped.

It reads the pipeline lines LIVE from the app, samples ground elevation ALONG your
patrol corridors from the free Open-Meteo API (same source the app uses online, so
offline matches), and writes a compact "DEM1" file the app loads as dem.bin. Once dem.bin
is in the repo, ground/AGL work fully offline everywhere you patrol -- forever.

HOW TO USE (Google Colab)
-------------------------
1.  https://colab.research.google.com  ->  File -> New notebook.
2.  Paste this whole file into a cell.
3.  Runtime -> Run all.  It asks to connect Google Drive (click Allow) -- that's where
    progress is saved so nothing is ever lost.
4.  It samples with a progress readout. If Colab disconnects or you close it, just open it
    again and Runtime -> Run all -- it resumes. Repeat until it prints  *** COMPLETE ***
    and downloads  dem.bin.
5.  Send that dem.bin back in the chat -- it gets committed and the app picks it up.

Nothing to configure. Re-run any time (e.g. after adding lines): delete the progress file
noted below to start fresh, or just Run all to top it up.
"""

import struct, time, math, sys, os, json, pickle, urllib.request

# ----------------------------------------------------------------- configuration
LINES_BASE = "https://raw.githubusercontent.com/shenherm/SurveyLSD/main/lines"
RADIUS_KM  = 3.0        # cover this far each side of every line (>= app's 2 km + margin)
CELL_DEG   = 0.004      # grid spacing (~445 m). Fine enough for AGL.
BLOCK_DEG  = 0.1        # storage block size (keeps the file compact)
BATCH      = 100        # Open-Meteo points per request
PAUSE      = 0.3        # seconds between requests (stay under the free rate limit)
SAVE_EVERY = 20         # save progress to Drive every N batches
OUT        = "dem.bin"
ND         = -32768

# --------------------------------------------------- connect Google Drive (resume store)
WORKDIR = "."
try:
    from google.colab import drive
    drive.mount("/content/drive")
    WORKDIR = "/content/drive/MyDrive/lsd_dem"
    os.makedirs(WORKDIR, exist_ok=True)
    print("Progress will be saved in Google Drive -> MyDrive/lsd_dem/")
except Exception:
    print("(Not on Colab / no Drive -- progress saved in the working folder.)")
PROG = os.path.join(WORKDIR, "dem_progress.pkl")

def load_progress():
    if os.path.exists(PROG):
        try:
            with open(PROG, "rb") as f: return pickle.load(f)
        except Exception: pass
    return {}
def save_progress(done):
    tmp = PROG + ".tmp"
    with open(tmp, "wb") as f: pickle.dump(done, f, protocol=2)
    os.replace(tmp, PROG)          # atomic: never leaves a half-written file

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

# --------------------------------------- 2) which grid cells the corridors need
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

# ---------------------------------------------- 3) sample remaining cells (resumable)
done = load_progress()                    # {(gr,gc): elev_int}
done = {k:v for k,v in done.items() if k in cells}   # keep only relevant
need = [c for c in cells if c not in done]
print(f"  already have {len(done):,}; {len(need):,} to go "
      f"(~{math.ceil(len(need)/BATCH):,} requests, ~{len(need)/BATCH*PAUSE/60:.0f} min)")

def elev_batch(cs, tries=5):
    lats = [gr*CELL for gr,gc in cs]; lons = [gc*CELL for gr,gc in cs]
    url = ("https://api.open-meteo.com/v1/elevation?latitude="
           + ",".join(f"{v:.5f}" for v in lats)
           + "&longitude=" + ",".join(f"{v:.5f}" for v in lons))
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                e = json.loads(r.read().decode("utf-8")).get("elevation")
                if e: return e
        except Exception: pass
        time.sleep(1.5*(a+1))            # back off on rate-limit
    return None

t0 = time.time(); nb = 0
for i in range(0, len(need), BATCH):
    chunk = need[i:i+BATCH]
    ev = elev_batch(chunk)
    if ev:
        for k,(gr,gc) in enumerate(chunk):
            v = ev[k] if k < len(ev) else None
            if v is not None and math.isfinite(v):
                done[(gr,gc)] = max(-32000, min(32000, int(round(v))))
    nb += 1
    if nb % SAVE_EVERY == 0: save_progress(done)
    if nb % 20 == 0 or i+BATCH >= len(need):
        got = len(done)
        print(f"  {got:,}/{len(cells):,} cells ({got*100//len(cells)}%)  "
              f"{time.time()-t0:.0f}s this run")
    time.sleep(PAUSE)
save_progress(done)

# ---------------------------------------------------------- 4) finished? build dem.bin
remaining = len([c for c in cells if c not in done])
if remaining > len(cells)*0.02:          # >2% still missing -> another pass needed
    print(f"\nStopped with {remaining:,} cells left (rate limit / disconnect). "
          f"Run all again to continue -- progress is saved.")
    sys.exit(0)

print(f"\nAll cells sampled. Building {OUT} ...")
region = {}                              # (bR,bC) -> grid list
def grid(bkey):
    if bkey not in region: region[bkey] = [ND]*((BC+1)*(BC+1))
    return region[bkey]
def put(gr, gc, v):
    bR, bC = gr//BC, gc//BC
    grid((bR,bC))[(gr-bR*BC)*(BC+1)+(gc-bC*BC)] = v
    if gr-bR*BC == 0: grid((bR-1,bC))[BC*(BC+1)+(gc-bC*BC)] = v          # overlap edges
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
