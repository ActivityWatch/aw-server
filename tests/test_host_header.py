import http.client
import socket
from threading import Thread

import pytest
from flask import request
from werkzeug.serving import make_server

from aw_server.server import AWFlask


@pytest.mark.parametrize(
    "host", ["localhost", "localhost:5600", "127.0.0.1:5600", "[::1]", "[::1]:5600"]
)
def test_loopback_host_headers(flask_client, host):
    response = flask_client.get("/api/0/buckets/", headers={"Host": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:5600",
        "[2001:db8::1]:5600",
        "::1",
        "[::1",
        "[::1]:bad",
        "[::1]:65536",
        "evil.example@localhost",
        "localhost/evil",
        "localhost?evil",
        "localhost#evil",
    ],
)
def test_untrusted_or_malformed_host_headers(app, host):
    # Inject after context creation: Werkzeug's test client parses Host for
    # its cookie jar and rejects malformed authorities before dispatch.
    with app.test_request_context("/api/0/buckets/"):
        request.environ["HTTP_HOST"] = host
        response = app.full_dispatch_request()
        assert response.status_code == 400


def test_configured_ipv6_host():
    app = AWFlask("2001:db8::1", testing=True, cors_origins=[])
    assert (
        app.test_client()
        .get("/api/0/buckets/", headers={"Host": "[2001:db8::1]:5600"})
        .status_code
        == 200
    )


def test_missing_host_header(flask_client):
    assert (
        flask_client.get(
            "/api/0/buckets/", environ_overrides={"HTTP_HOST": ""}
        ).status_code
        == 400
    )


def test_ipv6_loopback_listener():
    # Skip only when this machine cannot bind IPv6 loopback at all.
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError as error:
        pytest.skip(f"IPv6 loopback unavailable: {error}")
    app = AWFlask("::1", testing=True, cors_origins=[])
    server = make_server("::1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever)
    thread.start()
    connection = http.client.HTTPConnection("::1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/api/0/buckets/")
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"{}\n"
    finally:
        connection.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
