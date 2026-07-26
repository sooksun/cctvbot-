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

// How often to poll for the inner <video> element (created asynchronously
// inside the web component's shadow DOM).
const READY_POLL_INTERVAL_MS = 400;

// After playback has started, how often to sample currentTime for the stall
// watchdog.
const STALL_CHECK_INTERVAL_MS = 1000;

// How long currentTime may stay stuck (while not paused/ended) before a
// previously-playing stream is treated as permanently dead. Kept generous so
// normal brief buffering or go2rtc's own quick reconnect (which resumes
// currentTime on its own) doesn't trip a false fallback to the snapshot.
const STALL_TIMEOUT_MS = 12000;

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
    // `settled` is the single terminal flag: only fail() ever sets it, so
    // onError fires at most once across all paths (module load, never-started
    // timeout, post-success video error, post-success stall). `playing`
    // tracks whether succeed() has already run so it doesn't restart its own
    // watchdog if the ready-poll callback somehow ticks again.
    let settled = false;
    let playing = false;
    let el: VideoStreamElement | null = null;
    let failTimer: ReturnType<typeof setTimeout> | null = null;
    let readyPoll: ReturnType<typeof setInterval> | null = null;
    let stallWatch: ReturnType<typeof setInterval> | null = null;

    const clearTimers = () => {
      if (failTimer) {
        clearTimeout(failTimer);
        failTimer = null;
      }
      if (readyPoll) {
        clearInterval(readyPoll);
        readyPoll = null;
      }
      if (stallWatch) {
        clearInterval(stallWatch);
        stallWatch = null;
      }
    };

    const fail = () => {
      if (settled) return;
      settled = true;
      clearTimers();
      onError?.();
    };

    // Once the stream has started playing, keep watching it: a stream can
    // die well after its first frame, and the tile still needs to fall back
    // to a snapshot in that case.
    const succeed = (video: HTMLVideoElement) => {
      if (settled || playing) return;
      playing = true;
      clearTimers();
      video.controls = false;

      let lastCurrentTime = video.currentTime;
      let stalledMs = 0;
      stallWatch = setInterval(() => {
        if (video.paused || video.ended) {
          stalledMs = 0;
          return;
        }
        if (video.currentTime > lastCurrentTime) {
          lastCurrentTime = video.currentTime;
          stalledMs = 0;
          return;
        }
        stalledMs += STALL_CHECK_INTERVAL_MS;
        if (stalledMs >= STALL_TIMEOUT_MS) {
          fail();
        }
      }, STALL_CHECK_INTERVAL_MS);
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
        // as soon as it exists. That handler stays wired after succeed() so
        // a stream that dies later (post-success) still triggers fail().
        readyPoll = setInterval(() => {
          const video = el?.querySelector("video");
          if (!video) return;
          video.onerror = fail;
          if (video.readyState >= 2) {
            succeed(video);
          }
        }, READY_POLL_INTERVAL_MS);
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
