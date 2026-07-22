"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import {
  Camera,
  Event,
  EventFilters,
  listCameras,
  listEvents,
} from "@/lib/api";
import {
  EVENT_BANNER,
  EVENT_TYPES,
  STATUS_OPTIONS,
  eventTypeLabel,
  formatDateTime,
  severityClass,
  statusClass,
  statusLabel,
} from "@/lib/labels";

function DashboardContent() {
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [filters, setFilters] = useState<EventFilters>({
    status: "pending_review",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ev, cams] = await Promise.all([
        listEvents(filters),
        listCameras(),
      ]);
      setEvents(ev);
      setCameras(cams);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            สถานะกล้อง
          </h2>
          {cameras.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">
              ยังไม่มีกล้องในระบบ
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {cameras.map((cam) => (
                <div
                  key={cam.camera_id}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm"
                >
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      cam.is_online ? "bg-green-500" : "bg-red-500"
                    }`}
                    title={cam.is_online ? "ออนไลน์" : "ออฟไลน์"}
                  />
                  <span className="font-medium text-slate-800">{cam.name}</span>
                  <span className="text-xs text-slate-400">{cam.camera_id}</span>
                  {cam.zone ? (
                    <span className="rounded bg-slate-100 px-1.5 text-xs text-slate-500">
                      {cam.zone}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-3">
            <h2 className="text-base font-semibold text-slate-900">
              รายการเหตุการณ์
            </h2>
            <p className="text-sm text-slate-500">
              ข้อความแจ้งเตือนใช้คำว่า &ldquo;{EVENT_BANNER}&rdquo; เท่านั้น
            </p>
          </div>

          <div className="flex flex-wrap gap-3 border-b border-slate-100 px-4 py-3">
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              สถานะ
              <select
                value={filters.status || ""}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    status: e.target.value || undefined,
                  }))
                }
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                <option value="">ทั้งหมด</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-xs text-slate-500">
              กล้อง
              <select
                value={filters.camera_id || ""}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    camera_id: e.target.value || undefined,
                  }))
                }
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                <option value="">ทั้งหมด</option>
                {cameras.map((c) => (
                  <option key={c.camera_id} value={c.camera_id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-xs text-slate-500">
              ประเภทเหตุ
              <select
                value={filters.event_type || ""}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    event_type: e.target.value || undefined,
                  }))
                }
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                <option value="">ทั้งหมด</option>
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {eventTypeLabel(t)}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-end">
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                รีเฟรช
              </button>
            </div>
          </div>

          {error ? (
            <p className="px-4 py-3 text-sm text-red-600">{error}</p>
          ) : null}

          {loading ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">
              กำลังโหลด...
            </p>
          ) : events.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">
              ไม่พบเหตุการณ์ตามตัวกรอง
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">เวลา</th>
                    <th className="px-4 py-2 font-medium">กล้อง</th>
                    <th className="px-4 py-2 font-medium">ประเภท</th>
                    <th className="px-4 py-2 font-medium">ความรุนแรง</th>
                    <th className="px-4 py-2 font-medium">สถานะ</th>
                    <th className="px-4 py-2 font-medium">ข้อความ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {events.map((ev) => (
                    <tr key={ev.event_id} className="hover:bg-slate-50/80">
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">
                        <Link
                          href={`/events/${encodeURIComponent(ev.event_id)}`}
                          className="text-blue-600 hover:underline"
                        >
                          {formatDateTime(ev.detected_at || ev.created_at)}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {ev.camera_id}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {eventTypeLabel(ev.event_type)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded border px-2 py-0.5 text-xs ${severityClass(
                            ev.severity,
                          )}`}
                        >
                          {ev.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded border px-2 py-0.5 text-xs ${statusClass(
                            ev.status,
                          )}`}
                        >
                          {statusLabel(ev.status)}
                        </span>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-slate-600">
                        <Link
                          href={`/events/${encodeURIComponent(ev.event_id)}`}
                          className="hover:text-blue-700"
                          title={ev.message_th || EVENT_BANNER}
                        >
                          {ev.message_th || EVENT_BANNER}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default function HomePage() {
  return (
    <AuthGate>
      <DashboardContent />
    </AuthGate>
  );
}
