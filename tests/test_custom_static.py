from aw_server.server import AWFlask


def test_custom_static_not_found_is_escaped():
    app = AWFlask("127.0.0.1", testing=True, custom_static={})
    client = app.test_client()
    r = client.get("/pages/%3Cb%3Ewatcher/%3Ci%3Eview.html")
    assert r.status_code == 404
    assert b"&lt;b&gt;watcher" in r.data
    assert b"&lt;i&gt;view.html" in r.data
    assert b"<b>" not in r.data and b"<i>" not in r.data
