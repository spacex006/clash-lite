"""
mihomo_validator.py — اعتبارسنجی proxy ها با Mihomo core.

فقط چک میکنه که Mihomo بتونه config رو parse کنه.
proxy های ناسازگار حذف میشن. بدون HTTP test (سریع).
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# ──────────────────────────────────────────────────────────────────────────────
# تنظیمات
# ──────────────────────────────────────────────────────────────────────────────

MIHOMO_CONFIG = Path("/tmp/mihomo_validate_config.yaml")
MIHOMO_API    = "http://127.0.0.1:9091"   # پورت متفاوت از CC
STARTUP_WAIT  = 20    # ثانیه


# ──────────────────────────────────────────────────────────────────────────────
# پیدا کردن binary mihomo
# ──────────────────────────────────────────────────────────────────────────────

def _find_mihomo() -> Path:
    candidates = [
        Path.cwd() / "mihomo",
        Path("./mihomo").resolve(),
        Path("/usr/local/bin/mihomo"),
        Path("/usr/bin/mihomo"),
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()
    return Path.cwd() / "mihomo"


# ──────────────────────────────────────────────────────────────────────────────
# ساخت config
# ──────────────────────────────────────────────────────────────────────────────

def _build_config(proxies: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """ساخت config برای Mihomo + یکتاسازی نام‌ها."""
    clean: List[Dict] = []
    seen_names: Dict[str, int] = {}

    for p in proxies:
        cp = {k: v for k, v in p.items() if not k.startswith("_")}
        original_name = cp.get("name", "proxy")
        name = original_name
        if name in seen_names:
            seen_names[name] += 1
            name = f"{original_name}#{seen_names[original_name]}"
            cp["name"] = name
            # در proxy اصلی هم تغییر بده
            p["name"] = name
        else:
            seen_names[name] = 0
        clean.append(cp)

    names = [p["name"] for p in clean]

    config = {
        "mixed-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "external-controller": "127.0.0.1:9091",
        "proxies": clean,
        "proxy-groups": [{
            "name": "VALIDATE",
            "type": "select",
            "proxies": names if names else ["DIRECT"],
        }],
        "rules": ["MATCH,VALIDATE"],
    }
    return config, clean


# ──────────────────────────────────────────────────────────────────────────────
# نوشتن config با quoted strings
# ──────────────────────────────────────────────────────────────────────────────

def _write_config(config: Dict) -> None:
    class QuotedStr(str):
        pass

    def quoted_str_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")

    yaml.add_representer(QuotedStr, quoted_str_representer)

    def wrap_sensitive(obj):
        if isinstance(obj, dict):
            new = {}
            for k, v in obj.items():
                if k in ("short-id", "public-key", "uuid", "password") and isinstance(v, str):
                    new[k] = QuotedStr(v)
                else:
                    new[k] = wrap_sensitive(v)
            return new
        elif isinstance(obj, list):
            return [wrap_sensitive(i) for i in obj]
        return obj

    safe_config = wrap_sensitive(config)
    MIHOMO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    MIHOMO_CONFIG.write_text(
        yaml.dump(safe_config, allow_unicode=True, sort_keys=False, width=4096),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────────────────────────────────────
# اجرای Mihomo و تشخیص proxy های مشکل‌دار
# ──────────────────────────────────────────────────────────────────────────────

_PROXY_ERROR_RE = re.compile(r'proxy[\s:]+(.+?)[\s:]+', re.IGNORECASE)


def _try_start(proxies: List[Dict]) -> Tuple[bool, List[str]]:
    """
    تلاش برای start کردن Mihomo.
    اگر موفق بود → (True, [])
    اگر crash کرد → (False, [اسم proxy های مشکل‌دار])
    """
    bin_path = _find_mihomo()
    if not bin_path.exists():
        print(f"  [mihomo-val] ❌ binary پیدا نشد: {bin_path}")
        return True, []   # mihomo نصب نیست، رد شو

    config, _ = _build_config(proxies)
    _write_config(config)

    proc = subprocess.Popen(
        [str(bin_path), "-f", str(MIHOMO_CONFIG), "-d", "/tmp/mihomo_val_data"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # صبر برای start
    bad_proxies: List[str] = []
    for _ in range(STARTUP_WAIT * 2):
        try:
            urllib.request.urlopen(f"{MIHOMO_API}/version", timeout=2).read()
            # موفق start شد
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            return True, []
        except Exception:
            time.sleep(0.5)

        # چک کن آیا کرش کرده
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode(errors="replace")
            stderr = proc.stderr.read().decode(errors="replace")
            combined = stdout + "\n" + stderr

            # پیدا کردن خطاهای proxy
            # مثل: "proxy XYZ is the duplicate name"
            # یا: "proxy ABC: invalid ..."
            for line in combined.splitlines():
                if "proxy" in line.lower() and ("error" in line.lower() or "invalid" in line.lower() or "duplicate" in line.lower()):
                    m = re.search(r'proxy\s+([^\s:]+(?:\s+[^\s:]+)*?)\s*(?:is|:|invalid)', line, re.IGNORECASE)
                    if m:
                        bad_proxies.append(m.group(1).strip())
                    else:
                        # تلاش دیگه برای استخراج
                        m2 = re.search(r'proxy\s+["\']?(.+?)["\']?\s', line)
                        if m2:
                            bad_proxies.append(m2.group(1).strip())

            if bad_proxies:
                print(f"  [mihomo-val] ⚠ کرش با {len(bad_proxies)} proxy مشکل‌دار")
                for bp in bad_proxies[:5]:
                    print(f"    • {bp}")
            else:
                # کرش با دلیل نامعلوم - آخرین خطا رو نشون بده
                print(f"  [mihomo-val] ⚠ Mihomo کرش کرد بدون شناسایی proxy خاص")
                last_err = combined[-500:] if combined else "(empty)"
                print(f"  [mihomo-val] خطا: {last_err}")

            return False, bad_proxies

    # تایم‌اوت
    print(f"  [mihomo-val] ⚠ Mihomo start نشد در {STARTUP_WAIT}s")
    try:
        proc.kill()
    except Exception:
        pass
    return False, []


# ──────────────────────────────────────────────────────────────────────────────
# تابع اصلی
# ──────────────────────────────────────────────────────────────────────────────

def validate_with_mihomo(proxies: List[Dict], max_retries: int = 5) -> List[Dict]:
    """
    Mihomo رو روی proxies اجرا میکنه. اگر crash کرد، proxy های مشکل‌دار رو
    حذف میکنه و دوباره تلاش میکنه. تا وقتی موفق بشه یا max_retries تموم بشه.
    """
    bin_path = _find_mihomo()
    if not bin_path.exists():
        print(f"  [mihomo-val] ⚠ Mihomo نصب نیست — رد میشه")
        return proxies

    if not proxies:
        return []

    current = list(proxies)

    for attempt in range(1, max_retries + 1):
        print(f"\n  [mihomo-val] تلاش {attempt}: validate {len(current)} proxy …")
        ok, bad_names = _try_start(current)

        if ok:
            print(f"  [mihomo-val] ✅ همه {len(current)} proxy معتبرند!")
            return current

        if not bad_names:
            print(f"  [mihomo-val] ⚠ نمیتونم proxy مشکل‌دار رو شناسایی کنم")
            print(f"  [mihomo-val] ⚠ خروجی فعلی رو نگه میدارم")
            return current

        # حذف proxy های مشکل‌دار
        before = len(current)
        bad_set = set(bad_names)
        current = [p for p in current if p.get("name") not in bad_set]
        removed = before - len(current)
        print(f"  [mihomo-val] 🗑 حذف {removed} proxy، باقی: {len(current)}")

        if not current:
            print(f"  [mihomo-val] ⚠ هیچ proxy ای نموند!")
            return []

    print(f"  [mihomo-val] ⚠ بعد از {max_retries} تلاش هنوز خطا")
    return current
