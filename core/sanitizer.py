"""
sanitizer.py — پاکسازی عمیق تمام فیلدهای proxy dict از کاراکترهای کنترلی.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# کاراکترهای کنترلی که YAML قبول نمی‌کنه
# شامل: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F, 0x7F
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_str(s: str) -> str:
    """حذف کاراکترهای کنترلی از یک رشته."""
    return _CTRL_RE.sub("", s)


def _sanitize_value(val: Any) -> Any:
    """
    پاکسازی بازگشتی هر نوع مقدار:
    - str → حذف کنترلی
    - dict → پاکسازی همه مقادیر
    - list → پاکسازی همه آیتم‌ها
    - بقیه → بدون تغییر
    """
    if isinstance(val, str):
        return _clean_str(val)
    elif isinstance(val, dict):
        return {k: _sanitize_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_sanitize_value(i) for i in val]
    return val


def sanitize_proxy(p: Dict) -> Tuple[Dict, bool]:
    """
    پاکسازی عمیق یک proxy dict.
    برمی‌گرداند: (clean_proxy, was_changed)
    """
    clean = {}
    changed = False
    for k, v in p.items():
        new_v = _sanitize_value(v)
        clean[k] = new_v
        if new_v != v:
            changed = True
    return clean, changed


def sanitize_all(proxies: List[Dict]) -> Tuple[List[Dict], int]:
    """
    پاکسازی همه proxy dict ها.
    برمی‌گرداند: (clean_proxies, تعداد_تغییرها)
    """
    result = []
    total = 0
    for p in proxies:
        clean, changed = sanitize_proxy(p)
        if changed:
            print(f"  [sanitizer] 🧹 کاراکتر کنترلی حذف شد: {p.get('name', '?')}")
            total += 1
        result.append(clean)
    return result, total
