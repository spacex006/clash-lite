"""
debug.py — پیدا کردن همه proxy های مشکوک REALITY
"""

import yaml
from pathlib import Path
import json

PROFILE = Path("output/profile.yaml")

raw = PROFILE.read_text(encoding="utf-8")
yaml_text = "\n".join(ln for ln in raw.splitlines() if not ln.startswith("#"))
config = yaml.safe_load(yaml_text)

proxies = config.get("proxies", [])
print(f"کل proxy ها: {len(proxies)}\n")

# پیدا کردن همه proxy های مشکوک
suspicious = []

for i, p in enumerate(proxies):
    if p.get("type") != "vless":
        continue
    ro = p.get("reality-opts")
    if not isinstance(ro, dict):
        continue
    
    sid = ro.get("short-id", "")
    pbk = ro.get("public-key", "")
    
    issues = []
    
    # چک نوع
    if not isinstance(sid, str):
        issues.append(f"NOT_STRING (type={type(sid).__name__}, value={sid!r})")
    else:
        if not sid:
            issues.append("EMPTY")
        elif not all(c in "0123456789abcdefABCDEF" for c in sid):
            issues.append(f"NON_HEX: {sid!r}")
        elif len(sid) % 2 != 0:
            issues.append(f"ODD_LENGTH: {sid!r} (len={len(sid)})")
        elif len(sid) > 16:
            issues.append(f"TOO_LONG: {sid!r} (len={len(sid)})")
    
    if not isinstance(pbk, str) or not pbk:
        issues.append("PBK_INVALID")
    
    if issues:
        suspicious.append((i+1, p.get('name', '?')[:50], sid, issues))

print(f"تعداد proxy مشکوک: {len(suspicious)}")
print("=" * 70)

for num, name, sid, issues in suspicious:
    print(f"\n#{num} | {name}")
    print(f"  short-id: {sid!r}  type={type(sid).__name__}")
    for issue in issues:
        print(f"  ⚠ {issue}")

if not suspicious:
    print("\n✅ هیچ proxy مشکوکی پیدا نشد!")
    print("\nنکته: FClash ممکنه از proxy های دیگه (غیر REALITY) هم شکایت کنه")
    print("لطفاً یه نمونه از proxy های REALITY رو نشون بده:\n")
    
    count = 0
    for i, p in enumerate(proxies):
        if p.get("type") == "vless" and isinstance(p.get("reality-opts"), dict):
            print(f"#{i+1}: {json.dumps(p, ensure_ascii=False, default=str)}")
            count += 1
            if count >= 3:
                break
