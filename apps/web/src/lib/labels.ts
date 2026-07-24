export const EVENT_BANNER = "พบเหตุที่ควรตรวจสอบ";

export const STATUS_LABELS: Record<string, string> = {
  pending_review: "รอตรวจสอบ",
  confirmed: "ยืนยันเหตุ",
  false_positive: "ไม่ใช่เหตุ",
  action_taken: "ดำเนินการแล้ว",
  closed: "ปิดแล้ว",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  person_after_hours: "บุคคลนอกเวลา",
  person_restricted_zone: "บุคคลในพื้นที่หวงห้าม",
  person_fall_or_down: "บุคคลล้ม/นอนลง",
  camera_offline: "กล้องออฟไลน์",
  camera_tamper: "กล้องถูกปิดบัง/ย้าย",
  abnormal_motion: "การเคลื่อนไหวผิดปกติ",
  abnormal_crowd: "ฝูงชนผิดปกติ",
  possible_littering: "ทิ้งขยะ (น่าสงสัย)",
  possible_fight: "ทะเลาะวิวาท (น่าสงสัย)",
};

export const EVENT_TYPES = Object.keys(EVENT_TYPE_LABELS);

export const STATUS_OPTIONS = [
  "pending_review",
  "confirmed",
  "false_positive",
  "action_taken",
  "closed",
];

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

export function eventTypeLabel(type: string): string {
  return EVENT_TYPE_LABELS[type] || type;
}

export function severityClass(severity: string): string {
  switch (severity) {
    case "critical":
      return "bg-red-100 text-red-800 border-red-200";
    case "high":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "medium":
      return "bg-amber-100 text-amber-800 border-amber-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

export function statusClass(status: string): string {
  switch (status) {
    case "pending_review":
      return "bg-yellow-100 text-yellow-900 border-yellow-200";
    case "confirmed":
      return "bg-red-100 text-red-800 border-red-200";
    case "false_positive":
      return "bg-slate-100 text-slate-600 border-slate-200";
    case "action_taken":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "closed":
      return "bg-green-100 text-green-800 border-green-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("th-TH", {
      dateStyle: "short",
      timeStyle: "medium",
      timeZone: "Asia/Bangkok",
    });
  } catch {
    return iso;
  }
}
