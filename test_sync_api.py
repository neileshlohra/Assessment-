import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import uuid

import pytest
import requests


class SyncHandler(BaseHTTPRequestHandler):
    store = {}
    lock = threading.Lock()

    def do_POST(self):
        if self.path != "/sync-survey":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length))
            required = {"deviceId", "localId", "surveyId", "payload"}
            if not required.issubset(body):
                raise ValueError("missing required field")
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        key = (body["deviceId"], body["localId"], body["surveyId"])
        with self.lock:
            if key in self.store:
                # Idempotent replay: never overwrite the original body.
                status = 200
                response = {"status": "duplicate", "serverId": self.store[key]["serverId"]}
            else:
                server_id = str(uuid.uuid4())
                self.store[key] = {"serverId": server_id, "body": body}
                status = 201
                response = {"status": "created", "serverId": server_id}

        raw = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass


@pytest.fixture(scope="module")
def api_server():
    SyncHandler.store = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), SyncHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


@pytest.fixture(autouse=True)
def reset_store():
    SyncHandler.store = {}


def survey(device, local_id="School_1", name="Govt Primary School"):
    return {
        "deviceId": device,
        "localId": local_id,
        "surveyId": f"survey-{device}-001",
        "payload": {"schoolName": name, "worker": device},
    }


def post(base, payload):
    return requests.post(f"{base}/sync-survey", json=payload, timeout=3)


def test_same_local_id_from_two_devices_does_not_overwrite(api_server):
    ankit = survey("device-ankit")
    pooja = survey("device-pooja")

    first = post(api_server, ankit)
    second = post(api_server, pooja)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["serverId"] != second.json()["serverId"]
    assert SyncHandler.store[("device-ankit", "School_1", ankit["surveyId"])]["body"] == ankit
    assert SyncHandler.store[("device-pooja", "School_1", pooja["surveyId"])]["body"] == pooja


def test_exact_replay_is_idempotent_and_does_not_overwrite(api_server):
    payload = survey("device-ankit")
    first = post(api_server, payload)
    replay = post(api_server, payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["status"] == "duplicate"
    assert replay.json()["serverId"] == first.json()["serverId"]
    stored = SyncHandler.store[("device-ankit", "School_1", payload["surveyId"])]
    assert stored["body"] == payload


def test_concurrent_same_payload_creates_one_server_record(api_server):
    payload = survey("device-concurrent")
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: post(api_server, payload), range(50)))

    assert sum(r.status_code == 201 for r in responses) == 1
    assert sum(r.status_code == 200 for r in responses) == 49
    assert len([k for k in SyncHandler.store if k[0] == "device-concurrent"]) == 1


def test_missing_required_field_is_rejected(api_server):
    response = post(api_server, {"deviceId": "device-1", "localId": "School_1"})
    assert response.status_code == 400


def test_burst_from_many_devices_keeps_local_ids_isolated(api_server):
    payloads = [survey(f"device-{i}") for i in range(100)]
    with ThreadPoolExecutor(max_workers=25) as pool:
        responses = list(pool.map(lambda p: post(api_server, p), payloads))

    assert all(r.status_code == 201 for r in responses)
    ids = [r.json()["serverId"] for r in responses]
    assert len(set(ids)) == 100
