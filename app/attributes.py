import math
from fastapi import HTTPException

# Bounds/types are shared by form validation, vision extraction and rule questions.
FIELDS = {
    "wh": ("number", "Rated energy (Wh), printed on the label", "标签上的额定能量（Wh）", 10000),
    "label_clear": ("bool", "Are the battery capacity markings clearly readable?", "电池容量标志是否清晰？"),
    "damaged": ("bool", "Is the battery swollen, damaged or overheating?", "电池是否鼓包、损坏或异常发热？"),
    "recalled": ("bool", "Is this battery/model subject to a recall?", "该电池或型号是否在召回范围内？"),
    "ccc_clear": ("bool", "Does the power bank have a clear CCC (3C) mark?", "充电宝是否有清晰的 CCC（3C）标识？"),
    "blade_mm": ("number", "Measured blade length in millimetres", "实测刀刃长度（毫米）", 2000),
    "ordinary_knife": ("bool", "Is it an ordinary household knife, not a controlled or specialist blade? If unsure, select unknown.", "是否为普通日用刀具，而非管制或专业刀具？不确定请选择不知道。"),
    "volume_ml": ("number", "Container capacity in mL (not the remaining contents)", "容器标示容积（毫升，非剩余液量）", 100000),
    "flammable": ("bool", "Does the label show a flame, flammable or explosive warning?", "包装是否有火苗、易燃或易爆标志或提示？"),
    "pressurized": ("bool", "Is this a self-spraying pressurized can?", "是否为自喷压力容器？"),
    "toiletry": ("bool", "Is this a personal toiletry, rather than an industrial/defence spray?", "是否为个人日用品，而非工业或防身喷剂？"),
    "abv": ("number", "Alcohol by volume (%)", "酒精体积百分含量（%）", 100),
    "sealed": ("bool", "Is the retail packaging sealed with a readable label?", "零售包装是否密封且标志清晰？"),
    "ordinary_lighter": ("bool", "Is it an ordinary lighter, not a torch or fuel refill?", "是否为普通打火机，而非喷枪或燃料补充罐？"),
    "ordinary_liquid": ("bool", "Is this a non-hazardous everyday liquid (not fuel, corrosive or flammable)?", "是否为非危险日常液体（不是燃料、腐蚀品或易燃品）？"),
}


def validate_attributes(attrs):
    if len(attrs) > len(FIELDS):
        raise HTTPException(422, "Too many attributes")
    for key, value in attrs.items():
        if key not in FIELDS:
            raise HTTPException(422, f"Unsupported attribute: {key}")
        if value is None:
            continue
        definition = FIELDS[key]
        if definition[0] == "bool":
            if type(value) is not bool:
                raise HTTPException(422, f"{key} must be true, false or null")
        elif type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= definition[3]:
            raise HTTPException(422, f"Invalid numeric value for {key}")
    return attrs
