import asyncio
import io
import json
import logging
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.config import Settings
from app.db import Store, digest, now
from app.schemas import Trip, ItemObservation, RunRequest, Answers, QuestionRequest, uid
from app.attributes import validate_attributes, FIELDS
from app.providers import Qwen, find_services, ANCHORS, search_hints
from app.workflow import build_graph

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 24_000_000
ROOT = Path(__file__).parent
log = logging.getLogger("copilot")


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings)
    locks = defaultdict(asyncio.Lock)
    tasks = set()
    provider = Qwen(settings)
    slots = asyncio.Semaphore(settings.max_concurrent_runs)
    templates = Jinja2Templates(directory=str(ROOT / "templates"))

    @asynccontextmanager
    async def lifespan(app):
        store.migrate()
        store.seed()
        store.interrupt_runs()
        async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir / "checkpoints.db")) as saver:
            await saver.setup()
            app.state.graph = build_graph(saver)
            yield
            for task in list(tasks):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        store.engine.dispose()

    app = FastAPI(title="Pre-Security Copilot", lifespan=lifespan)
    app.state.store = store
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    @app.middleware("http")
    async def safeguards(request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
        length = request.headers.get("content-length")
        if length and int(length) > 62 * 1024 * 1024:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session_for(request, sid):
        session = store.get("session", sid)
        token = request.cookies.get("copilot_session", "")
        if not session or not secrets.compare_digest(session["token_hash"], digest(token)):
            raise HTTPException(404, "Session not found")
        return session

    def run_for(request, rid, fresh=False):
        run = store.get("run", rid)
        if not run:
            raise HTTPException(404, "Run not found")
        session = session_for(request, run["session_id"])
        if fresh and (run["revision"] != session["revision"] or run["status"] == "stale"):
            raise HTTPException(409, "This report is out of date. Start a new analysis.")
        return run, session

    def editable(session):
        if locks[session["id"]].locked():
            raise HTTPException(409, "Analysis is running. Please wait before editing.")

    def save_revision(session):
        session["revision"] += 1
        for run in store.all("run"):
            if run["session_id"] == session["id"] and run["status"] != "stale":
                run["status"] = "stale"
                store.put("run", run["id"], run)
        store.put("session", session["id"], session)

    def public_session(session):
        return {k: v for k, v in session.items() if k != "token_hash"}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "model_configured": bool(settings.dashscope_api_key)}

    @app.get("/api/config")
    async def config():
        return {"live_enabled": bool(settings.dashscope_api_key), "demo_enabled": settings.demo_enabled,
                "map_enabled": bool(settings.amap_api_key), "search_enabled": bool(settings.bocha_api_key),
                "model": settings.model_name, "attributes": FIELDS, "anchors": ANCHORS}

    @app.get("/api/rules")
    async def rules():
        bundle = store.get("rules", "active")
        return {"version": bundle["version"], "sources": bundle["sources"], "count": len(bundle["rules"])}

    @app.post("/api/sessions", status_code=201)
    async def create_session(request: Request):
        token = secrets.token_urlsafe(32)
        sid = uid()
        session = {"id": sid, "token_hash": digest(token), "created_at": now(), "revision": 0,
                   "trip": None, "items": [], "images": [], "latest_run": None, "mode": "live"}
        store.put("session", sid, session)
        response = JSONResponse(public_session(session), status_code=201)
        response.set_cookie("copilot_session", token, httponly=True, samesite="strict",
                            secure=settings.cookie_secure, max_age=7 * 86400)
        return response

    @app.get("/api/sessions/{sid}")
    async def get_session(sid: str, request: Request):
        return public_session(session_for(request, sid))

    @app.put("/api/sessions/{sid}/trip")
    async def set_trip(sid: str, payload: Trip, request: Request):
        session = session_for(request, sid)
        editable(session)
        session["trip"] = payload.model_dump(mode="json")
        save_revision(session)
        return public_session(session)

    @app.post("/api/sessions/{sid}/demo")
    async def load_demo(sid: str, request: Request):
        session = session_for(request, sid)
        editable(session)
        if not settings.demo_enabled:
            raise HTTPException(403, "Sample replay is disabled")
        demo = json.loads((ROOT / "data/demo.json").read_text())
        from datetime import date
        demo["trip"]["travel_date"] = date.today().isoformat()
        session.update(trip=Trip.model_validate(demo["trip"]).model_dump(mode="json"),
                       items=demo["items"], mode="demo", images=[])
        save_revision(session)
        return public_session(session)

    @app.post("/api/sessions/{sid}/items", status_code=201)
    async def add_item(sid: str, payload: ItemObservation, request: Request):
        session = session_for(request, sid)
        editable(session)
        if len(session["items"]) >= 30:
            raise HTTPException(422, "Maximum 30 items")
        validate_attributes(payload.attributes)
        payload.id = uid()
        payload.image_ids = []
        payload.provenance = {k: "user" for k in payload.attributes}
        session["items"].append(payload.model_dump())
        save_revision(session)
        return public_session(session)

    @app.patch("/api/sessions/{sid}/items/{item_id}")
    async def edit_item(sid: str, item_id: str, payload: ItemObservation, request: Request):
        session = session_for(request, sid)
        editable(session)
        original = next((i for i in session["items"] if i["id"] == item_id), None)
        if not original:
            raise HTTPException(404, "Item not found")
        validate_attributes(payload.attributes)
        payload.id = item_id
        payload.image_ids = original["image_ids"]
        payload.provenance = {k: original["provenance"].get(k, "user") if
                              original["attributes"].get(k) == v else "user" for k, v in payload.attributes.items()}
        session["items"] = [payload.model_dump() if i["id"] == item_id else i for i in session["items"]]
        save_revision(session)
        return public_session(session)

    @app.delete("/api/sessions/{sid}/items/{item_id}")
    async def delete_item(sid: str, item_id: str, request: Request):
        session = session_for(request, sid)
        editable(session)
        session["items"] = [i for i in session["items"] if i["id"] != item_id]
        save_revision(session)
        return public_session(session)

    @app.post("/api/sessions/{sid}/confirm")
    async def confirm(sid: str, request: Request):
        session = session_for(request, sid)
        editable(session)
        if not session["items"]:
            raise HTTPException(422, "Add or identify items first")
        for item in session["items"]:
            item["confirmed"] = True
        save_revision(session)
        return public_session(session)

    def sanitize_image(raw):
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}:
                    raise ValueError("Unsupported image format")
                image.load()
                cleaned = ImageOps.exif_transpose(image).convert("RGB")
                cleaned.thumbnail((1800, 1800))
                output = io.BytesIO()
                cleaned.save(output, format="JPEG", quality=88)
                return output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, "Invalid or oversized image. Use JPEG, PNG, WebP or HEIC.")

    @app.post("/api/sessions/{sid}/images")
    async def upload(sid: str, request: Request, files: list[UploadFile] = File(...)):
        session = session_for(request, sid)
        editable(session)
        if not 1 <= len(files) <= 6 or len(session["images"]) + len(files) > 6:
            raise HTTPException(422, "Maximum 6 photos per session")
        async with locks[sid]:
            prepared = []
            for file in files:
                raw = await file.read(10 * 1024 * 1024 + 1)
                await file.close()
                if len(raw) > 10 * 1024 * 1024:
                    raise HTTPException(413, "Each image must be 10 MB or smaller")
                prepared.append(await asyncio.to_thread(sanitize_image, raw))
            folder = settings.data_dir / "images" / sid
            folder.mkdir(parents=True, exist_ok=True)
            for cleaned in prepared:
                iid = uid()
                path = folder / f"{iid}.jpg"
                path.write_bytes(cleaned)
                record = {"id": iid, "session_id": sid, "path": str(path.resolve())}
                store.put("image", iid, record)
                session["images"].append({"id": iid, "url": f"/api/sessions/{sid}/images/{iid}"})
            save_revision(session)
        return public_session(session)

    @app.get("/api/sessions/{sid}/images/{iid}")
    async def image(sid: str, iid: str, request: Request):
        session = session_for(request, sid)
        image = store.get("image", iid)
        if not image or image["session_id"] != sid or iid not in {i["id"] for i in session["images"]}:
            raise HTTPException(404, "Image not found")
        return FileResponse(image["path"], media_type="image/jpeg")

    @app.post("/api/sessions/{sid}/recognize")
    async def recognize(sid: str, request: Request):
        session = session_for(request, sid)
        editable(session)
        if not settings.dashscope_api_key:
            raise HTTPException(503, "Configure DASHSCOPE_API_KEY to analyse real photos. Sample replay is available.")
        if not session["images"]:
            raise HTTPException(422, "Upload photos first")
        async with locks[sid]:
            try:
                images = [store.get("image", i["id"]) for i in session["images"]]
                session["items"] = await provider.identify(images)
                session["mode"] = "live"
                save_revision(session)
            except Exception as exc:
                log.warning("Vision request failed: %s", type(exc).__name__)
                raise HTTPException(502, "Vision service failed or returned invalid data. Retry or enter items manually.")
        return public_session(session)

    async def execute(rid, resume=None):
        run = store.get("run", rid)
        async with locks[run["session_id"]], slots:
            run = store.get("run", rid)
            if run["status"] == "stale":
                return
            run["status"] = "running"
            store.put("run", rid, run)
            try:
                config = {"configurable": {"thread_id": rid}, "recursion_limit": 150}
                snapshot = await app.state.graph.aget_state(config)
                if resume is not None:
                    graph_input = Command(resume=resume)
                elif snapshot.values:
                    graph_input = None
                else:
                    graph_input = run["input"]
                await app.state.graph.ainvoke(graph_input, config)
                snapshot = await app.state.graph.aget_state(config)
                run["questions"] = snapshot.values.get("questions", []) if snapshot.next else []
                run["status"] = "awaiting_answers" if snapshot.next else "completed"
                run["report"] = snapshot.values.get("report")
                run["error"] = None
                session = store.get("session", run["session_id"])
                if session["revision"] != run["revision"]:
                    run["status"] = "stale"
                else:
                    session["items"] = snapshot.values["items"]
                    store.put("session", session["id"], session)
            except Exception as exc:
                log.warning("Analysis failed: %s", type(exc).__name__)
                run["status"] = "failed"
                run["error"] = "Analysis could not finish. Your data is saved; retry this analysis."
            store.put("run", rid, run)

    def dispatch(rid, resume=None):
        task = asyncio.create_task(execute(rid, resume))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    @app.post("/api/sessions/{sid}/runs", status_code=202)
    async def start_run(sid: str, payload: RunRequest, request: Request):
        session = session_for(request, sid)
        editable(session)
        if not session["trip"] or not session["items"]:
            raise HTTPException(422, "Add a trip and items first")
        if any(not i["confirmed"] for i in session["items"]):
            raise HTTPException(422, "Confirm the item list before analysis")
        if payload.mode != session["mode"]:
            raise HTTPException(422, "Mode must match the session; sample items cannot be labelled live")
        existing = store.get("run", session.get("latest_run")) if session.get("latest_run") else None
        if existing and existing["revision"] == session["revision"] and existing["status"] in {"queued", "running", "awaiting_answers"}:
            return {"id": existing["id"], "status": existing["status"]}
        rid = uid()
        run = {"id": rid, "session_id": sid, "revision": session["revision"], "mode": session["mode"],
               "status": "queued", "created_at": now(), "questions": [], "report": None,
               "input": {"trip": session["trip"], "items": session["items"], "bundle": store.get("rules", "active")}}
        store.put("run", rid, run)
        session["latest_run"] = rid
        store.put("session", sid, session)
        dispatch(rid)
        return {"id": rid, "status": "queued"}

    @app.get("/api/runs/{rid}")
    async def get_run(rid: str, request: Request):
        run, session = run_for(request, rid)
        return {k: v for k, v in run.items() if k != "input"}

    @app.post("/api/runs/{rid}/answers", status_code=202)
    async def answers(rid: str, payload: Answers, request: Request):
        run, session = run_for(request, rid, True)
        if run["status"] != "awaiting_answers":
            raise HTTPException(409, "This analysis is not waiting for answers")
        questions = run["questions"]
        if set(payload.answers) != {q["id"] for q in questions}:
            raise HTTPException(422, "Answer the current questions only; use null for unknown")
        for question in questions:
            validate_attributes({question["field"]: payload.answers[question["id"]]})
        run["status"] = "queued"
        store.put("run", rid, run)
        dispatch(rid, payload.answers)
        return {"id": rid, "status": "queued"}

    @app.post("/api/runs/{rid}/retry", status_code=202)
    async def retry(rid: str, request: Request):
        run, session = run_for(request, rid, True)
        if run["status"] not in {"failed", "interrupted"}:
            raise HTTPException(409, "Only interrupted or failed analyses can be retried")
        run["status"] = "queued"
        store.put("run", rid, run)
        dispatch(rid)
        return {"id": rid, "status": "queued"}

    @app.post("/api/runs/{rid}/questions")
    async def question(rid: str, payload: QuestionRequest, request: Request):
        run, _ = run_for(request, rid, True)
        if run["status"] != "completed":
            raise HTTPException(409, "Complete the analysis first")
        report = run["report"]
        indices = list(range(len(report["decisions"])))
        mode = "rule_reference"
        if settings.dashscope_api_key and run["mode"] == "live":
            try:
                indices = await provider.select_decisions(payload.question, report)
                mode = "qwen_selected_evidence"
            except Exception:
                mode = "rule_reference_fallback"
        return {"mode": mode, "decisions": [report["decisions"][i] for i in indices],
                "message": "Answers below quote existing report findings only; new rules require verification.",
                "actions": report["actions"]}

    @app.get("/api/runs/{rid}/services")
    async def services(rid: str, request: Request, anchor: str = "beijing_south"):
        run, _ = run_for(request, rid, True)
        if run["status"] != "completed":
            raise HTTPException(409, "Complete the report first")
        if anchor not in ANCHORS:
            raise HTTPException(422, "Unknown Beijing anchor")
        return await find_services(settings, anchor)

    @app.get("/api/runs/{rid}/search")
    async def search(rid: str, request: Request, q: str = Query(min_length=2, max_length=200)):
        run_for(request, rid, True)
        return await search_hints(settings, q)

    @app.get("/api/runs/{rid}/card", response_class=HTMLResponse)
    async def card(rid: str, request: Request, hotel: str = Query(default="", max_length=250)):
        run, _ = run_for(request, rid, True)
        if run["status"] != "completed":
            raise HTTPException(409, "Complete the report first")
        return templates.TemplateResponse(request=request, name="card.html", context={"hotel": hotel, "mode": run["mode"]})

    return app


app = create_app()
