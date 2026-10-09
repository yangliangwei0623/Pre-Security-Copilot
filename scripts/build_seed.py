"""Reproducible seed authoring. Source excerpts were inspected on 2026-09-22.
This script does not refresh verification dates when rerun.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def bi(en, zh):
    return {"en": en, "zh": zh}

sources = []
def source(id, title, url, excerpt, effective=None):
    sources.append(dict(id=id, title=title, url=url, excerpt=excerpt, verified_at="2026-09-22",
                        effective_from=effective, effective_to=None, review_status="verified"))

source("rail2022", "铁路旅客禁止、限制携带和托运物品目录", "https://www.12306.cn/mormhweb/zxdt/202206/t20220617_37625.html",
       "标志清晰的充电宝、锂电池，单块额定能量不超过100Wh；日用刀具（刀刃长度超过60毫米）禁止随身携带但可以托运。自喷压力容器单体不超过150毫升，每种1件，累计不超过600毫升。", "2022-07-01")
source("bjmetro2015", "北京市轨道交通禁止携带物品目录（官方页面标注现行有效）", "https://www.beijing.gov.cn/zhengce/zhengcefagui/201905/t20190522_58453.html",
       "菜刀、砍刀、美工刀等刀具及其他锐器、钝器；5个（含）以上打火机；包装上带有易燃、易爆等危险化学品标志或提示信息的日常用品类。", "2015-05-06")
source("palace_items", "故宫博物院禁止携带物品目录", "https://www.dpm.org.cn/singles_detail/259832.html",
       "锐器、钝器，如菜刀、砍刀等刀具；包装上带有易燃、易爆等危险化学品标志或提示信息的物品，如打火机、火柴，含酒精的饮品等。符合存包标准的可寄存。")
source("tiananmen_visit", "天安门地区参观服务提示", "https://tamgw.beijing.gov.cn/zhengwugongkai/tzgg/202304/t20230410_2993773.html",
       "严禁携带危险物品、管制器具和违禁物品，禁止携带“低慢小”航空器、打火机等可能影响社会秩序和公共安全的物品。按预约日期和时段前往。", "2023-04-10")
source("tsa_knives", "TSA · Knives", "https://www.tsa.gov/travel/security-screening/whatcanibring/items/knives",
       "Carry On Bags: No. Checked Bags: Yes. Except rounded-blade, blunt non-serrated butter knives or plastic cutlery. Sharp objects in checked bags should be sheathed or securely wrapped.")
source("tsa_liquids", "TSA · Liquids Rule", "https://www.tsa.gov/travel/security-screening/liquids-rule",
       "A quart-sized bag of liquids, aerosols, gels, creams and pastes in carry-on baggage; containers 3.4 ounces (100 milliliters) or less per item. Exceptions and further screening may apply.")
source("faa_batteries", "FAA PackSafe · Lithium Batteries", "https://www.faa.gov/hazmat/packsafe/lithium-batteries",
       "Spare lithium batteries, including power banks, must be carried in carry-on baggage only. Lithium-ion batteries limited to 100Wh; larger batteries up to 160Wh require airline approval, up to two. Protect terminals. Damaged/recalled batteries likely to generate dangerous heat must not be carried.")
source("caac_power", "民航局关于民航旅客携带“充电宝”乘机规定的公告", "https://www.caac.gov.cn/XXGK/XXGK/TZTG/201511/t20151105_11173.html",
       "充电宝严禁托运；不超过100Wh无需航司批准；超过100Wh但不超过160Wh需航司批准且不超过两个；超过160Wh或无法判定额定能量的严禁携带。飞行中不得使用。", "2014-08-07")
source("caac_ccc", "民航局：禁止旅客携带无3C标识及被召回的充电宝乘坐境内航班", "https://www.caac.gov.cn/XWZX/MHYW/202506/t20250626_227805.html",
       "自6月28日起禁止旅客携带没有3C标识、3C标识不清晰、被召回型号或批次的充电宝乘坐境内航班。", "2025-06-28")

rules = []
def rule(id, scenes, categories, carry, required, outcomes, default, sources, since=None):
    rules.append(dict(id=id, scenes=scenes, categories=categories, carry=carry, required=required,
                      outcomes=outcomes, default=default, sources=sources, effective_from=since, effective_to=None))
def result(status, en, zh): return dict(status=status, reason=bi(en, zh))
def outcome(conditions, status, en, zh): return dict(when=conditions, **result(status, en, zh))
def blocked(field, op, val, en, zh): return outcome([[field, op, val]], "prohibited", en, zh)

rule("tsa_knife_cabin", ["us_air"], ["knife"], ["cabin"], [], [], result("prohibited", "Sharp knives are not permitted in TSA carry-on baggage. This category excludes blunt butter knives and plastic cutlery.", "TSA禁止随身携带锐利刀具；本类别不包括钝头黄油刀和塑料餐具。"), ["tsa_knives"])
rule("tsa_knife_checked", ["us_air"], ["knife"], ["checked"], ["ordinary_knife"],
     [outcome([["ordinary_knife","eq",False]], "unknown", "A specialist or potentially controlled blade requires separate checks.", "专业或疑似管制刀具需单独核实。")],
     result("conditional", "TSA permits checked knives when sheathed or securely wrapped. Destination/import rules are separate.", "TSA允许妥善套封或包裹的刀具托运；目的地及入境要求需另行核实。"), ["tsa_knives"])
rule("tsa_liquid_cabin", ["us_air"], ["liquid"], ["cabin"], ["volume_ml", "ordinary_liquid"],
     [outcome([["ordinary_liquid","eq",False]], "unknown", "Hazardous or special liquids need a substance-specific rule.", "危险或特殊液体需按具体成分核实。"),
      blocked("volume_ml","gt",100,"Ordinary liquids in containers over 100 mL do not meet the TSA carry-on liquid rule. Medical and other exceptions need separate screening.","普通液体容器超过100毫升，不符合TSA随身液体要求；医疗等例外须另行核验。")],
     result("conditional", "Each container must be 100 mL or less, and all liquids must fit in one quart-sized bag. Additional screening may apply.", "单体容器不超过100毫升，所有液体须装入一个夸脱大小袋中，可能需额外检查。"), ["tsa_liquids"])
for scene, cats, src in [("us_air", ["power_bank", "battery"], "faa_batteries"), ("cn_air", ["power_bank"], "caac_power")]:
    rule(scene+"_battery_checked", [scene], cats, ["checked"], [], [],
         result("prohibited", "Power banks and applicable spare lithium batteries cannot travel in checked baggage.", "充电宝及适用的备用锂电池不得放入托运行李。"), [src])
    required = ["wh", "label_clear", "damaged", "recalled"]
    outcomes = [blocked("wh","gt",160,"Rated energy exceeds 160 Wh.","额定能量超过160Wh。"),
                outcome([["damaged","eq",True]],"unknown","A damaged battery needs carrier safety review; do not pack or ship it as ordinary baggage.","损坏电池需承运方安全核验，不要按普通行李或包裹运输。"),
                outcome([["recalled","eq",True]],"unknown","Check the recall notice and carrier restrictions; no clearance is provided.","需核对召回通知及承运方限制，本系统不提供放行结论。"),
                outcome([["wh","gt",100],["quantity","gt",2]],"prohibited","More than two batteries above 100 Wh exceed the larger-battery allowance.","超过100Wh的电池多于两块，超过大容量电池数量限额。"),
                outcome([["wh","gt",100]],"conditional","100–160 Wh batteries require airline approval, maximum two. Carrier-specific restrictions still apply.","超过100Wh且不超过160Wh需航司批准，最多两块；仍需核实航司附加要求。"),
                outcome([["label_clear","eq",False]],"unknown","Rated energy cannot be confirmed from the label; request a clear label or operator assessment.","无法从标签确认额定能量，请补拍清晰标签或请运营方判定。")]
    if scene == "cn_air":
        required += ["ccc_clear"]
        outcomes += [blocked("ccc_clear","eq",False,"A clear CCC mark is required for power banks on mainland domestic flights.","中国境内航班要求充电宝具备清晰3C标识。"),
                     blocked("recalled","eq",True,"Recalled power-bank models/batches are prohibited on mainland domestic flights.","被召回型号或批次充电宝禁止携带乘坐境内航班。")]
    default_reason = result(
        "conditional",
        "Up to 100 Wh under the checked conditions. Protect terminals, keep in the cabin, and confirm carrier-specific limits.",
        "已确认条件下不超过100Wh；保护接点、随身携带并核实航司附加限制。",
    )
    if scene == "cn_air":
        default_reason = result(
            "conditional",
            "Up to 100 Wh under the checked conditions. Keep the power bank in the cabin, confirm carrier-specific limits, and do not use it during the flight.",
            "已确认条件下不超过100Wh；充电宝须随身携带，核实航司附加限制，并且飞行中不得使用。",
        )
    rule(scene+"_battery_cabin",[scene],cats,["cabin"],required,outcomes,
         default_reason,
         [src] + (["caac_ccc"] if scene=="cn_air" else []), "2025-06-28" if scene=="cn_air" else None)
rule("rail_battery",["rail"],["power_bank","battery"],["person"],["wh","label_clear","damaged"],
     [blocked("wh","gt",100,"Railway carry-on batteries must not exceed 100 Wh per unit.","铁路随身携带电池单块额定能量不得超过100Wh。"),
      blocked("label_clear","eq",False,"Railway carry-on batteries must have clear markings.","铁路要求充电宝及锂电池标志清晰。"),
      outcome([["damaged","eq",True]],"unknown","Damaged battery condition needs operator safety review.","电池损坏状态需运营方另行安全核实。")],
     result("allowed","The clear-marking and per-unit 100 Wh railway conditions are met for this ordinary battery.","该普通电池满足铁路标志清晰且单块不超过100Wh的条件。"),["rail2022"],"2022-07-01")
rule("rail_knife",["rail"],["knife"],["person"],["ordinary_knife","blade_mm"],
     [outcome([["ordinary_knife","eq",False]],"unknown","Do not infer controlled-weapon classification from blade length alone. Ask the operator.","不能仅凭刀刃长度判定是否属于管制器具，请向运营方核实。"),
      blocked("blade_mm","gt",60,"Listed household knives with blades longer than 60 mm are prohibited in carry-on railway baggage. This does not itself classify them as controlled knives.","目录内日用刀具刀刃超过60毫米禁止随身携带上火车，这不等同于认定为管制刀具。")],
     result("conditional","This ordinary blade does not exceed the listed 60 mm threshold; other sharp-tool categories and temporary restrictions still need operator confirmation.","该普通刀刃未超过目录中的60毫米阈值，但其他锐器类别及临时限制仍需向运营方核实。"),["rail2022"],"2022-07-01")
rule("rail_knife_checked",["rail"],["knife"],["checked"],["ordinary_knife"],
     [outcome([["ordinary_knife","eq",False]],"unknown","Controlled or specialist classification requires official confirmation.","管制或专业器具分类需官方核实。")],
     result("conditional","Ordinary knives in the listed category may be checked. Confirm baggage service availability and acceptance before arriving; parcel courier rules are separate.","目录内普通刀具可按条件办理铁路托运，须提前确认业务及收运条件；快递规则另行核实。"),["rail2022"],"2022-07-01")
rule("rail_spray",["rail"],["aerosol"],["person"],["volume_ml","pressurized","toiletry","flammable"],
     [outcome([["toiletry","eq",False]],"unknown","Industrial, pesticide or defence sprays need a substance-specific classification.","工业、农药或防身喷剂需按具体类别核实。"),
      outcome([["pressurized","eq",True],["volume_ml","gt",150]],"prohibited","Pressurized toiletry containers may not exceed 150 mL each.","自喷压力日用品单体容器不得超过150毫升。"),
      outcome([["pressurized","eq",False],["flammable","eq",True],["volume_ml","gt",100]],"prohibited","Flammable non-pressurized daily-use containers may not exceed 100 mL.","含易燃成分的非自喷压力日用品单体容器不得超过100毫升。"),
      blocked("quantity","gt",1,"Only one of each restricted spray type is allowed.","受限喷雾每种限带一件。")],
     result("conditional","Confirm the exact product class: pressurized daily-use containers up to 150 mL each, one of each type, 600 mL combined. Flammable non-pressurized daily products: 100 mL, one per type.","需确认具体品类：自喷压力日用品单体150毫升以内、每种1件、累计600毫升；含易燃成分的非自喷日用品单体100毫升、每种1件。"),["rail2022"],"2022-07-01")
rule("rail_alcohol",["rail"],["alcohol"],["person"],["abv","volume_ml","sealed"],
     [blocked("abv","gt",70,"Alcoholic drinks above 70% ABV are prohibited.","酒精体积含量超过70%的酒类饮品禁止携带。"),
      outcome([["sealed","eq",False]],"unknown","Packaging and label must be verified; unclear alcohol labels are prohibited.","需核实包装及标签；标志不清晰的酒类饮品禁止携带。")],
     result("conditional","24–70% ABV drinks must be sealed and clearly labelled, no more than 3,000 mL combined. Other alcohol products require separate checks.","24%–70%酒类饮品须密封、标志清晰，累计不超过3000毫升；其他酒精产品需另查。"),["rail2022"],"2022-07-01")
rule("rail_lighter",["rail"],["lighter"],["person"],["ordinary_lighter"],
     [blocked("quantity","gt",2,"At most two ordinary lighters may be carried on railways.","铁路普通打火机最多携带2个。"),
      outcome([["ordinary_lighter","eq",False]],"unknown","Torch lighters and fuel need a separate rule.","喷枪类打火机或燃料需单独核实。")],
     result("conditional","At most two ordinary lighters; do not include lighter fuel. Temporary controls may differ.","普通打火机不超过2个，不含打火机燃料，临时管制可能不同。"),["rail2022"],"2022-07-01")
for scene, src in [("beijing_subway","bjmetro2015"),("palace","palace_items")]:
    rule(scene+"_knife",[scene],["knife"],["person"],[],[],result("prohibited","Sharp knives/tools in this category are prohibited at this checkpoint; this is not a legal controlled-weapon determination.","该类别锐利刀具或工具禁止带入此安检点；此结论不是管制器具法律认定。"),[src])
    rule(scene+"_flammable",[scene],["aerosol","liquid"],["person"],["flammable"],
         [blocked("flammable","eq",True,"Daily-use products labelled flammable/explosive are prohibited here, regardless of a smaller travel size.","包装标注易燃、易爆的日用品禁止带入此处，换小容量不消除该限制。")],
         result("unknown","No flame marking alone does not establish permission. Confirm the product contents with the venue.","没有火苗标识不能单独证明可携带，需向场所核实成分及类别。"),[src])
rule("metro_lighter",["beijing_subway"],["lighter"],["person"],["ordinary_lighter"],
     [blocked("quantity","gt",4,"Five or more lighters are prohibited on Beijing metro.","北京地铁禁止携带5个及以上打火机。"),
      outcome([["ordinary_lighter","eq",False]],"unknown","Special lighter/fuel classification needs confirmation.","特殊打火机或燃料类别需另行核实。")],
     result("conditional","Fewer than five ordinary lighters under this directory; confirm temporary controls.","此目录下普通打火机少于5个，仍需核实临时管制。"),["bjmetro2015"])
for scene, src in [("palace","palace_items"),("tiananmen","tiananmen_visit")]:
    rule(scene+"_lighter",[scene],["lighter"],["person"],[],[],result("prohibited","Lighters are prohibited at this venue.","该场所禁止携带打火机。"),[src])
rule("palace_alcohol",["palace"],["alcohol"],["person"],[],[],result("prohibited","The Palace Museum prohibited-items list includes alcoholic drinks.","故宫禁止携带物品目录包含含酒精的饮品。"),["palace_items"])
notes=[
 {"scene":"palace","url":"https://www.dpm.org.cn/Visit.html","text":bi("Use the Palace Museum's official booking channel and check the current passport and entry procedure. Palace admission and Tiananmen Square reservations are separate processes; verify any current exemption. Storage is only for items meeting the museum's acceptance conditions.","通过故宫官方渠道预约，并核实当前护照和入院流程。故宫与天安门广场预约是不同流程，是否有预约互认或豁免请查当日规定；仅符合故宫存包条件的物品可寄存。"),"review_status":"pending"},
 {"scene":"tiananmen","url":"https://tamgw.beijing.gov.cn/zhengwugongkai/tzgg/202304/t20230410_2993773.html","text":bi("Check the official Tiananmen Square reservation channel and attend at the booked time. Verify the current foreign-passport procedure and any event-day restrictions before visiting. This report does not confirm a reservation.","通过天安门广场官方预约渠道核实并按预约时段前往。出行前确认外籍护照办理流程及活动日临时管制；本报告不代表已预约。"),"review_status":"partial"}
]
bundle=dict(version="beijing-2026-09-22.2", sources=sources, rules=rules, venue_notes=notes)
(ROOT/"app/data/rules.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n")
demo=dict(trip=dict(origin="United States",destination="Beijing",travel_date="2026-09-22",language="en",segments=[dict(id="flight",scene="us_air",carry="cabin"),dict(id="train",scene="rail",carry="person"),dict(id="metro",scene="beijing_subway",carry="person"),dict(id="museum",scene="palace",carry="person"),dict(id="square",scene="tiananmen",carry="person")]),items=[])
for id,name,cat,attrs in [("demo-battery","Travel power bank · 74 Wh","power_bank",dict(wh=74,label_clear=True,damaged=False,recalled=False)),("demo-spray","Travel hair spray · 100 mL","aerosol",dict(volume_ml=100,pressurized=True,toiletry=True)),("demo-knife","Multi-tool with an 80 mm blade","knife",dict(blade_mm=80,ordinary_knife=True)),("demo-liquid","Face cleanser · 80 mL","liquid",dict(volume_ml=80,ordinary_liquid=True,flammable=False))]:
    demo['items'].append(dict(id=id,name=name,category=cat,quantity=1,attributes=attrs,provenance={k:"demo" for k in attrs},image_ids=[],confirmed=False))
(ROOT/"app/data/demo.json").write_text(json.dumps(demo,ensure_ascii=False,indent=2)+"\n")
print(f"Wrote {len(rules)} rules from {len(sources)} inspected official sources")
