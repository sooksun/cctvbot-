import { describe, expect, it } from "vitest";

import {
  EVENT_TYPES,
  EVENT_TYPE_LABELS,
  eventTypeLabel,
  formatDateTime,
  severityClass,
  statusClass,
  statusLabel,
} from "@/lib/labels";

describe("labels", () => {
  it("maps known status to Thai and falls back to the raw value", () => {
    expect(statusLabel("pending_review")).toBe("รอตรวจสอบ");
    expect(statusLabel("confirmed")).toBe("ยืนยันเหตุ");
    expect(statusLabel("weird")).toBe("weird");
  });

  it("maps event types with fallback", () => {
    expect(eventTypeLabel("person_after_hours")).toBe("บุคคลนอกเวลา");
    expect(eventTypeLabel("unknown_type")).toBe("unknown_type");
  });

  it("EVENT_TYPES equals the label keys", () => {
    expect(EVENT_TYPES).toEqual(Object.keys(EVENT_TYPE_LABELS));
    expect(EVENT_TYPES).toContain("possible_fight");
  });

  it("severity/status classes return tailwind strings", () => {
    expect(severityClass("critical")).toContain("red");
    expect(statusClass("closed")).toContain("green");
    expect(severityClass("weird")).toContain("slate");
  });

  it("formatDateTime handles null", () => {
    expect(formatDateTime(null)).toBe("-");
  });
});
