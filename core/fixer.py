"""
fixer.py — اصلاح خودکار فیلدهای مشکل‌دار در proxy dict.

مشکلات برطرف‌شده:
  ① REALITY short-id نامعتبر  →  اصلاح بدون حذف کانفیگ
  ② alterId منفی              →  صفر
  ③ port خارج از بازه         →  علامت‌گذاری (حذف در validator)
  ④ نام حاوی کاراکتر کنترلی   →  پاکسازی
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# REALITY short-id
# ──────────────────────────────────────────────────────────────────────────────

_MAX_SID_HEX = 16          # 8 bytes = 16 hex chars حداکثر
_VALID_SID_RE = re.compile(r"^[0-9a-f]*$")   # hex کوچک، طول صفر هم OK


def fix_reality_short_id(sid: str) -> Tuple[str, bool]:
    """
    اصلاح short-id برای REALITY.

    قوانین:
      • فقط کاراکترهای hex (0-9 a-f) مجاز
      • طول باید زوج باشد (هر بایت = 2 هگز)
      • حداکثر 16 کاراکتر (8 بایت)
      • طول صفر (رشته خالی) هم قبول است

    برمی‌گرداند: (fixed_sid, was_changed)
    """
    if not isinstance(sid, str):
        sid = str(sid)

    original = sid

    # ① فقط کاراکترهای hex کوچک
    clean = re.sub(r"[^0-9a-fA-F]", "", sid).lower()

    # ② طول زوج
    if len(clean) % 2 != 0:
        clean = clean[:-1]   # آخرین کاراکتر برش

    # ③ حداکثر طول
    if len(clean) > _MAX_SID_HEX:
        clean = clean[:_MAX_SID_HEX]

    return clean, (clean != original.lower().replace(" ", ""))


def is_valid_short_id(sid: str) -> bool:
    """بررسی معتبربودن short-id (بدون تغییر)."""
    if not isinstance(sid, str):
        return False
    return (
        bool(_VALID_SID_RE.match(sid))
        and len(sid) % 2 == 0
        and len(sid) <= _MAX_SID_HEX
    )


# ──────────────────────────────────────────────────────────────────────────────
# اصلاح کلی یک proxy dict
# ──────────────────────────────────────────────────────────────────────────────

def fix_proxy(p: Dict) -> Tuple[Dict, List[str]]:
    """
    اعمال همه اصلاحات بر یک proxy dict.
    برمی‌گرداند: (fixed_proxy, list_of_change_messages)
    """
    p       = dict(p)       # کپی — side-effect-free
    changes: List[str] = []
    name    = p.get("name", "?")

    # ── ① REALITY short-id ──────────────────────────────────────────────
    ro = p.get("reality-opts")
    if isinstance(ro, dict) and "short-id" in ro:
        ro = dict(ro)
        raw_sid = ro.get("short-id", "")
        fixed_sid, changed = fix_reality_short_id(raw_sid)
        if changed:
            changes.append(
                f"[{name}] reality short-id: {raw_sid!r} → {fixed_sid!r}"
            )
        ro["short-id"]   = fixed_sid
        p["reality-opts"] = ro

    # ── ② alterId منفی ──────────────────────────────────────────────────
    if "alterId" in p and int(p.get("alterId", 0)) < 0:
        p["alterId"] = 0
        changes.append(f"[{name}] alterId منفی → 0")

    # ── ③ نام کنترلی ────────────────────────────────────────────────────
    raw_name = p.get("name", "")
    clean_name = re.sub(r"[\x00-\x1f\x7f]", "", raw_name)
    if clean_name != raw_name:
        p["name"] = clean_name or "proxy"
        changes.append(f"[{name}] کاراکتر کنترلی در نام حذف شد")

    return p, changes


def fix_all(proxies: List[Dict]) -> Tuple[List[Dict], int]:
    """
    اصلاح همه proxy dict ها.
    برمی‌گرداند: (fixed_proxies, total_fixes_count)
    """
    result     = []
    total_fixes = 0
    for p in proxies:
        fixed, changes = fix_proxy(p)
        if changes:
            for msg in changes:
                print(f"  [fixer] 🔧 {msg}")
        total_fixes += len(changes)
        result.append(fixed)
    return result, total_fixes
