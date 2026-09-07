const CACHE = "weight-app-v2";
const SHELL = [
  "/offline",
  "/static/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  event.respondWith(
    fetch(request).catch(() => caches.match(request).then(r => r || caches.match("/offline")))
  );
});

self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  const title = data.title || "선수 체중관리";
  const options = {
    body: data.body || "체중 기록을 확인해 주세요.",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: {url: data.url || "/"},
    vibrate: [100, 50, 100]
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
      const target = event.notification.data?.url || "/";
      for (const client of list) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
