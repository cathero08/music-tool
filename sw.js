const CACHE = "jukebox-v3";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  const isAppShell = url.origin === self.location.origin;
  const isGoogle = /google\.com$|\.google\.com$|\.googleusercontent\.com$/.test(url.hostname);
  const isYouTube = /youtube\.com$|\.youtube\.com$|youtu\.be$|ytimg\.com$|\.ytimg\.com$/.test(url.hostname);

  if (isGoogle || isYouTube) return;

  if (!isAppShell) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const fetched = fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return resp;
      }).catch(() => cached || caches.match("./index.html"));
      return cached || fetched;
    })
  );
});
