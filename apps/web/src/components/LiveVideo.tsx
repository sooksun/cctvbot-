"use client";

import { useEffect, useRef } from "react";

// Wraps go2rtc's vendored <video-stream> web component to play MSE.
// Dev default points at the standalone go2rtc; prod overrides via env
// (full WS base up to ?src=).
const WS_BASE =
  process.env.NEXT_PUBLIC_LIVE_WS_BASE || "ws://localhost:1984/api/ws";

// No frames within this window (inner <video> never reaching readyState >= 2)
// counts as a load failure.
const FAIL_TIMEOUT_MS = 10000;

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
    s.onerror = () => {
      // Allow a later mount to retry instead of failing forever on one blip.
      modulePromise = null;
      reject(new Error("failed to load video-stream.js"));
    };
    document.head.appendChild(s);
  });
  return modulePromise;
}

type VideoStreamElement = HTMLElement & { mode?: string; src?: string };

export default function LiveVideo({
  cameraId,
  onError,
}: {
  cameraId: string;
  onError?: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Guards onError so it fires at most once per mount, regardless of which
    // of the three failure paths (module load, video error, timeout) trips.
    let settled = false;
    let el: VideoStreamElement | null = null;
    let failTimer: ReturnType<typeof setTimeout> | null = null;
    let readyPoll: ReturnType<typeof setInterval> | null = null;

    const clearTimers = () => {
      if (failTimer) {
        clearTimeout(failTimer);
        failTimer = null;
      }
      if (readyPoll) {
        clearInterval(readyPoll);
        readyPoll = null;
      }
    };

    const fail = () => {
      if (settled) return;
      settled = true;
      clearTimers();
      onError?.();
    };

    const succeed = (video: HTMLVideoElement) => {
      if (settled) return;
      settled = true;
      clearTimers();
      video.controls = false;
    };

    ensureComponent()
      .then(() => {
        if (settled || !containerRef.current) return;

        el = document.createElement("video-stream") as VideoStreamElement;
        el.mode = "mse";
        el.style.width = "100%";
        el.style.height = "100%";
        el.style.display = "block";
        el.src = `${WS_BASE}?src=${encodeURIComponent(cameraId)}`;
        containerRef.current.appendChild(el);

        failTimer = setTimeout(fail, FAIL_TIMEOUT_MS);
        // Poll for the inner <video> since it's created inside the web
        // component's shadow DOM asynchronously; also wire its error event
        // as soon as it exists.
        readyPoll = setInterval(() => {
          const video = el?.querySelector("video");
          if (!video) return;
          video.onerror = fail;
          if (video.readyState >= 2) {
            succeed(video);
          }
        }, 400);
      })
      .catch(fail);

    return () => {
      settled = true;
      clearTimers();
      if (el && el.parentNode) {
        el.parentNode.removeChild(el);
      }
    };
  }, [cameraId, onError]);

  return <div ref={containerRef} className="h-full w-full bg-black" />;
}
