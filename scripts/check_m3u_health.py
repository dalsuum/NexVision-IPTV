#!/usr/bin/env python3
"""Daily M3U stream health checker.

Usage:
  M3U_URL=https://example.com/playlist.m3u python scripts/check_m3u_health.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

OUTPUT_PATH = Path("monitoring/m3u-last-checked.json")
DEFAULT_TIMEOUT = 8
MAX_STREAMS = 25
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_m3u_stream_urls(content: str) -> list[str]:
    urls: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if URL_RE.match(line):
            urls.append(line)
    return urls


def check_url(session: requests.Session, url: str, timeout: int) -> tuple[bool, int | None, str | None]:
    try:
        response = session.get(url, timeout=timeout, stream=True, allow_redirects=True)
        code = response.status_code
        ok = 200 <= code < 400
        response.close()
        return ok, code, None
    except requests.RequestException as exc:
        return False, None, str(exc)


def main() -> int:
    m3u_url = os.getenv("M3U_URL", "").strip()
    timeout = int(os.getenv("M3U_TIMEOUT", str(DEFAULT_TIMEOUT)))
    max_streams = int(os.getenv("M3U_MAX_STREAMS", str(MAX_STREAMS)))

    report: dict[str, object] = {
        "checked_at": now_iso(),
        "m3u_url": m3u_url,
        "total_streams": 0,
        "tested_streams": 0,
        "healthy": 0,
        "unhealthy": 0,
        "success_rate": 0.0,
        "status": "skipped",
        "message": "M3U_URL is not set",
        "sample_failures": [],
    }

    if not m3u_url:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Skipped: set M3U_URL secret/environment variable.")
        return 0

    session = requests.Session()
    try:
        playlist_resp = session.get(m3u_url, timeout=timeout)
        playlist_resp.raise_for_status()
        streams = parse_m3u_stream_urls(playlist_resp.text)

        report["total_streams"] = len(streams)
        to_test = streams[:max_streams]
        report["tested_streams"] = len(to_test)

        failures: list[dict[str, object]] = []
        healthy = 0

        for stream in to_test:
            ok, status_code, error = check_url(session, stream, timeout)
            if ok:
                healthy += 1
            else:
                if len(failures) < 10:
                    failures.append({
                        "url": stream,
                        "status_code": status_code,
                        "error": error,
                    })

        tested = len(to_test)
        unhealthy = tested - healthy
        success_rate = round((healthy / tested) * 100, 2) if tested else 0.0

        report.update(
            {
                "healthy": healthy,
                "unhealthy": unhealthy,
                "success_rate": success_rate,
                "status": "ok" if success_rate >= 80 else "degraded",
                "message": "Health check completed",
                "sample_failures": failures,
            }
        )
    except Exception as exc:  # noqa: BLE001
        report.update(
            {
                "status": "error",
                "message": f"Health check failed: {exc}",
            }
        )
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["message"])
        return 1
    finally:
        session.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Checked {report['tested_streams']} streams. Success rate: {report['success_rate']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
