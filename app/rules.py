from datetime import date, timedelta
from app.attributes import FIELDS
from app.schemas import SegmentDecision, ActionPlan


def bi(en, zh):
    return {"en": en, "zh": zh}


def value(item, field):
    return item.get("quantity", 1) if field == "quantity" else item.get("attributes", {}).get(field)


def matches(check, item):
    actual = value(item, check[0])
    if actual is None:
        return None
    op, expected = check[1:]
    return {"eq": lambda: actual == expected, "gt": lambda: actual > expected,
            "lte": lambda: actual <= expected}[op]()


def applicable(bundle, item, segment):
    return [r for r in bundle["rules"] if segment["scene"] in r["scenes"]
            and item["category"] in r["categories"] and segment["carry"] in r["carry"]]


def valid_rule(rule, trip_date, sources):
    day = date.fromisoformat(trip_date)
    if rule.get("effective_from") and day < date.fromisoformat(rule["effective_from"]):
        return False
    if rule.get("effective_to") and day > date.fromisoformat(rule["effective_to"]):
        return False
    # A verification is a dated snapshot, not an assertion of perpetual validity.
    for source_id in rule["sources"]:
        source = sources[source_id]
        if source["review_status"] != "verified" or not source.get("verified_at"):
            return False
        if day > date.fromisoformat(source["verified_at"]) + timedelta(days=90):
            return False
    return True


def questions_for(bundle, items, trip):
    questions = []
    sources = {s["id"]: s for s in bundle["sources"]}
    for item in items:
        needed = set()
        for segment in trip["segments"]:
            for rule in applicable(bundle, item, segment):
                if not valid_rule(rule, trip["travel_date"], sources):
                    continue
                # A known unconditional prohibition needs no further questions.
                if not rule.get("required"):
                    continue
                known_block = any(all(matches(c, item) is True for c in outcome["when"])
                                  for outcome in rule.get("outcomes", [])
                                  if outcome["status"] == "prohibited")
                if not known_block:
                    needed.update(rule.get("required", []))
        for field in sorted(needed):
            if field not in item.get("attributes", {}):
                spec = FIELDS[field]
                questions.append({"id": f"{item['id']}:{field}", "item_id": item["id"],
                                  "item_name": item["name"], "field": field, "type": spec[0],
                                  "text": bi(spec[1], spec[2])})
    return questions[:3]


def evaluate_rule(rule, item):
    outcomes = rule.get("outcomes", [])
    # Known prohibitions can be asserted even if another required field is missing.
    for outcome in outcomes:
        if outcome["status"] == "prohibited" and all(matches(c, item) is True for c in outcome["when"]):
            return outcome["status"], outcome["reason"]
    if any(value(item, field) is None for field in rule.get("required", [])):
        return "unknown", bi("Key label or item details are still unknown. Confirm with the operator.",
                             "关键标识或属性仍不明确，请向运营方确认。")
    for outcome in outcomes:
        if all(matches(c, item) is True for c in outcome["when"]):
            return outcome["status"], outcome["reason"]
    return rule["default"]["status"], rule["default"]["reason"]


