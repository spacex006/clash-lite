#!/usr/bin/env python3
"""
main.py — orchestrator اصلی پایپلاین.

ترتیب اجرا:
  ① fetch     → URI های خام از همه سورس‌ها
  ② parse     → تبدیل به proxy dict
  ③ dedup     → حذف تکراری سنگین (UUID / IP / name)
  ④ fix       → اصلاح REALITY short-id و سایر مشکلات
  ⑤ tcp_test  → تست موازی + مرتب‌سازی بر اساس latency
  ⑥ convert   → ساخت Clash YAML (AUTO + MANUAL)
  ⑦ validate  → اعتبارسنجی خروجی
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# ── تنظیمات ──────────────────────────────────────────────────────────────────
URLS_FILE    = Path("urls.txt")
CONFIGS_TXT  = Path("output/configs.txt")
PROFILE_YAML = Path("output/profile.yaml")

# ── گزینه‌های dedup ───────────────────────────────────────────────────────────
from core.deduplicator import DedupConfig
DEDUP_CFG = DedupConfig(
    uuid_dedup       = False,  # True = یک UUID در کل خروجی (برای CDN off کن)
    server_port_dedup= True,   # True = یک کانفیگ به ازای هر server:port
    name_dedup       = False,  # True = نام‌های یکسان حذف شوند
    tcp_test         = True,   # True = تست TCP و حذف مرده‌ها
    tcp_timeout      = 3.0,    # ثانیه
    tcp_workers      = 120,    # thread موازی
)

# ──────────────────────────────────────────────────────────────────────────────

def _banner(step: str, n: int = 0) -> None:
    suffix = f"  ({n:,})" if n else ""
    print(f"\n{'─'*52}")
    print(f"  {step}{suffix}")
    print(f"{'─'*52}")


def main() -> int:
    start = datetime.now(timezone.utc)
    print(f"🚀  clash-lite pipeline — {start.strftime('%Y-%m-%d %H:%M UTC')}")

    # ── imports داخلی ─────────────────────────────────────────────────────────
    from core.fetcher      import read_url_list, fetch_all
    from core.parser       import parse_many
    from core.deduplicator import deduplicate, tcp_filter_and_sort, unique_names
    from core.fixer        import fix_all
    from core.converter    import build_config, write_yaml
    from core.validator    import print_report

    # ─────────────────────────────────────────────────────────────────────────
    # ① Fetch
    # ─────────────────────────────────────────────────────────────────────────
    if not URLS_FILE.exists():
        print(f"❌  {URLS_FILE} یافت نشد.", file=sys.stderr)
        return 1

    urls = read_url_list(str(URLS_FILE))
    _banner("① FETCH", len(urls))

    raw_uris = fetch_all(urls)
    print(f"  جمع URI های دریافتی: {len(raw_uris):,}")

    if not raw_uris:
        print("⚠  هیچ URI ای دریافت نشد.", file=sys.stderr)
        return 1

    # ─────────────────────────────────────────────────────────────────────────
    # ② Parse
    # ─────────────────────────────────────────────────────────────────────────
    _banner("② PARSE", len(raw_uris))
    proxies, parse_errors = parse_many(raw_uris)
    print(f"  پارس موفق : {len(proxies):,}")
    print(f"  رد شده   : {parse_errors:,}")

    # ─────────────────────────────────────────────────────────────────────────
    # ③ Dedup
    # ─────────────────────────────────────────────────────────────────────────
    _banner("③ DEDUP (uuid/ip/name)")
    before = len(proxies)
    proxies = deduplicate(proxies, DEDUP_CFG)
    print(f"  قبل از dedup : {before:,}")
    print(f"  بعد از dedup : {len(proxies):,}  (−{before - len(proxies):,})")

    # ─────────────────────────────────────────────────────────────────────────
    # ④ Fix
    # ─────────────────────────────────────────────────────────────────────────
    _banner("④ FIX (REALITY short-id + …)")
    proxies, n_fixes = fix_all(proxies)
    print(f"  اصلاحات انجام‌شده: {n_fixes}")

    # ─────────────────────────────────────────────────────────────────────────
    # ⑤ TCP Test & Sort
    # ─────────────────────────────────────────────────────────────────────────
    if DEDUP_CFG.tcp_test:
        _banner("⑤ TCP TEST + SORT", len(proxies))
        alive, dead = tcp_filter_and_sort(
            proxies,
            timeout = DEDUP_CFG.tcp_timeout,
            workers = DEDUP_CFG.tcp_workers,
        )
        print(f"  زنده : {len(alive):,}  |  مرده : {len(dead):,}")
        proxies = alive
    else:
        print("\n⑤ TCP TEST  →  غیرفعال (DEDUP_CFG.tcp_test = False)")

    if not proxies:
        print("⚠  هیچ proxy زنده‌ای نماند.", file=sys.stderr)
        return 1

    # ─────────────────────────────────────────────────────────────────────────
    # یکتاسازی نام‌ها (پس از sort)
    # ─────────────────────────────────────────────────────────────────────────
    proxies = unique_names(proxies)

    # ─────────────────────────────────────────────────────────────────────────
    # ⑥ ذخیره configs.txt
    # ─────────────────────────────────────────────────────────────────────────
    _banner("⑥ SAVE configs.txt", len(proxies))
    CONFIGS_TXT.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    uris_out = [p.get("_uri", "") for p in proxies if p.get("_uri")]
    CONFIGS_TXT.write_text(
        f"# Updated: {now_str} | Count: {len(uris_out)}\n"
        + "\n".join(uris_out) + "\n",
        encoding="utf-8",
    )
    print(f"  ✅  ذخیره شد → {CONFIGS_TXT}")

    # ─────────────────────────────────────────────────────────────────────────
    # ⑦ Convert → Clash YAML
    # ─────────────────────────────────────────────────────────────────────────
    _banner("⑦ CONVERT → Clash YAML")
    config = build_config(proxies)
    write_yaml(config, PROFILE_YAML, len(proxies))
    print(f"  ✅  ذخیره شد → {PROFILE_YAML}")

    # ─────────────────────────────────────────────────────────────────────────
    # ⑧ Validate
    # ─────────────────────────────────────────────────────────────────────────
    _banner("⑧ VALIDATE YAML")
    ok = print_report(PROFILE_YAML)

    # ─────────────────────────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start).seconds
    print(f"✅  پایپلاین تمام شد در {elapsed}s  |  {len(proxies):,} proxy")
    print(f"   configs.txt → {CONFIGS_TXT}")
    print(f"   profile.yaml → {PROFILE_YAML}\n")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
