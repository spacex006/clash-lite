"""
fixer.py — اصلاح خودکار فیلدهای مشکل‌دار در proxy dict.

مشکلات برطرف‌شده:
  ① REALITY short-id نامعتبر  →  fix + normalize به lowercase
  ② VMess cipher خالی/نامعتبر  →  default به "auto"
  ③ alterId منفی              →  صفر
  ④ نام حاوی کاراکتر کنترلی   →  پاکسازی
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# REALITY short-id
# ──────────────────────────────────────────────────────────────────────────────

_MAX_SID_HEX  = 16          # 8 bytes = 16 hex chars
# ← هر دو حالت بزرگ/کوچک برای بررسی اولیه
_SID_CHARS_RE = re.compile(r"^[0-9a-fA-F]*$")


def fix_reality_short_id(sid) -> Tuple[str, bool]:
    """
    اصلاح و normalize کردن REALITY short-id.

    قوانین خروجی:
      • فقط hex lowercase (0-9 a-f)
      • طول زوج (هر بایت = 2 هگز)
      • حداکثر 16 کاراکتر (8 بایت)
      • طول صفر (رشته خالی) مجاز

    برمی‌گرداند: (fixed_sid, was_changed)
    """
    if sid is None:
        sid = ""
    if not isinstance(sid, str):
        sid = str(sid)

    original = sid

    # ① حذف همه کاراکترهای غیر-hex و تبدیل به lowercase
    clean = re.sub(r"[^0-9a-fA-F]", "", sid).lower()

    # ② طول زوج
    if len(clean) % 2 != 0:
        clean = clean[:-1]

    # ③ حداکثر طول
    if len(clean) > _MAX_SID_HEX:
        clean = clean[:_MAX_SID_HEX]

    # تغییر یافته اگر با نسخه نرمال‌شده اصلی متفاوت باشد
    changed = (clean != original.lower())
    return clean, changed


def is_valid_short_id(sid: str) -> bool:
    """بررسی معتبربودن short-id (هر دو حالت بزرگ/کوچک قبول)."""
    if not isinstance(sid, str):
        return False
    return (
        bool(_SID_CHARS_RE.match(sid))
        and len(sid) % 2 == 0
        and len(sid) <= _MAX_SID_HEX
    )


# ──────────────────────────────────────────────────────────────────────────────
# VMess cipher
# ──────────────────────────────────────────────────────────────────────────────

# مقادیر معتبر cipher برای VMess در Mihomo/Clash
VALID_VMESS_CIPHERS = frozenset({
    "auto", "aes-128-gcm", "chacha20-poly1305",
    "none", "zero",
})


def fix_vmess_cipher(cipher) -> Tuple[str, bool]:
    """
    اصلاح cipher VMess.
    هر مقداری که معتبر نباشد → 'auto'
    """
    clean = str(cipher or "").strip().lower()
    if clean in VALID_VMESS_CIPHERS:
        return clean, (clean != str(cipher or "").strip())
    return "auto", True


# ──────────────────────────────────────────────────────────────────────────────
# اصلاح کلی یک proxy dict
# ──────────────────────────────────────────────────────────────────────────────

def fix_proxy(p: Dict) -> Tuple[Dict, List[str]]:
    """
    اعمال همه اصلاحات بر یک proxy dict.
    برمی‌گرداند: (fixed_proxy, list_of_change_messages)
    """
    p       = dict(p)
    changes: List[str] = []
    name    = p.get("name", "?")

    # ── ① REALITY short-id ──────────────────────────────────────────────────
    # اجرا روی هر proxy ای که reality-opts دارد (حتی اگر short-id نداشته باشد)
    ro = p.get("reality-opts")
    if isinstance(ro, dict):
        ro = dict(ro)                           # کپی nested dict
        raw_sid = ro.get("short-id", "")        # اگر نبود "" پیش‌فرض
        fixed_sid, changed = fix_reality_short_id(raw_sid)

        if changed or raw_sid != fixed_sid:     # هر تغییری (شامل case-normalize)
            changes.append(
                f"[{name}] reality short-id: {raw_sid!r} → {fixed_sid!r}"
            )

        ro["short-id"]    = fixed_sid           # همیشه set کن (lowercase)
        p["reality-opts"] = ro

    # ── ② VMess cipher ──────────────────────────────────────────────────────
    if p.get("type") == "vmess":
        raw_cipher = p.get("cipher", "")
        fixed_cipher, changed = fix_vmess_cipher(raw_cipher)
        if changed:
            changes.append(
                f"[{name}] vmess cipher: {raw_cipher!r} → {fixed_cipher!r}"
            )
        p["cipher"] = fixed_cipher

    # ── ③ alterId منفی ──────────────────────────────────────────────────────
    if "alterId" in p:
        try:
            aid = int(p["alterId"])
            if aid < 0:
                p["alterId"] = 0
                changes.append(f"[{name}] alterId {aid} → 0")
        except (TypeError, ValueError):
            p["alterId"] = 0

    # ── ④ نام کنترلی ────────────────────────────────────────────────────────
    raw_name  = p.get("name", "")
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
    result      = []
    total_fixes = 0
    for p in proxies:
        fixed, changes = fix_proxy(p)
        if changes:
            for msg in changes:
                print(f"  [fixer] 🔧 {msg}")
        total_fixes += len(changes)
        result.append(fixed)
    return result, total_fixes


# ──────────────────────────────────────────────────────────────────────────────
# فیلتر نهایی — حذف proxy هایی که بعد از fix هنوز نامعتبرند
# ──────────────────────────────────────────────────────────────────────────────

def post_fix_filter(proxies: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    آخرین خط دفاعی:
    هر proxy ای که بعد از fix هنوز مشکل داشته باشد حذف می‌شود.
    برمی‌گرداند: (valid_proxies, list_of_removed_reasons)
    """
    valid:   List[Dict] = []
    removed: List[str]  = []

    for p in proxies:
        name  = p.get("name", "?")
        ptype = p.get("type", "")
        issue = None

        # بررسی REALITY short-id
        ro = p.get("reality-opts")
        if isinstance(ro, dict):
            sid = ro.get("short-id", "")
            if not is_valid_short_id(str(sid or "")):
                issue = f"REALITY short-id نامعتبر بعد از fix: {sid!r}"

        # بررسی VMess cipher
        if not issue and ptype == "vmess":
            cipher = str(p.get("cipher", "")).strip()
            if cipher not in VALID_VMESS_CIPHERS:
                issue = f"vmess cipher نامعتبر بعد از fix: {cipher!r}"

        # بررسی server و port
        if not issue:
            try:
                port = int(p.get("port", 0))
                if not (1 <= port <= 65535) or not p.get("server"):
                    issue = f"server/port نامعتبر: {p.get('server')}:{port}"
            except (TypeError, ValueError):
                issue = f"port قابل تبدیل نیست: {p.get('port')!r}"

        if issue:
            msg = f"[{name}] ❌ حذف شد: {issue}"
            print(f"  [post-filter] {msg}")
            removed.append(msg)
        else:
            valid.append(p)

    return valid, removed