def build_report(bundle, items, trip):
    sources = {s["id"]: s for s in bundle["sources"]}
    decisions = []
    for item in items:
        for segment in trip["segments"]:
            rules = applicable(bundle, item, segment)
            valid = [r for r in rules if valid_rule(r, trip["travel_date"], sources)]
            status, reason = "unknown", bi("No current verified rule covers this item and journey segment.",
                                            "暂无覆盖该物品及行程段的有效核验规则。")
            ids, evidence = [], []
            if valid:
                results = [evaluate_rule(r, item) for r in valid]
                statuses = {r[0] for r in results}
                # Conflicting source conclusions must never silently become permission.
                if "prohibited" in statuses and "allowed" in statuses:
                    status, reason = "unknown", bi("Sources conflict. Ask the operator before travelling.", "来源存在冲突，请出行前向运营方核实。")
                else:
                    order = {"allowed": 0, "conditional": 1, "unknown": 2, "prohibited": 3}
                    status, reason = max(results, key=lambda r: order[r[0]])
                ids = [r["id"] for r in valid]
                evidence = [sources[s] for s in sorted({s for r in valid for s in r["sources"]})]
            elif rules:
                reason = bi("This rule is unverified or outside its review/date window. Check the official notice.",
                            "规则尚未核验或超出适用/核验时间窗口，请查阅官方通知。")
                evidence = [sources[s] for s in sorted({s for r in rules for s in r["sources"]})]
            decisions.append(SegmentDecision(item_id=item["id"], segment_id=segment["id"], scene=segment["scene"],
                                              status=status, reason=reason, rule_ids=ids, evidence=evidence).model_dump())
    # Category-wide totals are not per-item permissions. Unknown composition remains conditional.
    for segment in trip["segments"]:
        if segment["scene"] == "rail" and segment["carry"] != "checked":
            sprays = [i for i in items if i["category"] == "aerosol" and i.get("attributes", {}).get("pressurized") is True]
            total = sum((i["attributes"].get("volume_ml") or 0) * i["quantity"] for i in sprays)
            alcohol = [i for i in items if i["category"] == "alcohol" and
                       24 <= (i.get("attributes", {}).get("abv") or 0) <= 70]
            alcohol_total = sum((i["attributes"].get("volume_ml") or 0) * i["quantity"] for i in alcohol)
            for d in decisions:
                if d["segment_id"] != segment["id"] or not d["rule_ids"]:
                    continue
                if total > 600 and d["item_id"] in {i["id"] for i in sprays}:
                    d.update(status="prohibited", reason=bi("Combined pressurized containers exceed 600 mL.", "自喷压力容器累计超过600毫升。"))
                if alcohol_total > 3000 and d["item_id"] in {i["id"] for i in alcohol}:
                    d.update(status="prohibited", reason=bi("Combined 24–70% alcoholic drinks exceed 3,000 mL.", "24%–70%酒类饮品累计超过3000毫升。"))
    actions = []
    for item in items:
        affected = [d for d in decisions if d["item_id"] == item["id"] and d["status"] != "allowed"]
        if not affected:
            continue
        hazardous = item["category"] in {"battery", "power_bank", "alcohol", "aerosol", "lighter", "knife"}
        text = bi("Ask the operator about this exact item before storage or shipping; a nearby shop is not proof of acceptance.",
                  "寄存或寄送前请向服务方说明具体物品；附近有网点不代表可以收寄。")
        if item["category"] in {"battery", "power_bank"}:
            text = bi("Keep spare batteries out of checked baggage. Ask the carrier to verify the label, condition and route requirements. Never mail a damaged battery as an ordinary parcel.",
                      "备用电池不要放入民航托运行李。请承运方核实标识、状态及航线要求；损坏电池不能按普通包裹寄送。")
        elif item["category"] == "knife":
            text = bi("For an ordinary non-controlled knife, ask the carrier about checked transport before arrival. Suspected controlled items require official guidance; do not assume storage or shipping is available.",
                      "普通非管制刀具可提前询问承运方托运条件；疑似管制器具请咨询主管部门，不默认可以寄存或寄送。")
        elif item["category"] in {"aerosol", "liquid", "alcohol"}:
            text = bi("Consider an eligible travel-size or non-flammable alternative. Size alone does not override content or venue restrictions. Confirm storage/shipping acceptance first.",
                      "可考虑符合要求的小规格或非易燃替代品；缩小容量不能消除成分或场所限制。寄存、寄送仍需先核实。")
        actions.append(ActionPlan(item_id=item["id"], kind="contact_operator" if hazardous else "alternative",
                                  text=text).model_dump())
    return {"rule_version": bundle["version"], "trip": trip, "items": items, "decisions": decisions,
            "actions": actions, "venue_notes": [n for n in bundle.get("venue_notes", [])
                                                if n["scene"] in {s["scene"] for s in trip["segments"]}],
            "notice": bi("Dated pre-travel guidance, not checkpoint clearance. Temporary controls and airline conditions may apply.",
                         "这是有核验日期的行前参考，不是安检放行凭证；临时管制及航司条件可能另有要求。")}
