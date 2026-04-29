import json
import re
import sys
from typing import Any, Dict, List, Optional

import requests

API_BASE = "http://localhost:8000/api/v1"
TIMEOUT = 35

session = requests.Session()


def login() -> None:
    r = session.post(
        f"{API_BASE}/users/login",
        json={"username": "testuser", "password": "testpass123"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    tok = r.json().get("access_token")
    if tok:
        session.headers.update({"Authorization": f"Bearer {tok}"})


def send(msg: str, cid: Optional[str]) -> Dict[str, Any]:
    payload = {"message": msg}
    if cid:
        payload["conversation_id"] = cid
    r = session.post(f"{API_BASE}/chat", json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def content(resp: Dict[str, Any]) -> Dict[str, Any]:
    c = resp.get("message", {}).get("content", {})
    return c if isinstance(c, dict) else {}


def sql(resp: Dict[str, Any]) -> str:
    message = resp.get("message", {})
    metadata = message.get("metadata") if isinstance(message, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return str(metadata.get("generated_sql", "") or "")


def to_num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def chk_non_empty(c: Dict[str, Any]) -> bool:
    return isinstance(c.get("result_data"), list) and len(c.get("result_data")) > 0


def chk_non_zero(c: Dict[str, Any]) -> bool:
    vals = [to_num(i.get("value")) for i in c.get("result_data", [])]
    vals = [v for v in vals if v is not None]
    return any(v > 0 for v in vals) if vals else False


def chk_summary_first(c: Dict[str, Any]) -> bool:
    rd = c.get("result_data", [])
    if not rd:
        return False
    v = str(rd[0].get("value", ""))
    s = str(c.get("insight_summary", ""))
    # Normalise digits so formatted/unformatted numbers both match.
    sv = "".join(ch for ch in v if ch.isdigit())
    ss = "".join(ch for ch in s if ch.isdigit())
    return bool(sv) and (sv in ss)


def chk_consistent(c: Dict[str, Any]) -> bool:
    rd = c.get("result_data", [])
    raw = c.get("raw_rows", [])
    if not rd or not raw:
        return True

    raw_map: Dict[str, float] = {}
    for r in raw:
        p = r.get("platform")
        mv = r.get("metric_value", r.get("value"))
        if p is not None and mv is not None:
            try:
                raw_map[str(p).lower()] = float(mv)
            except Exception:
                pass

    if raw_map:
        for d in rd:
            p = str(d.get("platform", "")).lower()
            if p in raw_map:
                dv = to_num(d.get("value"))
                if dv is None or abs(dv - raw_map[p]) > 0.5:
                    return False
        return True

    n = min(len(rd), len(raw))
    for i in range(n):
        dv = to_num(rd[i].get("value"))
        mv = raw[i].get("metric_value", raw[i].get("value"))
        try:
            fm = float(mv)
        except Exception:
            return False
        if dv is None or abs(dv - fm) > 0.5:
            return False
    return True


def run_flow(name: str, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    cid: Optional[str] = None
    out: Dict[str, Any] = {"flow": name, "passed": True, "turns": []}

    for t in turns:
        prompt = t["prompt"]
        r = send(prompt, cid)
        cid = r.get("conversation_id", cid)
        c = content(r)
        s = sql(r)

        checks: Dict[str, bool] = {
            "non_empty": chk_non_empty(c),
            "summary_matches": chk_summary_first(c),
            "raw_consistency": chk_consistent(c),
        }
        if t.get("expect_non_zero"):
            checks["non_zero"] = chk_non_zero(c)
        if t.get("sql_contains"):
            checks["sql_match"] = t["sql_contains"].lower() in s.lower()

        passed = all(checks.values())
        if not passed:
            out["passed"] = False

        out["turns"].append(
            {
                "prompt": prompt,
                "sql": s,
                "checks": checks,
                "passed": passed,
                "rows": len(c.get("result_data", [])) if isinstance(c.get("result_data", []), list) else 0,
            }
        )

    return out


def main() -> int:
    login()

    flows = [
        (
            "A",
            [
                {"prompt": "What are the top 5 viewed videos", "sql_contains": "group by beast_uuid"},
                {
                    "prompt": "Compare the first video across all platforms",
                    "sql_contains": "where beast_uuid = :top_beast_uuid",
                    "expect_non_zero": True,
                },
                {
                    "prompt": "Which platform contributes the highest share for that same video?",
                    "sql_contains": "beast_uuid",
                    "expect_non_zero": True,
                },
            ],
        ),
        (
            "D",
            [
                {"prompt": "What are the top 5 viewed videos", "sql_contains": "group by beast_uuid"},
                {
                    "prompt": "For the first one, compare video views across platforms",
                    "sql_contains": "where beast_uuid = :top_beast_uuid",
                    "expect_non_zero": True,
                },
                {
                    "prompt": "For that same one, compare total interactions across platforms",
                    "sql_contains": "where beast_uuid = :top_beast_uuid",
                    "expect_non_zero": True,
                },
            ],
        ),
    ]

    report = [run_flow(name, turns) for name, turns in flows]
    all_passed = all(f["passed"] for f in report)
    out = {"all_passed": all_passed, "flows": report}
    print(json.dumps(out, indent=2))

    with open("/tmp/beast_e2e_compact_report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
