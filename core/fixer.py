"""
fixer.py — اصلاح خودکار فیلدهای مشکل‌دار در proxy dict.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# REALITY short-id
# ──────────────────────────────────────────────────────────────────────────────

_MAX_SID_HEX  = 16
_SID_CHARS_RE = re.compile(r"^[0-9a-fA-F]+$")


def fix_reality_short_id(sid) -> Tuple[str, bool]:
    if sid is None:
        sid = ""
    if not isinstance(sid, str):
        sid = str(sid)

    original = sid
    clean = re.sub(r"[^0-9a-fA-F]", "", sid).lower()

    if len(clean) % 2 != 0:
        clean = clean[:-1]
    if len(clean) > _MAX_SID_HEX:
        clean = clean[:_MAX_SID_HEX]

    changed = (clean != original.lower())
    return clean, changed


def is_valid_short_id(sid: str) -> bool:
    if not isinstance(sid, str):
        return False
    if len(sid) == 0:
        return False
    return (
        bool(_SID_CHARS_RE.match(sid))
        and len(sid) % 2 == 0
        and len(sid) <= _MAX_SID_HEX
    )


# ──────────────────────────────────────────────────────────────────────────────
# VMess cipher
# ──────────────────────────────────────────────────────────────────────────────

VALID_VMESS_CIPHERS = frozenset({
    "auto", "aes-128-gcm", "chacha20-poly1305",
    "none", "zero",
})


def fix_vmess_cipher(cipher) -> Tuple[str, bool]:
    clean = str(cipher or "").strip().lower()
    if clean in VALID_VMESS_CIPHERS:
        return clean, (clean != str(cipher or "").strip())
    return "auto", True


# ──────────────────────────────────────────────────────────────────────────────
# Shadowsocks cipher
# ──────────────────────────────────────────────────────────────────────────────

# مقادیر معتبر cipher برای Shadowsocks در Mihomo/Clash
VALID_SS_CIPHERS = frozenset({
    # AEAD (پیشنهادی)
    "aes-128-gcm", "aes-192-gcm", "aes-256-gcm",
    "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
    # AEAD 2022
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
    # Stream (legacy)
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr",
    "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "rc4-md5", "chacha20-ietf", "xchacha20",
    # سایر
    "none", "plain",
})

# نگاشت مقادیر اشتباه به معتبر
_SS_ALIASES = {
    "auto":                    "aes-256-gcm",
    "chacha20":                "chacha20-ietf-poly1305",
    "chacha20-poly1305":       "chacha20-ietf-poly1305",
    "aes-256-poly1305":        "aes-256-gcm",
}


def fix_ss_cipher(cipher) -> Tuple[str, bool]:
    """
    اصلاح cipher Shadowsocks.
    اگر معتبر بود → بدون تغییر
    اگر در alias بود → نگاشت
    در غیر اینصورت → None برمی‌گرداند (proxy باید حذف شود)
    """
    raw = str(cipher or "").strip()
    clean = raw.lower()

    if clean in VALID_SS_CIPHERS:
        return clean, (clean != raw)

    if clean in _SS_ALIASES:
        return _SS_ALIASES[clean], True

    # نامعتبر — برمی‌گرداند رشته خالی تا در post_fix_filter حذف شود
    return "", True


# ──────────────────────────────────────────────────────────────────────────────
# اصلاح یک proxy
# ──────────────────────────────────────────────────────────────────────────────

def fix_proxy(p: Dict) -> Tuple[Dict, List[str]]:
    p = dict(p)
    changes: List[str] = []
    name = p.get("name", "?")

    # ── ① REALITY short-id ──────────────────────────────────────────────────
    ro = p.get("reality-opts")
    if isinstance(ro, dict):
        ro = dict(ro)
        raw_sid = ro.get("short-id", "")
        fixed_sid, changed = fix_reality_short_id(raw_sid)

        if changed or raw_sid != fixed_sid:
            changes.append(
                f"[{name}] reality short-id: {raw_sid!r} → {fixed_sid!r}"
            )

        if fixed_sid:
            ro["short-id"] = fixed_sid
        else:
            ro.pop("short-id", None)

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

    # ── ②-b Shadowsocks cipher ──────────────────────────────────────────────
    if p.get("type") == "ss":
        raw_cipher = p.get("cipher", "")
        fixed_cipher, changed = fix_ss_cipher(raw_cipher)
        if changed:
            changes.append(
                f"[{name}] ss cipher: {raw_cipher!r} → {fixed_cipher!r}"
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
    raw_name = p.get("name", "")
    clean_name = re.sub(r"[\x00-\x1f\x7f]", "", raw_name)
    if clean_name != raw_name:
        p["name"] = clean_name or "proxy"
        changes.append(f"[{name}] کاراکتر کنترلی در نام حذف شد")

    return p, changes


def fix_all(proxies: List[Dict]) -> Tuple[List[Dict], int]:
    result = []
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
# فیلتر نهایی
# ──────────────────────────────────────────────────────────────────────────────

def post_fix_filter(proxies: List[Dict]) -> Tuple[List[Dict], List[str]]:
    valid: List[Dict] = []
    removed: List[str] = []

    for p in proxies:
        name = p.get("name", "?")
        ptype = p.get("type", "")
        issue = None

        # ── REALITY ─────────────────────────────────────────────────────
        ro = p.get("reality-opts")
        if isinstance(ro, dict):
            pbk = str(ro.get("public-key", "")).strip()
            if not pbk:
                issue = "REALITY: public-key خالی است"
            else:
                sid = ro.get("short-id", "")
                if not sid or not is_valid_short_id(str(sid)):
                    issue = f"REALITY short-id نامعتبر: {sid!r}"

        # ── VMess cipher ────────────────────────────────────────────────
        if not issue and ptype == "vmess":
            cipher = str(p.get("cipher", "")).strip()
            if cipher not in VALID_VMESS_CIPHERS:
                issue = f"vmess cipher نامعتبر: {cipher!r}"

        # ── Shadowsocks cipher ──────────────────────────────────────────
        if not issue and ptype == "ss":
            cipher = str(p.get("cipher", "")).strip().lower()
            if not cipher or cipher not in VALID_SS_CIPHERS:
                issue = f"ss cipher نامعتبر: {cipher!r}"

        # ── server و port ───────────────────────────────────────────────
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
