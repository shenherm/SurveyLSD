/* SurveyLSD / LSD Patrol Nav - offline service worker (browser PWA only).
   NOTE: in a native (Capacitor) build this worker does not run. Offline imagery,
   pipelines and pins therefore live in IndexedDB / localStorage (read directly by
   the app), not here, so they work in both the PWA and the native iPad app.
   This worker only makes the PWA's app SHELL available offline + caches elevation.
   Bump SHELL_VER when the shell, libraries or icons change.
   The survey grids + DEM live in their OWN cache (GRIDS) so a shell/code update
   never re-downloads or evicts them -- they are fetched once and kept. Bump
   GRID_VER only when ats_grid.bin / sk_grid.bin / dem.bin themselves change. */
var SHELL_VER = 'v29';
var DATA_VER  = 'v1';
var GRID_VER  = 'v1';
var SHELL = 'surveylsd-shell-' + SHELL_VER;   // app shell + libraries (cache-first)
var DATA  = 'surveylsd-data-'  + DATA_VER;    // elevation lookups (network-first, cache fallback)
var GRIDS = 'surveylsd-grids-' + GRID_VER;    // survey grids + DEM: downloaded once, kept across shell updates

var SHELL_CORE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './envirotech-logo.png',
  './vendor/leaflet/leaflet.css',
  './vendor/leaflet/leaflet.js',
  './vendor/leaflet/images/layers.png',
  './vendor/leaflet/images/layers-2x.png',
  './vendor/leaflet/images/marker-icon.png',
  './vendor/leaflet/images/marker-icon-2x.png',
  './vendor/leaflet/images/marker-shadow.png',
  './vendor/jszip.min.js',
  './fonts/plex-sans-400.woff2',
  './fonts/plex-sans-600.woff2',
  './fonts/plex-sans-700.woff2',
  './fonts/plex-mono-400.woff2',
  './fonts/plex-mono-600.woff2',
  './fonts/plex-mono-700.woff2',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  './apple-touch-icon-167.png'
];
var GRID_FILES = ['./ats_grid.bin', './sk_grid.bin', './dem.bin'];

function isElevHost(u){
  var h = u.hostname;
  return h === 'api.open-meteo.com' || h === 'elevation3d.arcgis.com';
}
function isGridFile(u){
  var p = u.pathname;
  return p.indexOf('ats_grid.bin') !== -1 || p.indexOf('sk_grid.bin') !== -1 || p.indexOf('dem.bin') !== -1;
}

self.addEventListener('install', function(event){
  event.waitUntil((async function(){
    var cache = await caches.open(SHELL);
    await cache.addAll(SHELL_CORE);
    // Grids/DEM: only fetch the ones not already cached (so a shell update doesn't re-download them).
    var gc = await caches.open(GRIDS);
    await Promise.all(GRID_FILES.map(async function(u){
      var has = await gc.match(u);
      if (!has) { try { await gc.add(u); } catch (e) {} }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', function(event){
  event.waitUntil((async function(){
    var names = await caches.keys();
    await Promise.all(names.map(function(n){
      if (n.indexOf('surveylsd-') === 0 && n !== SHELL && n !== DATA && n !== GRIDS) return caches.delete(n);
      return null;
    }));
    await caches.open(DATA);
    await self.clients.claim();
  })());
});

async function cacheFirst(req, cacheName){
  var cache = await caches.open(cacheName);
  var hit = await cache.match(req);
  if (hit) return hit;
  try {
    var res = await fetch(req);
    if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
    return res;
  } catch (e) {
    var fb = await cache.match(req);
    if (fb) return fb;
    throw e;
  }
}

/* Grids are critical + static: prefer the cache, but if it's missing/broken, fetch from
   network and (re)cache a valid copy. This self-heals a bad cached grid. */
async function gridFirst(req){
  var cache = await caches.open(GRIDS);
  var hit = await cache.match(req);
  if (hit) return hit;
  var res = await fetch(req);              // may throw when offline -> handled by caller's fallback
  if (res && res.ok) cache.put(req, res.clone());
  return res;
}

async function networkFirst(req, cacheName){
  var cache = await caches.open(cacheName);
  try {
    var res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (e) {
    var hit = await cache.match(req);
    if (hit) return hit;
    throw e;
  }
}

self.addEventListener('fetch', function(event){
  var req = event.request;
  if (req.method !== 'GET') return;
  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

  if (isElevHost(url)) { event.respondWith(networkFirst(req, DATA)); return; }

  if (url.origin === self.location.origin){
    // Survey grids + DEM: their own persistent cache, self-healing from network.
    if (isGridFile(url)) { event.respondWith(gridFirst(req).catch(function(){ return caches.match(req); })); return; }
    // Built-in lines (manifest + geometry): network-first so new/updated built-ins appear online.
    if (url.pathname.indexOf('/lines/') !== -1) { event.respondWith(networkFirst(req, SHELL)); return; }
    var isDoc = req.mode === 'navigate'
             || url.pathname.charAt(url.pathname.length - 1) === '/'
             || url.pathname.indexOf('.html') !== -1;
    if (isDoc) { event.respondWith(networkFirst(req, SHELL)); return; }
    event.respondWith(cacheFirst(req, SHELL)); return;
  }
  // Anything else (incl. map tiles when online): network, fall back to cache if present.
  event.respondWith(fetch(req).catch(function(){ return caches.match(req); }));
});
