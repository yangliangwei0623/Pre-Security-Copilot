"""Local administrative commands. No public rule-write endpoint."""
import argparse
import json
from pathlib import Path
from app.config import Settings
from app.db import Store
from app.schemas import RuleEvidence
from app.attributes import FIELDS


def validate_bundle(bundle):
    assert isinstance(bundle["version"], str) and 1 <= len(bundle["version"]) <= 100
    sources = {s["id"]: RuleEvidence.model_validate(s) for s in bundle["sources"]}
    assert len(sources) == len(bundle["sources"]), "Duplicate source IDs"
    ids = set()
    for rule in bundle["rules"]:
        assert rule["id"] not in ids, "Duplicate rule IDs"
        ids.add(rule["id"])
        assert rule["sources"] and all(s in sources for s in rule["sources"])
        assert all(f in FIELDS for f in rule["required"])
        assert set(rule["scenes"]) <= {"us_air","cn_air","rail","beijing_subway","palace","tiananmen","other"}
        assert set(rule["carry"]) <= {"cabin","checked","person"}
        for outcome in rule["outcomes"] + [rule["default"]]:
            assert outcome["status"] in {"allowed","conditional","prohibited","unknown"}
            assert set(outcome["reason"]) == {"en","zh"}
            for field, operator, value in outcome.get("when", []):
                assert field in FIELDS or field == "quantity"
                assert operator in {"eq","gt","lte"}
        for sid in rule["sources"]:
            s = sources[sid]
            assert s.url.startswith("https://"), "Only HTTPS source URLs"
            if s.review_status == "verified":
                assert s.verified_at and s.excerpt, "Verified sources need date and excerpt"
    return bundle


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-demo")
    commands.add_parser("migrate")
    imp = commands.add_parser("import-rules")
    imp.add_argument("path", type=Path)
    check = commands.add_parser("check-model")
    check.add_argument("image", type=Path, help="A non-sensitive test photograph to send to the configured Qwen API")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "check-model":
        import asyncio
        from app.providers import Qwen
        result = asyncio.run(Qwen(settings).identify([{"id":"probe","path":str(args.image)}]))
        print(json.dumps({"model":settings.model_name,"items":result},ensure_ascii=False,indent=2))
        return
    store = Store(settings)
    store.migrate()
    if args.command == "init-demo":
        validate_bundle(json.loads((Path(__file__).parent / "data/rules.json").read_text()))
        store.seed()
        print("Database and rule library ready. Sample replay is loaded on demand in the UI.")
    elif args.command == "import-rules":
        bundle = validate_bundle(json.loads(args.path.read_text()))
        existing = store.get("rule_versions", bundle["version"])
        if existing and existing != bundle:
            raise ValueError("Rule releases are immutable; use a new version")
        store.put("rule_versions", bundle["version"], bundle)
        store.put("rules", "active", bundle)
        print(f"Published {bundle['version']}; existing reports retain their original snapshot.")
    store.engine.dispose()


if __name__ == "__main__":
    main()
