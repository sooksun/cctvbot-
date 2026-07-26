import { act, renderHook, waitFor } from "@testing-library/react";
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
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
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

  it("lastUpdated is null before the first fetch resolves and a number after a successful fetch", async () => {
    let resolveFetch: (value: string) => void = () => {};
    fetchSnapshot.mockReset();
    fetchSnapshot.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const { result } = renderHook(() => useCameraSnapshot("cam5", 2000));

    expect(result.current.lastUpdated).toBeNull();

    resolveFetch("blob:fake-url");
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    expect(typeof result.current.lastUpdated).toBe("number");
  });

  it("does not update lastUpdated when the fetch rejects", async () => {
    fetchSnapshot.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useCameraSnapshot("cam6", 2000));
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.lastUpdated).toBeNull();
  });

  it("keeps the previous lastUpdated unchanged when a later fetch rejects", async () => {
    const { result } = renderHook(() => useCameraSnapshot("cam7", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    expect(typeof result.current.lastUpdated).toBe("number");
    const capturedValue = result.current.lastUpdated;

    fetchSnapshot.mockRejectedValueOnce(new Error("boom"));
    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.lastUpdated).toBe(capturedValue);
  });

  it("revokes the object URL on unmount", async () => {
    const { result, unmount } = renderHook(() => useCameraSnapshot("cam3", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });

  it("does not poll on mount while document.hidden is true, and resumes on visibilitychange", async () => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });

    renderHook(() => useCameraSnapshot("cam4", 2000));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchSnapshot).not.toHaveBeenCalled();

    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    await waitFor(() => expect(fetchSnapshot).toHaveBeenCalledWith("cam4"));
  });
});
