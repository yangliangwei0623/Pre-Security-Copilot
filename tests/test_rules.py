import json
from pathlib import Path

from app.rules import build_report, questions_for


def bundle():
    return json.loads((Path(__file__).parents[1] / "app/data/rules.json").read_text())


def trip(*segments):
    return {
        "origin": "United States",
        "destination": "Beijing",
        "travel_date": "2026-09-22",
        "language": "en",
        "segments": list(segments),
    }


def item(category, attributes, quantity=1):
    return {
        "id": "item",
        "name": "Test item",
        "category": category,
        "quantity": quantity,
        "attributes": attributes,
        "provenance": {},
        "image_ids": [],
        "confirmed": True,
    }


def decision(report, scene):
    return next(d for d in report["decisions"] if d["scene"] == scene)


def test_tsa_carry_on_knife_is_prohibited():
    report = build_report(
        bundle(),
        [item("knife", {"blade_mm": 40, "ordinary_knife": True})],
        trip({"id": "flight", "scene": "us_air", "carry": "cabin", "label": ""}),
    )
    assert decision(report, "us_air")["status"] == "prohibited"


def test_rail_knife_threshold_does_not_claim_controlled_weapon():
    report = build_report(
        bundle(),
        [item("knife", {"blade_mm": 61, "ordinary_knife": True})],
        trip({"id": "rail", "scene": "rail", "carry": "person", "label": ""}),
    )
    result = decision(report, "rail")
    assert result["status"] == "prohibited"
    assert "不等同于认定为管制刀具" in result["reason"]["zh"]


def test_rail_power_bank_requires_readable_label():
    report = build_report(
        bundle(),
        [item("power_bank", {"wh": 74, "label_clear": False, "damaged": False})],
        trip({"id": "rail", "scene": "rail", "carry": "person", "label": ""}),
    )
    assert decision(report, "rail")["status"] == "prohibited"


def test_china_domestic_power_bank_requires_ccc():
    report = build_report(
        bundle(),
        [item("power_bank", {
            "wh": 74,
            "label_clear": True,
            "damaged": False,
            "recalled": False,
            "ccc_clear": False,
        })],
        trip({"id": "flight", "scene": "cn_air", "carry": "cabin", "label": ""}),
    )
    assert decision(report, "cn_air")["status"] == "prohibited"


def test_us_battery_guidance_does_not_include_china_inflight_rule():
    report = build_report(
        bundle(),
        [item("power_bank", {
            "wh": 74,
            "label_clear": True,
            "damaged": False,
            "recalled": False,
        })],
        trip({"id": "flight", "scene": "us_air", "carry": "cabin", "label": ""}),
    )
    reason = decision(report, "us_air")["reason"]["en"]
    assert "China flight" not in reason
    assert "carrier-specific" in reason


def test_questions_are_bounded_and_rule_driven():
    questions = questions_for(
        bundle(),
        [item("power_bank", {})],
        trip(
            {"id": "flight", "scene": "cn_air", "carry": "cabin", "label": ""},
            {"id": "rail", "scene": "rail", "carry": "person", "label": ""},
        ),
    )
    assert len(questions) == 3
    assert {q["field"] for q in questions} <= {
        "wh", "label_clear", "damaged", "recalled", "ccc_clear"
    }


def test_future_trip_outside_review_window_is_unknown():
    report = build_report(
        bundle(),
        [item("knife", {"blade_mm": 80, "ordinary_knife": True})],
        {
            **trip({"id": "rail", "scene": "rail", "carry": "person", "label": ""}),
            "travel_date": "2027-01-15",
        },
    )
    result = decision(report, "rail")
    assert result["status"] == "unknown"
    assert not result["rule_ids"]
