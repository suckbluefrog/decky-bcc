import json
import socket

SOCKET = "/run/armada/control.sock"
MAX_RESPONSE_BYTES = 1024 * 1024


def call(action, **payload):
    request = {"action": action, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(SOCKET)
        sock.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if len(data) > MAX_RESPONSE_BYTES:
                raise RuntimeError("privileged response exceeded size limit")
    if not data:
        raise RuntimeError("privileged service returned an empty response")
    try:
        response = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("privileged service returned an invalid response") from exc
    if not isinstance(response, dict):
        raise RuntimeError("privileged service returned an invalid response")
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "privileged call failed")
    return response.get("result", {})
