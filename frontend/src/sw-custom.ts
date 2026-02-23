/// <reference lib="webworker" />

import { precacheAndRoute, cleanupOutdatedCaches } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

// Workbox 프리캐시 매니페스트
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// push 이벤트: 알림 표시
self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload: {
    title?: string;
    body?: string;
    url?: string;
    icon?: string;
    badge?: string;
  };

  try {
    payload = event.data.json();
  } catch {
    payload = { title: "SENTIO", body: event.data.text() };
  }

  const options = {
    body: payload.body ?? "",
    icon: payload.icon ?? "/icon-192x192.png",
    badge: payload.badge ?? "/icon-192x192.png",
    vibrate: [200, 100, 200],
    requireInteraction: true,
    data: {
      url: payload.url ?? "/",
    },
    tag: "sentio-alert",
  };

  event.waitUntil(
    self.registration.showNotification(payload.title ?? "SENTIO", options),
  );
});

// notificationclick 이벤트: 대시보드 포커스/열기
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const url = (event.notification.data?.url as string) ?? "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
