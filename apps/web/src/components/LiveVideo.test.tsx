import { render, act } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LiveVideo from "@/components/LiveVideo";

// Pretend the web component is already registered so the module-load path resolves.
beforeEach(() => {
  vi.useFakeTimers();
  (window.customElements as unknown as { get: (n: string) => unknown }).get = () => class {};
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("mounts a video-stream with an mse src built from the camera id", async () => {
  const { container } = render(<LiveVideo cameraId="gate_front" />);
  await act(async () => { await Promise.resolve(); });
  const el = container.querySelector("video-stream") as HTMLElement & { src?: string; mode?: string };
  expect(el).not.toBeNull();
  expect(el.mode).toBe("mse");
  expect(el.src).toContain("?src=gate_front");
});

it("calls onError when no frames arrive within the timeout", async () => {
  const onError = vi.fn();
  render(<LiveVideo cameraId="gate_front" onError={onError} />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { vi.advanceTimersByTime(10000); });
  expect(onError).toHaveBeenCalledTimes(1);
});

// Simulates the inner <video> (normally created inside the web component's
// shadow DOM) reaching readyState >= 2, which is what the ready-poll looks
// for to consider the stream successfully started.
async function playToSuccess(container: HTMLElement) {
  const el = container.querySelector("video-stream") as HTMLElement;
  const video = document.createElement("video");
  Object.defineProperty(video, "readyState", { value: 2, configurable: true });
  Object.defineProperty(video, "currentTime", { value: 0, configurable: true, writable: true });
  Object.defineProperty(video, "paused", { value: false, configurable: true });
  Object.defineProperty(video, "ended", { value: false, configurable: true });
  el.appendChild(video);
  await act(async () => { vi.advanceTimersByTime(400); });
  return video;
}

it("falls back to snapshot when the stream dies after it starts playing", async () => {
  const onError = vi.fn();
  const { container } = render(<LiveVideo cameraId="gate_front" onError={onError} />);
  await act(async () => { await Promise.resolve(); });

  const video = await playToSuccess(container);
  expect(onError).not.toHaveBeenCalled();

  // A never-started timeout must not fire now that we've succeeded.
  await act(async () => { vi.advanceTimersByTime(10000); });
  expect(onError).not.toHaveBeenCalled();

  // Stream permanently dies: the inner <video> fires its error event.
  await act(async () => {
    video.dispatchEvent(new Event("error"));
  });
  expect(onError).toHaveBeenCalledTimes(1);

  // Further error/stall activity must not call onError again.
  await act(async () => {
    video.dispatchEvent(new Event("error"));
    vi.advanceTimersByTime(20000);
  });
  expect(onError).toHaveBeenCalledTimes(1);
});

it("falls back to snapshot when currentTime stalls for a sustained window post-success", async () => {
  const onError = vi.fn();
  const { container } = render(<LiveVideo cameraId="gate_front" onError={onError} />);
  await act(async () => { await Promise.resolve(); });

  await playToSuccess(container);

  // currentTime never advances from here on (frozen stream), and the video
  // is neither paused nor ended.
  await act(async () => { vi.advanceTimersByTime(12000); });
  expect(onError).toHaveBeenCalledTimes(1);
});

it("does not fall back for a brief stall that recovers before the threshold", async () => {
  const onError = vi.fn();
  const { container } = render(<LiveVideo cameraId="gate_front" onError={onError} />);
  await act(async () => { await Promise.resolve(); });

  const video = await playToSuccess(container);

  // Stall for less than the threshold, then resume progress (mimics go2rtc's
  // own quick reconnect resuming currentTime).
  await act(async () => { vi.advanceTimersByTime(8000); });
  expect(onError).not.toHaveBeenCalled();

  Object.defineProperty(video, "currentTime", { value: 5, configurable: true, writable: true });
  await act(async () => { vi.advanceTimersByTime(1000); });

  // Even after further time passes, no stale stall should have accumulated
  // across the recovery.
  await act(async () => { vi.advanceTimersByTime(8000); });
  expect(onError).not.toHaveBeenCalled();
});
