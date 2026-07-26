"use client";

import { useCallback, useEffect, useState } from "react";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import {
  Camera,
  fetchCameraSnapshotUrl,
  isAdmin,
  listCameras,
  updateCamera,
} from "@/lib/api";

function CameraCard({ cam, onSaved }: { cam: Camera; onSaved: () => void }) {
  const [snap, setSnap] = useState<string | null>(null);
  const [name, setName] = useState(cam.name);
  const [zone, setZone] = useState(cam.zone ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadSnap = useCallback(async () => {
    setErr(null);
    try {
      const url = await fetchCameraSnapshotUrl(cam.camera_id);
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch {
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setErr("ไม่มีภาพจากกล้อง");
    }
  }, [cam.camera_id]);

  useEffect(() => {
    void loadSnap();
    const t = setInterval(() => void loadSnap(), 5000);
    return () => {
      clearInterval(t);
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [loadSnap]);

  async function save(patch: {
    name?: string;
    zone?: string | null;
    enabled?: boolean;
  }) {
    setBusy(true);
    setErr(null);
    try {
      await updateCamera(cam.camera_id, patch);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "บันทึกไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 aspect-video overflow-hidden rounded-lg bg-slate-100">
        {snap ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={snap}
            alt={`ภาพ ${cam.name}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {err ?? "กำลังโหลด..."}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              cam.is_online ? "bg-green-500" : "bg-red-500"
            }`}
          />
          <code className="text-xs text-slate-500">{cam.camera_id}</code>
          {!cam.enabled ? (
            <span className="rounded bg-slate-200 px-1.5 text-xs text-slate-600">
              ปิดเฝ้าระวัง
            </span>
          ) : null}
        </span>
        <button
          type="button"
          onClick={() => void loadSnap()}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          รีเฟรชภาพ
        </button>
      </div>
      <div className="mt-3 space-y-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900"
          placeholder="ชื่อกล้อง"
        />
        <input
          value={zone}
          onChange={(e) => setZone(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900"
          placeholder="โซน"
        />
        <div className="flex items-center justify-between">
          <button
            type="button"
            disabled={busy}
            onClick={() => void save({ name, zone: zone || null })}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            บันทึก
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void save({ enabled: !cam.enabled })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              cam.enabled
                ? "border border-slate-300 text-slate-700 hover:bg-slate-50"
                : "bg-green-600 text-white hover:bg-green-700"
            }`}
          >
            {cam.enabled ? "ปิดเฝ้าระวัง" : "เปิดเฝ้าระวัง"}
          </button>
        </div>
        {err ? <p className="text-xs text-red-600">{err}</p> : null}
      </div>
    </div>
  );
}

function CamerasContent() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const admin = isAdmin();

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

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <h1 className="text-lg font-semibold text-slate-900">จัดการกล้อง</h1>
        {!admin ? (
          <p className="text-sm text-slate-500">เฉพาะแอดมินเท่านั้น</p>
        ) : error ? (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : loading ? (
          <p className="text-sm text-slate-500">กำลังโหลด...</p>
        ) : cameras.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีกล้องในระบบ</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cameras.map((cam) => (
              <CameraCard
                key={cam.camera_id}
                cam={cam}
                onSaved={() => void load()}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function CamerasPage() {
  return (
    <AuthGate>
      <CamerasContent />
    </AuthGate>
  );
}
