"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearSession, getRole, getUsername } from "@/lib/api";

export default function AppHeader() {
  const router = useRouter();
  const username = getUsername();
  const role = getRole();

  function logout() {
    clearSession();
    router.replace("/login");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-lg font-semibold text-slate-900">
            ระบบเฝ้าระวัง CCTV โรงเรียน
          </Link>
          <span className="hidden text-xs text-slate-500 sm:inline">
            ตรวจทานเหตุการณ์ภายใน
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link
            href="/monitor"
            className="hidden text-slate-600 hover:text-slate-900 sm:inline"
          >
            จอมอนิเตอร์
          </Link>
          {role === "admin" ? (
            <Link
              href="/cameras"
              className="hidden text-slate-600 hover:text-slate-900 sm:inline"
            >
              จัดการกล้อง
            </Link>
          ) : null}
          <Link
            href="/account"
            className="hidden text-slate-600 hover:text-slate-900 sm:inline"
          >
            เปลี่ยนรหัสผ่าน
          </Link>
          <span className="text-slate-600">
            {username}
            {role ? (
              <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                {role}
              </span>
            ) : null}
          </span>
          <button
            type="button"
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50"
          >
            ออกจากระบบ
          </button>
        </div>
      </div>
    </header>
  );
}
