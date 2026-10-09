from io import BytesIO

from PIL import Image

from tests.conftest import create_session


def test_health_and_config(client):
    assert client.get("/healthz").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["live_enabled"] is False
    assert config["demo_enabled"] is True


def test_anonymous_sessions_are_isolated(client):
    first = create_session(client)
    first_cookie = client.cookies.get("copilot_session")

    second_response = client.post("/api/sessions")
    second = second_response.json()
    second_cookie = client.cookies.get("copilot_session")
    assert first_cookie != second_cookie

    client.cookies.set("copilot_session", first_cookie)
    assert client.get(f"/api/sessions/{first['id']}").status_code == 200
    assert client.get(f"/api/sessions/{second['id']}").status_code == 404


def test_demo_run_reaches_questions_then_report(client):
    session = create_session(client)
    loaded = client.post(f"/api/sessions/{session['id']}/demo")
    assert loaded.status_code == 200
    confirmed = client.post(f"/api/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200

    started = client.post(
        f"/api/sessions/{session['id']}/runs", json={"mode": "demo"}
    )
    assert started.status_code == 202
    run_id = started.json()["id"]

    run = wait_until(client, run_id, {"awaiting_answers", "completed"})
    while run["status"] == "awaiting_answers":
        answers = {q["id"]: None for q in run["questions"]}
        response = client.post(f"/api/runs/{run_id}/answers", json={"answers": answers})
        assert response.status_code == 202
        run = wait_until(client, run_id, {"awaiting_answers", "completed"})

    assert run["status"] == "completed"
    assert run["mode"] == "demo"
    assert run["report"]["rule_version"].startswith("beijing-")
    assert any(d["status"] == "prohibited" for d in run["report"]["decisions"])

    services = client.get(f"/api/runs/{run_id}/services").json()
    assert services["mode"] == "demo"
    assert services["points"][0]["is_demo"] is True

    card = client.get(f"/api/runs/{run_id}/card")
    assert card.status_code == 200
    assert "不证明物品可寄存" in card.text


def test_upload_is_sanitized_and_model_key_is_required(client):
    session = create_session(client)
    image = Image.new("RGB", (32, 32), "red")
    raw = BytesIO()
    image.save(raw, format="PNG")

    response = client.post(
        f"/api/sessions/{session['id']}/images",
        files={"files": ("photo.png", raw.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    stored = response.json()["images"][0]
    fetched = client.get(stored["url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/jpeg"

    recognized = client.post(f"/api/sessions/{session['id']}/recognize")
    assert recognized.status_code == 503
    assert "DASHSCOPE_API_KEY" in recognized.json()["detail"]


def wait_until(client, run_id, states):
    import time

    for _ in range(100):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in states:
            return run
        time.sleep(0.02)
    raise AssertionError(f"Run did not reach {states}")
