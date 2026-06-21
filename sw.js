/* SurveyLSD / LSD Patrol Nav - offline service worker
   Bump SHELL_VER when the app shell, libraries or icons change (old shell cache is
   cleared on activate). TILE_VER is kept stable on purpose so imagery a crew has
   already downloaded for offline use is NOT wiped by an app update. */
var SHELL_VER = 'v2';   // bump on app-shell / library / icon changes
var TILE_VER  = 'v1';   // keep STABLE so downloaded offline imagery survives app updates
var DATA_VER  = 'v1';
var SHELL = 'surveylsd-shell-' + SHELL_VER;   // app shell + survey grids (cache-first)
var TILES = 'surveylsd-tiles-' + TILE_VER;    // map imagery (cache-first, capped)
var DATA  = 'surveylsd-data-'  + DATA_VER;    // elevation lookups (network-first, cache fallback)

var TILE_MAX = 2000;  // ~ a few hundred MB of tiles; oldest are evicted past this

/* Small, must-succeed shell assets */
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
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  './apple-touch-icon-167.png'
];

/* Large best-effort assets - install must not fail if one hiccups */
var SHELL_BIG = [
  './ats_grid.bin',
  './sk_grid.bin'
];

/* 1x1 transparent PNG, returned for tiles that aren't cached while offline */
var BLANK_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
function blankTile(){
  var bin = atob(BLANK_PNG);
  var arr = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Response(arr, { headers: { 'Content-Type': 'image/png' } });
}

function isTileHost(u){
  var h = u.hostname;
  return h === 'ibasemaps-api.arcgis.com'   // Esri World Imagery
      || h === 'tiles.maps.eox.at'          // Sentinel-2 cloudless
      || h.indexOf('tile.openstreetmap.org') !== -1; // OSM (a/b/c subdomains)
}
function isElevHost(u){
  var h = u.hostname;
  return h === 'api.open-meteo.com' || h === 'elevation3d.arcgis.com';
}

self.addEventListener('install', function(event){
  event.waitUntil((async function(){
    var cache = await caches.open(SHELL);
    await cache.addAll(SHELL_CORE);
    // grids: cache each individually, never let one failure abort install
    await Promise.all(SHELL_BIG.map(function(u){
      return cache.add(u).catch(function(){ return null; });
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', function(event){
  event.waitUntil((async function(){
    var names = await caches.keys();
    await Promise.all(names.map(function(n){
      if (n.indexOf('surveylsd-') === 0 && n !== SHELL && n !== TILES && n !== DATA){
        return caches.delete(n);
      }
      return null;
    }));
    // ensure the runtime caches exist under the current names, so the page's
    // one-click downloader writes to exactly the cache this worker reads from
    await caches.open(TILES);
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

var trimming = false;
async function trimTiles(){
  if (trimming) return;
  trimming = true;
  try {
    var cache = await caches.open(TILES);
    var keys = await cache.keys();
    if (keys.length > TILE_MAX){
      var remove = keys.length - TILE_MAX;
      for (var i = 0; i < remove; i++) await cache.delete(keys[i]); // FIFO eviction
    }
  } catch (e) {}
  trimming = false;
}

async function tileFirst(req){
  var cache = await caches.open(TILES);
  var hit = await cache.match(req);
  if (hit) return hit;
  try {
    var res = await fetch(req);
    if (res && (res.ok || res.type === 'opaque')){
      cache.put(req, res.clone());
      trimTiles();
    }
    return res;
  } catch (e) {
    return blankTile();  // offline + never cached: show transparent instead of broken
  }
}

self.addEventListener('fetch', function(event){
  var req = event.request;
  if (req.method !== 'GET') return;
  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

  if (isTileHost(url)) { event.respondWith(tileFirst(req)); return; }
  if (isElevHost(url)) { event.respondWith(networkFirst(req, DATA)); return; }

  if (url.origin === self.location.origin){
    var isDoc = req.mode === 'navigate'
             || url.pathname.charAt(url.pathname.length - 1) === '/'
             || url.pathname.indexOf('.html') !== -1;
    if (isDoc) { event.respondWith(networkFirst(req, SHELL)); return; }  // get updates when online
    event.respondWith(cacheFirst(req, SHELL)); return;                  // libs, grids, icons
  }

  // any other cross-origin GET: try network, fall back to whatever we cached
  event.respondWith(fetch(req).catch(function(){ return caches.match(req); }));
});
