import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCameraSnapshotUrl } from "@/lib/api";

/**
 * Poll a camera's snapshot on an interval. Revokes prior object URLs, and
 * pauses polling while the browser tab is hidden (resumes + refreshes on show).
 */
export function useCameraSnapshot(
  cameraId: string,
  intervalMs: number,
): { url: string | null; error: boolean; refresh: () => void } {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const urlRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchCameraSnapshotUrl(cameraId);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = next;
      setUrl(next);
      setError(false);
    } catch {
      setError(true);
    }
  }, [cameraId]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      void refresh();
      timer = setInterval(() => void refresh(), intervalMs);
    };
    const stop = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [refresh, intervalMs]);

  return { url, error, refresh };
}
