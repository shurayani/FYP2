// IPECS service worker - makes the app installable.
// IPECS needs a live connection to the computer it runs on, so pages are NOT cached for offline use.
// Only a small "cannot reach IPECS" page is kept, shown when that computer is off or out of reach.
const CACHE = "ipecs-pwa-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => c.add("/offline.html"))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;      // data, images and the live connection go straight to the network
  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match("/offline.html").then((r) => r || new Response("IPECS is not reachable.", {status: 503}))
    )
  );
});
