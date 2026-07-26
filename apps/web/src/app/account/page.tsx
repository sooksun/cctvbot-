"use client";

import { FormEvent, useState } from "react";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import { changePassword } from "@/lib/api";

function AccountContent() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (next.length < 8) {
      setError("รหัสใหม่ต้องยาวอย่างน้อย 8 ตัวอักษร");
      return;
    }
    if (next !== confirm) {
      setError("ยืนยันรหัสใหม่ไม่ตรงกัน");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(current, next);
      setMessage("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เปลี่ยนรหัสผ่านไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  const field =
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500";

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-md space-y-4 px-4 py-6">
        <h1 className="text-lg font-semibold text-slate-900">เปลี่ยนรหัสผ่าน</h1>
        <form
          onSubmit={onSubmit}
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <label className="block text-sm text-slate-600">
            รหัสผ่านปัจจุบัน
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              className={field}
            />
          </label>
          <label className="block text-sm text-slate-600">
            รหัสผ่านใหม่ (อย่างน้อย 8 ตัวอักษร)
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              className={field}
            />
          </label>
          <label className="block text-sm text-slate-600">
            ยืนยันรหัสผ่านใหม่
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className={field}
            />
          </label>
          {error ? (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">
              {message}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {submitting ? "กำลังบันทึก..." : "บันทึกรหัสผ่านใหม่"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default function AccountPage() {
  return (
    <AuthGate>
      <AccountContent />
    </AuthGate>
  );
}
