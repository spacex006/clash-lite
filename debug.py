"""
debug.py — پیدا کردن proxy خاص با شماره
"""

import yaml
from pathlib import Path

PROFILE = Path("output/profile.yaml")

raw = PROFILE.read_text(encoding="utf-8")
yaml_text = "\n".join(ln for ln in raw.splitlines() if not ln.startswith("#"))
config = yaml.safe_load(yaml_text)

proxies = config.get("proxies", [])
print(f"کل proxy ها: {len(proxies)}\n")

# proxy های مشکوک: همه vless با reality
print("=" * 70)
print("بررسی همه vless+reality:")
print("=" * 70)

for i, p in enumerate(proxies):
    if p.get("type") != "vless":
        continue
    ro = p.get("reality-opts")
    if not isinstance(ro, dict):
        continue
    
    sid = ro.get("short-id", "")
    pbk = ro.get("public-key", "")
    
    # نمایش اطلاعات
    sid_type = type(sid).__name__
    sid_repr = repr(sid)
    
    print(f"\n#{i} | {p.get('name', '?')[:40]}")
    print(f"  short-id: {sid_repr}  (type={sid_type}, len={len(str(sid))})")
    print(f"  pbk: {pbk[:30]}...")
    
    # هشدارها
    if not sid:
        print("  ⚠ short-id خالی!")
    elif not isinstance(sid, str):
        print(f"  ⚠ short-id غیر string! (تبدیل اتومتیک PyYAML)")
    elif not all(c in "0123456789abcdefABCDEF" for c in sid):
        print(f"  ⚠ short-id کاراکتر غیر hex داره!")
    elif len(sid) % 2 != 0:
        print(f"  ⚠ short-id طول فرد داره!")
    elif len(sid) > 16:
        print(f"  ⚠ short-id بیش از 16 کاراکتر!")

print("\n" + "=" * 70)
print("بررسی proxy شماره 2224 (index 2223):")
print("=" * 70)

if len(proxies) >= 2224:
    p = proxies[2223]
    import json
    print(json.dumps(p, indent=2, ensure_ascii=False, default=str))
