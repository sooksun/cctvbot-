import { render, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
