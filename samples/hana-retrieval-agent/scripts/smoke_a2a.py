"""Require source-linked vector and graph answers from an actual A2A endpoint."""

import argparse
import json
from uuid import uuid4

import httpx


def run(url):
    with httpx.Client(timeout=60, trust_env=False) as client:
        results = []
        for message, expected in [
            ("vector:manufacturing:assembly delay", "https://example.com/source/doc-1"),
            ("graph:customer-42", "https://example.com/source/customer-42"),
        ]:
            response = client.post(
                url.rstrip("/") + "/",
                headers={"A2A-Version": "1.0"},
                json={
                    "jsonrpc": "2.0",
                    "id": str(uuid4()),
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": str(uuid4()),
                            "role": "ROLE_USER",
                            "parts": [{"text": message}],
                        }
                    },
                },
            )
            response.raise_for_status()
            task = response.json()["result"]["task"]
            if task["status"]["state"] != "TASK_STATE_COMPLETED":
                raise RuntimeError("retrieval task did not complete")
            answer = "\n".join(
                part["text"] for artifact in task["artifacts"] for part in artifact["parts"]
            )
            if expected not in answer:
                raise RuntimeError("retrieval answer lacks its expected source reference")
            results.append({"message": message, "state": task["status"]["state"], "reply": answer})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    print(json.dumps(run(parser.parse_args().base_url), indent=2))
