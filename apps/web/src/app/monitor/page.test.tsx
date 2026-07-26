import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listCameras = vi.fn();
vi.mock("@/lib/api", () => ({
  listCameras: () => listCameras(),
  isAdmin: () => false,
}));
vi.mock("@/hooks/useCameraSnapshot", () => ({
  useCameraSnapshot: () => ({ url: null, error: true, refresh: vi.fn() }),
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
});
