"""Private loopback-only synthetic OAuth/OData fixture. Never a SAP tenant."""

import base64
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SCENARIOS = {
    "paged",
    "expired",
    "unauthorized",
    "denied",
    "malformed",
    "outside",
    "wrong_region",
}
REGIONS = {"EMEA", "O'Reilly"}
LOCK = threading.Lock()
STATE = {}


def reset(shape, scenario="paged", region="EMEA", trial="unselected"):
    STATE[shape] = {
        "shape": shape,
        "trial": trial,
        "scenario": scenario,
        "region": region,
        "tokens": 0,
        "pages": 0,
        "unauthorized": 0,
        "filter_checks": 0,
        "basic_auth_checks": 0,
        "outside_requests": 0,
        "service_listings": 0,
        "collection_attempts": 0,
        "responses": dict.fromkeys(
            [
                "ok",
                "unauthorized",
                "denied",
                "malformed",
                "outside_link",
                "wrong_region",
            ],
            0,
        ),
        "denied": False,
    }


reset("A")
reset("B")


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, value, *, malformed=False):
        body = b"{" if malformed else json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid fixture body length") from None
        if not 0 <= length <= 2048:
            raise ValueError("fixture body exceeds limit")
        return self.rfile.read(length)

    def do_POST(self):
        try:
            raw = self.read_body()
            if self.path == "/control":
                body = json.loads(raw)
                if (
                    not isinstance(body, dict)
                    or set(body) != {"shape", "scenario", "region", "trial"}
                    or body["shape"] not in {"A", "B"}
                    or body["scenario"] not in SCENARIOS
                    or body["region"] not in REGIONS
                    or not isinstance(body["trial"], str)
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", body["trial"]) is None
                ):
                    raise ValueError("invalid fixture control")
                with LOCK:
                    reset(body["shape"], body["scenario"], body["region"], body["trial"])
                self.reply(
                    200,
                    {
                        "synthetic_fixture_only": True,
                        "shape": body["shape"],
                        "trial": body["trial"],
                    },
                )
                return
            if self.path not in {"/token/A", "/token/B"}:
                self.reply(404, {"error": "unknown fixture path"})
                return
            shape = self.path[-1]
            expected = "Basic " + base64.b64encode(b"fixture-id:fixture-secret").decode()
            if self.headers.get("Authorization") != expected or parse_qs(raw.decode()) != {
                "grant_type": ["client_credentials"]
            }:
                self.reply(401, {"error": "fixture authorization failed"})
                return
            with LOCK:
                state = STATE[shape]
                state["basic_auth_checks"] += 1
                state["tokens"] += 1
                generation = state["tokens"]
                expiry = 0.03 if state["scenario"] == "expired" and generation == 1 else 60
            self.reply(
                200,
                {
                    "access_token": f"fixture-token-{shape}-{generation}",
                    "expires_in": expiry,
                },
            )
        except (ValueError, UnicodeError, TypeError, KeyError):
            self.reply(400, {"error": "invalid fixture request"})

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/health":
            self.reply(200, {"synthetic_fixture_only": True})
            return
        if parts.path in {"/audit/A", "/audit/B"}:
            with LOCK:
                state = STATE[parts.path[-1]]
                audit = {**state, "responses": dict(state["responses"])}
            self.reply(200, audit)
            return
        shape = "B" if parts.path.startswith("/relational/") else "A"
        with LOCK:
            state = STATE[shape]
            if parts.path not in {
                "/SPACE/SALES",
                "/relational/SPACE/SALES/",
                "/relational/SPACE/SALES/Rows",
            }:
                state["outside_requests"] += 1
                self.reply(404, {"error": "outside fixture collection"})
                return
            expected = f"Bearer fixture-token-{shape}-{state['tokens']}"
            if not state["tokens"] or self.headers.get("Authorization") != expected:
                self.reply(401, {"error": "fixture token invalid"})
                return
            if parts.path == "/relational/SPACE/SALES/":
                self.reply(200, {"value": [{"name": "Rows", "url": "Rows"}]})
                state["service_listings"] += 1
                return
            state["collection_attempts"] += 1
            query = parse_qs(parts.query)
            second = query == {"$skiptoken": ["second"]}
            if not second:
                expected_query = {
                    "$select": ["Region,Revenue"],
                    "$filter": ["Region eq '" + state["region"].replace("'", "''") + "'"],
                    "$top": ["50"],
                }
                if query != expected_query:
                    self.reply(400, {"error": "synthetic filter contract failed"})
                    return
                state["filter_checks"] += 1
            if state["scenario"] == "unauthorized" and not state["denied"]:
                state["denied"] = True
                self.reply(401, {"error": "synthetic expired-token retry"})
                state["unauthorized"] += 1
                state["responses"]["unauthorized"] += 1
                return
            if state["scenario"] == "denied":
                self.reply(403, {"error": "synthetic denied read"})
                state["responses"]["denied"] += 1
                return
            if state["scenario"] == "malformed":
                self.reply(200, {}, malformed=True)
                state["responses"]["malformed"] += 1
                return
            state["pages"] += 1
            scenario, region = state["scenario"], state["region"]
        if scenario == "expired" and not second:
            time.sleep(
                0.06
            )  # Exercises reader expiry before the second page, not a new live window.
        value = {
            "value": [
                {
                    "Region": "WRONG" if scenario == "wrong_region" else region,
                    "Revenue": "7.50" if second else "12.50",
                    "PrivateExtra": "fixture-private-extra",
                }
            ]
        }
        if not second:
            value["@odata.nextLink"] = (
                "/outside"
                if scenario == "outside"
                else parts.path.rsplit("/", 1)[-1] + "?$skiptoken=second"
            )
        with LOCK:
            if STATE[shape] is not state:
                self.reply(409, {"error": "fixture control changed during a request"})
                return
            self.reply(200, value)
            state["responses"]["ok"] += 1
            state["responses"]["outside_link"] += int(scenario == "outside" and not second)
            state["responses"]["wrong_region"] += int(scenario == "wrong_region")


if __name__ == "__main__":
    ThreadingHTTPServer(
        ("127.0.0.1", int(os.getenv("FIXTURE_PORT", "8093"))), Fixture
    ).serve_forever()
