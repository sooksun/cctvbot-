import type { ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const listCameras = vi.fn();
vi.mock("@/lib/api", () => ({
  listCameras: () => listCameras(),
  isAdmin: () => false,
}));
let snapshotMock: () => {
  url: string | null;
  error: boolean;
  refresh: () => void;
  lastUpdated: number | null;
} = () => ({ url: null, error: true, refresh: vi.fn(), lastUpdated: null });
vi.mock("@/hooks/useCameraSnapshot", () => ({
  useCameraSnapshot: () => snapshotMock(),
}));
vi.mock("@/components/AuthGate", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/AppHeader", () => ({ default: () => <div /> }));

import MonitorPage from "@/app/monitor/page";

const CAMS = [
  {
    camera_id: "gate_front",
    name: "กล้องหน้า",
    stream_type: "ip",
    zone: "gate",
    is_online: true,
    enabled: true,
    last_seen_at: null,
    created_at: null,
  },
  {
    camera_id: "yard_1",
    name: "สนาม",
    stream_type: "ip",
    zone: "yard",
    is_online: false,
    enabled: false,
    last_seen_at: null,
    created_at: null,
  },
];

describe("MonitorPage", () => {
  beforeEach(() => {
    listCameras.mockReset();
    listCameras.mockResolvedValue(CAMS);
    snapshotMock = () => ({
      url: null,
      error: true,
      refresh: vi.fn(),
      lastUpdated: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a tile per camera including offline/disabled", async () => {
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    expect(screen.getByText("สนาม")).toBeInTheDocument();
    expect(screen.getByText("ปิดเฝ้าระวัง")).toBeInTheDocument();
    expect(screen.getByText("ออฟไลน์")).toBeInTheDocument();
  });

  it("opens fullscreen on tile click and closes on Escape", async () => {
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /กล้องหน้า/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows the last-updated time when the snapshot is fresh", async () => {
    const ts = 1700000000000;
    snapshotMock = () => ({
      url: "blob:x",
      error: false,
      refresh: vi.fn(),
      lastUpdated: ts,
    });
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    expect(screen.getAllByText(/อัปเดตเมื่อ/).length).toBeGreaterThan(0);
  });

  it("marks a stale frame when error is true but a previous url still exists", async () => {
    snapshotMock = () => ({
      url: "blob:x",
      error: true,
      refresh: vi.fn(),
      lastUpdated: null,
    });
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    expect(screen.getAllByText(/ภาพไม่อัปเดต/).length).toBeGreaterThan(0);
  });

  it("shows both the stale badge and the last-updated time for a stale frame", async () => {
    const ts = 1700000000000;
    snapshotMock = () => ({
      url: "blob:x",
      error: true,
      refresh: vi.fn(),
      lastUpdated: ts,
    });
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    expect(screen.getAllByText(/ภาพไม่อัปเดต/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/อัปเดตเมื่อ/).length).toBeGreaterThan(0);
  });

  it("re-polls the camera list after LIST_REFRESH_MS and survives a transient re-poll error", async () => {
    vi.useFakeTimers();
    listCameras.mockReset();
    listCameras.mockResolvedValueOnce(CAMS);

    render(<MonitorPage />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(listCameras).toHaveBeenCalledTimes(1);
    expect(screen.getByText("กล้องหน้า")).toBeInTheDocument();

    listCameras.mockRejectedValueOnce(new Error("transient"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(listCameras).toHaveBeenCalledTimes(2);
    // transient re-poll error must not blank the grid
    expect(screen.getByText("กล้องหน้า")).toBeInTheDocument();

    listCameras.mockResolvedValueOnce(CAMS);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(listCameras).toHaveBeenCalledTimes(3);
  });

  it("clears the re-poll interval on unmount (no further listCameras calls, no setState-after-unmount)", async () => {
    vi.useFakeTimers();
    listCameras.mockReset();
    listCameras.mockResolvedValue(CAMS);

    const { unmount } = render(<MonitorPage />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(listCameras).toHaveBeenCalledTimes(1);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(listCameras).toHaveBeenCalledTimes(1);
  });
});
