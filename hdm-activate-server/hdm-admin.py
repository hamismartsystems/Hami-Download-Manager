#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HDM activation — admin tool (run from your own PC).

    python3 hdm-admin.py list
    python3 hdm-admin.py release HG-XXXX-XXXX-XXXX-XXXX-XXXX   # free a license
    python3 hdm-admin.py plan HG-... 12                        # change plan (06/12/99)
    python3 hdm-admin.py server https://hamidesigns.shop/api/hdm list
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER = "https://hamidesigns.shop/api/hdm"
TOKEN = "YnVTbNKcvND2V05rKvhTRiykkuPJEuQk"


def call(base, path, payload=None, query=None):
    url = base.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", "HDM-admin/1.0")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    args = sys.argv[1:]
    base = SERVER
    if args and args[0].startswith("http"):
        base = args.pop(0)
    cmd = (args[0] if args else "list").lower()

    if cmd == "list":
        out = call(base, "/admin/list", None, {"token": TOKEN})
        if not out.get("ok"):
            print("Error:", out.get("error"))
            return 1
        print("%d license(s) on %s\n" % (out["count"], base))
        print("%-26s %-18s %-10s %-17s %-17s %s" %
              ("KEY", "NAME", "PLAN", "FIRST", "LAST SEEN", "CHECKS"))
        print("-" * 104)
        for i in out["items"]:
            k = i["key"]
            pretty = "HG-%s-%s-%s-%s-%s" % (k[2:6], k[6:10], k[10:14], k[14:18], k[18:22])
            print("%-26s %-18s %-10s %-17s %-17s %s" %
                  (pretty, i["name"], i["plan"], i["first"], i["last"], i["checks"]))
        return 0

    if cmd == "release" and len(args) > 1:
        out = call(base, "/admin/release", {"token": TOKEN, "key": args[1]})
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("ok") else 1

    if cmd == "plan" and len(args) > 2:
        out = call(base, "/admin/plan", {"token": TOKEN, "key": args[1], "plan": args[2]})
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("ok") else 1

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
