from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
# Asia/Bangkok has no DST; fixed offset works without tzdata package on Windows.
BANGKOK = timezone(timedelta(hours=7))

EVENT_TYPE_TH: dict[str, str] = {
    "person_after_hours": "บุคคลนอกเวลา",
    "person_restricted_zone": "บุคคลในโซนหวงห้าม",
    "person_fall_or_down": "บุคคลล้ม/นอนนิ่ง",
    "camera_offline": "กล้องออฟไลน์",
    "camera_tamper": "กล้องถูกแทรกแซง",
    "abnormal_motion": "การเคลื่อนที่ผิดปกติ",
    "abnormal_crowd": "กลุ่มคนหนาแน่น",
    "possible_littering": "สงสัยทิ้งขยะ",
    "possible_fight": "สงสัยทะเลาะวิวาท",
}


def send_line_text(token: str, user_id: str, text: str) -> None:
    """Push a text-only LINE message (no images/clips)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text,
            }
        ],
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(LINE_PUSH_URL, headers=headers, json=payload)
        response.raise_for_status()


def _time_local(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BANGKOK).strftime("%H:%M")


def event_type_th(event_type: str, rule_json: Any = None) -> str:
    if isinstance(rule_json, dict):
        name = rule_json.get("name")
        if name:
            return str(name)
    return EVENT_TYPE_TH.get(event_type, event_type)


def build_confirm_line_text(
    *,
    camera_name: str,
    time_local: str,
    event_type_label: str,
    event_id: str,
) -> str:
    return (
        "[ยืนยันแล้ว] พบเหตุที่ควรตรวจสอบ\n"
        f"จุด: {camera_name} | เวลา: {time_local}\n"
        f"ประเภท: {event_type_label}\n"
        f"รหัส: {event_id}\n"
        "เปิดดูภาพได้ที่ระบบภายในเท่านั้น"
    )


def build_line_text_for_event(
    event: Any,
    camera_name: str,
) -> str:
    when = event.detected_at or event.started_at
    return build_confirm_line_text(
        camera_name=camera_name,
        time_local=_time_local(when),
        event_type_label=event_type_th(event.event_type, event.rule_json),
        event_id=event.event_id,
    )
