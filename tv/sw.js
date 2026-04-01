// NexVision IPTV — Service Worker cleanup
// This worker now self-destructs and clears old caches so admin routes cannot
// be shadowed by a stale cached TV app shell.

self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(key => caches.delete(key)));

    const registrations = await self.registration.unregister();
    await self.clients.claim();

    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) {
      client.navigate(client.url);
    }

    return registrations;
  })());
});
