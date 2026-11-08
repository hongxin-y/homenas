import json
import threading
import urllib.request

from http.server import ThreadingHTTPServer

from homenas.standalone import Handler, Runtime


def test_standalone_health_and_login(tmp_path, monkeypatch):
    # This is a narrow smoke test for the offline path; it does not bind a public interface.
    runtime = Runtime(tmp_path / "homenas.db")
    runtime.start()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.runtime = runtime
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    try:
        with opener.open(base + "/api/health") as response:
            assert response.status == 200
            assert json.loads(response.read())["status"] == "ok"
        request = urllib.request.Request(base + "/api/auth/login", data=json.dumps({"username": "admin", "password": "admin"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(request) as response:
            assert "homenas_session" in ";".join(response.headers.get_all("Set-Cookie") or [])
        request = urllib.request.Request(base + "/api/overview")
        with opener.open(request) as response:
            data = json.loads(response.read())
            assert "system" in data and "storage" in data
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()

