"use strict";
// Cache the UI shell only. Evidence files are NEVER cached or claimed to be live.
const CACHE = "janus-nexus-shell-v1";
const SHELL = ["./", "./index.html", "./styles.css", "./app.js", "./icon.svg", "./manifest.webmanifest"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(names => Promise.all(
    names.filter(name => name.startsWith("janus-nexus-shell-") && name !== CACHE)
      .map(name => caches.delete(name))
  )).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET" || req.mode === "navigate" && new URL(req.url).pathname.indexOf("/nexus/") === -1) return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.pathname.includes("/nexus/")) return;
  const path = url.pathname.split("/").pop();
  if (!["", "index.html", "styles.css", "app.js", "icon.svg", "manifest.webmanifest"].includes(path)) return;
  event.respondWith(fetch(req).then(response => {
    if (response.ok) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(req, copy)));
    }
    return response;
  }).catch(() => caches.match(req)));
});
