import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, event, text
from alembic import command
from alembic.config import Config


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def configure(dbapi, _):
            dbapi.execute("PRAGMA journal_mode=WAL")
            dbapi.execute("PRAGMA busy_timeout=5000")

    def migrate(self):
        cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
        with self.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")

    def get(self, kind, key):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT body FROM records WHERE kind=:k AND id=:i"),
                               {"k": kind, "i": key}).scalar_one_or_none()
        return json.loads(row) if row else None

    def put(self, kind, key, body):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO records(kind,id,body) VALUES(:k,:i,:b) "
                              "ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body"),
                         {"k": kind, "i": key, "b": json.dumps(body, ensure_ascii=False)})

    def all(self, kind):
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT body FROM records WHERE kind=:k"), {"k": kind}).scalars()
            return [json.loads(r) for r in rows]

    def seed(self):
        if not self.get("rules", "active"):
            bundle = json.loads((Path(__file__).parent / "data/rules.json").read_text())
            self.put("rule_versions", bundle["version"], bundle)
            self.put("rules", "active", bundle)

    def interrupt_runs(self):
        for run in self.all("run"):
            if run["status"] in {"queued", "running"}:
                run["status"] = "interrupted"
                run["error"] = "The server restarted. Retry to continue from the saved checkpoint."
                self.put("run", run["id"], run)
