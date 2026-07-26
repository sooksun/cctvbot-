import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchSnapshot = vi.fn();
vi.mock("@/lib/api", () => ({
  fetchCameraSnapshotUrl: (id: string) => fetchSnapshot(id),
}));

import { useCameraSnapshot } from "@/hooks/useCameraSnapshot";

describe("useCameraSnapshot", () => {
  beforeEach(() => {
    fetchSnapshot.mockReset();
    fetchSnapshot.mockResolvedValue("blob:fake-url");
    vi.stubGlobal("URL", {
      ...URL,
      revokeObjectURL: vi.fn(),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches a snapshot on mount and exposes the url", async () => {
    const { result } = renderHook(() => useCameraSnapshot("cam1", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    expect(fetchSnapshot).toHaveBeenCalledWith("cam1");
  });

  it("sets error=true when the fetch rejects", async () => {
    fetchSnapshot.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useCameraSnapshot("cam2", 2000));
    await waitFor(() => expect(result.current.error).toBe(true));
  });

  it("revokes the object URL on unmount", async () => {
    const { result, unmount } = renderHook(() => useCameraSnapshot("cam3", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });
});
