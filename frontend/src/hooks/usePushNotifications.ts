/**
 * 푸시 알림 훅
 *
 * VAPID 키 획득 → 알림 권한 요청 → PushManager 구독 → 백엔드 등록
 */

import { useState, useCallback, useEffect } from "react";
import { apiCall } from "@/lib/auth";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export function usePushNotifications() {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const supported =
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window;
    setIsSupported(supported);

    if (supported) {
      navigator.serviceWorker.ready.then(async (registration) => {
        const subscription = await registration.pushManager.getSubscription();
        setIsSubscribed(!!subscription);
      });
    }
  }, []);

  const subscribe = useCallback(async () => {
    if (!isSupported) return;
    setIsLoading(true);

    try {
      // 1. 알림 권한 요청
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setIsLoading(false);
        return;
      }

      // 2. VAPID 공개 키 획득
      const response = await apiCall("/api/push/vapid-key");
      if (!response.ok) {
        setIsLoading(false);
        return;
      }
      const { public_key } = await response.json();

      // 3. PushManager 구독
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });

      // 4. 백엔드에 구독 등록
      const subJson = subscription.toJSON();
      await apiCall("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: subJson.endpoint,
          p256dh_key: subJson.keys?.p256dh ?? "",
          auth_key: subJson.keys?.auth ?? "",
        }),
      });

      setIsSubscribed(true);
    } catch (error) {
      console.error("Push subscription failed:", error);
    } finally {
      setIsLoading(false);
    }
  }, [isSupported]);

  const unsubscribe = useCallback(async () => {
    if (!isSupported) return;
    setIsLoading(true);

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe();

        // 백엔드에서 구독 해제
        await apiCall("/api/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint }),
        });
      }

      setIsSubscribed(false);
    } catch (error) {
      console.error("Push unsubscription failed:", error);
    } finally {
      setIsLoading(false);
    }
  }, [isSupported]);

  return {
    isSubscribed,
    isSupported,
    isLoading,
    subscribe,
    unsubscribe,
  };
}
