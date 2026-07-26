"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";
import AppHeader from "@/components/AppHeader";
import AuthGate from "@/components/AuthGate";
import { Camera, listCameras } from "@/lib/api";
import { useCameraSnapshot } from "@/hooks/useCameraSnapshot";
import LiveVideo from "@/components/LiveVideo";

const REFRESH_MS = 2000;
const LIST_REFRESH_MS = 15000;

function formatUpdatedAt(lastUpdated: number | null): string | null {
  if (lastUpdated == null) return null;
  return `อัปเดตเมื่อ ${new Date(lastUpdated).toLocaleTimeString("th-TH")}`;
}

function StaleBadge() {
  return (
    <span className="rounded bg-amber-100 px-1.5 text-xs text-amber-800">
      ⚠ ภาพไม่อัปเดต
    </span>
  );
}

function StatusBadges({ cam }: { cam: Camera }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={`h-2.5 w-2.5 rounded-full ${
          cam.is_online ? "bg-green-500" : "bg-red-500"
        }`}
      />
      <span className="text-sm text-slate-800">{cam.name}</span>
      {!cam.enabled ? (
        <span className="rounded bg-slate-200 px-1.5 text-xs text-slate-600">
          ปิดเฝ้าระวัง
        </span>
      ) : null}
      {!cam.is_online ? (
        <span className="rounded bg-red-100 px-1.5 text-xs text-red-700">
          ออฟไลน์
        </span>
      ) : null}
    </span>
  );
}

function TileButton({
  cam,
  onExpand,
  children,
}: {
  cam: Camera;
  onExpand: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label={cam.name}
      className="overflow-hidden rounded-xl border border-slate-200 bg-white text-left shadow-sm hover:border-slate-300"
    >
      {children}
    </button>
  );
}

// Owns useCameraSnapshot so it only polls once live has failed for this tile
// — healthy live tiles never mount this, so they never poll the snapshot API.
function SnapshotFallback({
  cam,
  isExpanded,
  onExpand,
  onClose,
}: {
  cam: Camera;
  isExpanded: boolean;
  onExpand: () => void;
  onClose: () => void;
}) {
  const { url, error, lastUpdated } = useCameraSnapshot(cam.camera_id, REFRESH_MS);
  const stale = error && !!url;
  const updatedLabel = formatUpdatedAt(lastUpdated);
  return (
    <>
      <TileButton cam={cam} onExpand={onExpand}>
        <div className="aspect-video overflow-hidden bg-slate-100">
          {url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={url}
              alt={`ภาพ ${cam.name}`}
              className={`h-full w-full object-cover ${stale ? "opacity-50" : ""}`}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              {error ? "ไม่มีภาพจากกล้อง" : "กำลังโหลด..."}
            </div>
          )}
        </div>
        <div className="space-y-1 p-3">
          <StatusBadges cam={cam} />
          {stale ? <StaleBadge /> : null}
          {updatedLabel ? (
            <p className="text-xs text-slate-400">{updatedLabel}</p>
          ) : null}
        </div>
      </TileButton>
      {isExpanded ? (
        <FullscreenView
          cam={cam}
          url={url}
          error={error}
          lastUpdated={lastUpdated}
          onClose={onClose}
        />
      ) : null}
    </>
  );
}

function MonitorTile({
  cam,
  isExpanded,
  onExpand,
  onClose,
}: {
  cam: Camera;
  isExpanded: boolean;
  onExpand: () => void;
  onClose: () => void;
}) {
  const [liveFailed, setLiveFailed] = useState(false);
  const handleLiveError = useCallback(() => setLiveFailed(true), []);

  if (liveFailed) {
    return (
      <SnapshotFallback
        cam={cam}
        isExpanded={isExpanded}
        onExpand={onExpand}
        onClose={onClose}
      />
    );
  }

  return (
    <>
      <TileButton cam={cam} onExpand={onExpand}>
        <div className="aspect-video overflow-hidden bg-slate-100">
          <LiveVideo cameraId={cam.camera_id} onError={handleLiveError} />
        </div>
        <div className="space-y-1 p-3">
          <StatusBadges cam={cam} />
          <p className="text-xs font-medium text-red-600">🔴 สด</p>
        </div>
      </TileButton>
      {isExpanded ? (
        <FullscreenView
          cam={cam}
          url={null}
          error={false}
          lastUpdated={null}
          onClose={onClose}
        />
      ) : null}
    </>
  );
}

function FullscreenView({
  cam,
  url,
  error,
  lastUpdated,
  onClose,
}: {
  cam: Camera;
  url: string | null;
  error: boolean;
  lastUpdated: number | null;
  onClose: () => void;
}) {
  const stale = error && !!url;
  const updatedLabel = formatUpdatedAt(lastUpdated);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`ภาพเต็มจอ ${cam.name}`}
      onClick={onClose}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-4"
    >
      <div className="mb-2 text-sm text-white">{cam.name} — กด ESC เพื่อปิด</div>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={`ภาพเต็มจอ ${cam.name}`}
          className={`max-h-[85vh] max-w-full rounded-lg object-contain ${
            stale ? "opacity-50" : ""
          }`}
        />
      ) : (
        <div className="text-slate-300">
          {error ? "ไม่มีภาพจากกล้อง" : "กำลังโหลด..."}
        </div>
      )}
      {stale ? (
        <div className="mt-2">
          <StaleBadge />
        </div>
      ) : null}
      {updatedLabel ? (
        <div className="mt-2 text-xs text-slate-300">{updatedLabel}</div>
      ) : null}
    </div>
  );
}

function MonitorContent() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCameras(await listCameras());
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดกล้องไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      listCameras()
        .then((next) => setCameras(next))
        .catch(() => {
          // transient re-poll error: keep showing the last known list
        });
    }, LIST_REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <h1 className="text-lg font-semibold text-slate-900">จอมอนิเตอร์</h1>
        {error ? (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        ) : loading ? (
          <p className="text-sm text-slate-500">กำลังโหลด...</p>
        ) : cameras.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีกล้องในระบบ</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cameras.map((cam) => (
              <MonitorTile
                key={cam.camera_id}
                cam={cam}
                isExpanded={expandedId === cam.camera_id}
                onExpand={() => setExpandedId(cam.camera_id)}
                onClose={() => setExpandedId(null)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function MonitorPage() {
  return (
    <AuthGate>
      <MonitorContent />
    </AuthGate>
  );
}
