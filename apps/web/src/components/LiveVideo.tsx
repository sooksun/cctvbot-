"use client";

import { useEffect, useRef } from "react";

// SPIKE: wraps go2rtc's vendored <video-stream> web component to play MSE.
// Dev default points at the standalone go2rtc; prod overrides via env
// (full WS base up to ?src=).
const WS_BASE =
  process.env.NEXT_PUBLIC_LIVE_WS_BASE || "ws://localhost:1984/api/ws";

let modulePromise: Promise<void> | null = null;
function ensureComponent(): Promise<void> {
  if (typeof window !== "undefined" && customElements.get("video-stream")) {
    return Promise.resolve();
  }
  if (modulePromise) return modulePromise;
  modulePromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.type = "module";
    s.src = "/vendor/go2rtc/video-stream.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("failed to load video-stream.js"));
    document.head.appendChild(s);
  });
  return modulePromise;
}

export default function LiveVideo({
  cameraId,
  onError,
}: {
  cameraId: string;
  onError?: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let el: HTMLElement | null = null;
    let failTimer: ReturnType<typeof setTimeout> | null = null;
    let readyPoll: ReturnType<typeof setInterval> | null = null;

    const fail = () => {
      if (cancelled) return;
      cancelled = true;
      onError?.();
    };

    ensureComponent()
      .then(() => {
        if (cancelled || !containerRef.current) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        el = document.createElement("video-stream") as any;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (el as any).mode = "mse";
        el.style.width = "100%";
        el.style.height = "100%";
        el.style.display = "block";
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (el as any).src = `${WS_BASE}?src=${encodeURIComponent(cameraId)}`;
        containerRef.current.appendChild(el);

        // Fallback if no frames within 10s.
        failTimer = setTimeout(fail, 10000);
        // Success once the inner <video> has data; also catch its error event.
        readyPoll = setInterval(() => {
          const video = el?.querySelector("video");
          if (!video) return;
          if (video.readyState >= 2) {
            if (failTimer) clearTimeout(failTimer);
            if (readyPoll) clearInterval(readyPoll);
            video.controls = false;
          }
          video.onerror = fail;
        }, 400);
      })
      .catch(fail);

    return () => {
      cancelled = true;
      if (failTimer) clearTimeout(failTimer);
      if (readyPoll) clearInterval(readyPoll);
      if (el && el.parentNode) el.parentNode.removeChild(el);
    };
  }, [cameraId, onError]);

  return <div ref={containerRef} className="h-full w-full bg-black" />;
}
