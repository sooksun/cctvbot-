"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import {
  Event,
  changeEventStatus,
  fetchEvidenceFileBlobUrl,
  getEvent,
  getEvidence,
  isAdmin,
  reviewEvent,
} from "@/lib/api";
import {
  EVENT_BANNER,
  eventTypeLabel,
  formatDateTime,
  severityClass,
  statusClass,
  statusLabel,
} from "@/lib/labels";

function EventDetailContent() {
  const params = useParams();
  const router = useRouter();
  const eventId = decodeURIComponent(String(params.eventId || ""));

  const [event, setEvent] = useState<Event | null>(null);
  const [evidenceMeta, setEvidenceMeta] = useState<{
    thumb: string | null;
    clip: string | null;
    relative_path: string;
    paths: Record<string, string | null>;
  } | null>(null);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const admin = isAdmin();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setThumbUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    try {
      const ev = await getEvent(eventId);
      setEvent(ev);
      if (admin) {
        try {
          const meta = await getEvidence(eventId);
          setEvidenceMeta({
            thumb: meta.thumb,
            clip: meta.clip,
            relative_path: meta.relative_path,
            paths: meta.paths,
          });
          if (meta.thumb === "thumb.jpg" || meta.thumb) {
            try {
              const url = await fetchEvidenceFileBlobUrl(eventId, "thumb.jpg");
              setThumbUrl(url);
            } catch {
              setThumbUrl(null);
            }
          }
        } catch {
          setEvidenceMeta(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดเหตุการณ์ไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [eventId, admin]);

  useEffect(() => {
    void load();
    return () => {
      setThumbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [load]);

  async function onReview(
    e: FormEvent,
    decision: "confirmed" | "false_positive",
  ) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await reviewEvent(eventId, decision, note.trim() || undefined);
      setEvent(updated);
      setMessage(
        decision === "confirmed"
          ? "ยืนยันเหตุแล้ว (ถ้าตั้งค่า LINE จะส่งข้อความแจ้งเตือน)"
          : "บันทึกว่าไม่ใช่เหตุแล้ว",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  async function onStatusChange(status: "action_taken" | "closed") {
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await changeEventStatus(
        eventId,
        status,
        note.trim() || undefined,
      );
      setEvent(updated);
      setMessage(
        status === "action_taken" ? "บันทึกว่าดำเนินการแล้ว" : "ปิดเคสแล้ว",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <div className="flex items-center justify-between gap-3">
          <Link
            href="/"
            className="text-sm text-blue-600 hover:underline"
          >
            ← กลับรายการ
          </Link>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-white"
          >
            รีเฟรช
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">กำลังโหลด...</p>
        ) : error && !event ? (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : event ? (
          <>
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-sm font-medium text-amber-900">
                {EVENT_BANNER}
              </p>
              <p className="mt-1 text-sm text-amber-800">
                {event.message_th || EVENT_BANNER}
              </p>
            </div>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h1 className="text-lg font-semibold text-slate-900">
                รายละเอียดเหตุการณ์
              </h1>
              <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">รหัสเหตุการณ์</dt>
                  <dd className="font-mono text-xs text-slate-800">
                    {event.event_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">สถานะ</dt>
                  <dd>
                    <span
                      className={`inline-block rounded border px-2 py-0.5 text-xs ${statusClass(
                        event.status,
                      )}`}
                    >
                      {statusLabel(event.status)}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">กล้อง</dt>
                  <dd className="text-slate-800">{event.camera_id}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">ประเภท</dt>
                  <dd className="text-slate-800">
                    {eventTypeLabel(event.event_type)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">ความรุนแรง</dt>
                  <dd>
                    <span
                      className={`inline-block rounded border px-2 py-0.5 text-xs ${severityClass(
                        event.severity,
                      )}`}
                    >
                      {event.severity}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">ความมั่นใจ</dt>
                  <dd className="text-slate-800">
                    {event.confidence != null
                      ? `${(event.confidence * 100).toFixed(0)}%`
                      : "-"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">ตรวจพบเมื่อ</dt>
                  <dd className="text-slate-800">
                    {formatDateTime(event.detected_at)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">เริ่ม / สิ้นสุด</dt>
                  <dd className="text-slate-800">
                    {formatDateTime(event.started_at)} —{" "}
                    {formatDateTime(event.ended_at)}
                  </dd>
                </div>
              </dl>

              {event.review ? (
                <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm">
                  <p className="font-medium text-slate-700">ผลการตรวจทาน</p>
                  <p className="mt-1 text-slate-600">
                    {statusLabel(event.review.decision || event.status)} โดย{" "}
                    {event.review.reviewed_by || "-"} ·{" "}
                    {formatDateTime(event.review.reviewed_at)}
                  </p>
                  {event.review.note ? (
                    <p className="mt-1 text-slate-600">
                      หมายเหตุ: {event.review.note}
                    </p>
                  ) : null}
                  {event.review.action_taken_by ? (
                    <p className="mt-1 text-slate-600">
                      ดำเนินการโดย {event.review.action_taken_by} ·{" "}
                      {formatDateTime(event.review.action_taken_at)}
                    </p>
                  ) : null}
                  {event.review.closed_by ? (
                    <p className="mt-1 text-slate-600">
                      ปิดเคสโดย {event.review.closed_by} ·{" "}
                      {formatDateTime(event.review.closed_at)}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-slate-900">
                หลักฐาน
              </h2>
              {event.evidence ? (
                <div className="mt-3 space-y-3">
                  {thumbUrl ? (
                    <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={thumbUrl}
                        alt="ภาพย่อหลักฐาน"
                        className="max-h-72 w-full object-contain"
                      />
                    </div>
                  ) : admin && event.evidence.thumb ? (
                    <p className="text-xs text-slate-400">
                      ไม่พบไฟล์ภาพย่อบนเซิร์ฟเวอร์
                    </p>
                  ) : null}
                  <ul className="space-y-1 text-sm text-slate-600">
                    <li>
                      โฟลเดอร์:{" "}
                      <code className="text-xs">
                        {event.evidence.relative_path || "-"}
                      </code>
                    </li>
                    <li>ภาพย่อ: {event.evidence.thumb || "-"}</li>
                    <li>คลิป: {event.evidence.clip || "-"}</li>
                    {evidenceMeta?.paths?.thumb ? (
                      <li className="text-xs text-slate-400">
                        เส้นทางเซิร์ฟเวอร์ (admin): {evidenceMeta.paths.thumb}
                      </li>
                    ) : null}
                  </ul>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">ไม่มีข้อมูลหลักฐาน</p>
              )}
              <p className="mt-3 text-xs text-slate-400">
                ไฟล์วิดีโอ/ภาพเก็บบนเซิร์ฟเวอร์โรงเรียนเท่านั้น
                ไม่เผยแพร่ภายนอก
              </p>
            </section>

            {admin && event.status === "pending_review" ? (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-slate-900">
                  ตรวจทาน (แอดมิน)
                </h2>
                <form className="mt-3 space-y-3">
                  <label className="block text-sm text-slate-600">
                    หมายเหตุ (ถ้ามี)
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      rows={3}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      placeholder="บันทึกเพิ่มเติม..."
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={(e) => void onReview(e, "confirmed")}
                      className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      ยืนยันเหตุ
                    </button>
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={(e) => void onReview(e, "false_positive")}
                      className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                    >
                      ไม่ใช่เหตุ
                    </button>
                  </div>
                </form>
              </section>
            ) : null}

            {admin &&
            ["confirmed", "action_taken", "false_positive"].includes(
              event.status,
            ) ? (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-slate-900">
                  จัดการเคส (แอดมิน)
                </h2>
                <label className="mt-3 block text-sm text-slate-600">
                  หมายเหตุ (ถ้ามี)
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="รายละเอียดการดำเนินการ..."
                  />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  {event.status === "confirmed" ? (
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => void onStatusChange("action_taken")}
                      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      ดำเนินการแล้ว
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={() => void onStatusChange("closed")}
                    className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    ปิดเคส
                  </button>
                </div>
              </section>
            ) : null}

            {!admin ? (
              <p className="text-sm text-slate-500">
                บัญชีผู้ชมสามารถดูรายละเอียดได้เท่านั้น ไม่สามารถตรวจทานได้
              </p>
            ) : null}

            {message ? (
              <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">
                {message}
              </p>
            ) : null}
            {error ? (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            ) : null}

            <div className="pt-2">
              <button
                type="button"
                onClick={() => router.push("/")}
                className="text-sm text-slate-500 hover:text-slate-800"
              >
                กลับหน้าหลัก
              </button>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}

export default function EventDetailPage() {
  return (
    <AuthGate>
      <EventDetailContent />
    </AuthGate>
  );
}
