def test_spike_page_served(client):
    r = client.get("/spike")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "screen.js" in r.text


def test_screen_js_served(client):
    r = client.get("/static/screen.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "extractable" in r.text and "cave-screen-auth:" in r.text


def test_static_does_not_serve_outside_web_dir(client):
    assert client.get("/static/../db.py").status_code == 404
    assert client.get("/static/%2e%2e/db.py").status_code == 404
