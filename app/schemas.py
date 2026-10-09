from datetime import date
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator


def uid():
    return str(uuid4())


class Scene(StrEnum):
    us_air = "us_air"
    cn_air = "cn_air"
    rail = "rail"
    beijing_subway = "beijing_subway"
    palace = "palace"
    tiananmen = "tiananmen"
    other = "other"


class Segment(BaseModel):
    id: str = Field(default_factory=uid, max_length=80)
    scene: Scene
    carry: Literal["cabin", "checked", "person"] = "person"
    label: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def carry_mode(self):
        if self.scene in {Scene.us_air, Scene.cn_air} and self.carry == "person":
            self.carry = "cabin"
        if self.scene not in {Scene.us_air, Scene.cn_air, Scene.rail} and self.carry == "checked":
            raise ValueError("Checked baggage is not available at this venue")
        return self


class Trip(BaseModel):
    origin: str = Field(default="United States", max_length=100)
    destination: str = Field(default="Beijing", max_length=100)
    travel_date: date = Field(default_factory=date.today)
    segments: list[Segment] = Field(min_length=1, max_length=12)
    language: Literal["en", "zh"] = "en"

    @model_validator(mode="after")
    def unique_segments(self):
        if len({s.id for s in self.segments}) != len(self.segments):
            raise ValueError("Duplicate segment IDs")
        return self


Category = Literal["power_bank", "battery", "knife", "aerosol", "liquid", "alcohol", "lighter", "medicine", "other"]


class ItemObservation(BaseModel):
    id: str = Field(default_factory=uid, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    category: Category = "other"
    quantity: int = Field(default=1, ge=1, le=100)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)
    image_ids: list[str] = Field(default_factory=list, max_length=6)
    confirmed: bool = False


class VisionOutput(BaseModel):
    items: list[ItemObservation] = Field(max_length=30)


class Answers(BaseModel):
    answers: dict[str, Any] = Field(max_length=3)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class RunRequest(BaseModel):
    mode: Literal["live", "demo"] = "live"


class RuleEvidence(BaseModel):
    id: str
    title: str
    url: str
    excerpt: str
    verified_at: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    review_status: Literal["verified", "pending"] = "pending"


class SegmentDecision(BaseModel):
    item_id: str
    segment_id: str
    scene: str
    status: Literal["allowed", "conditional", "prohibited", "unknown"]
    reason: dict[str, str]
    rule_ids: list[str]
    evidence: list[dict] = Field(default_factory=list)


class ActionPlan(BaseModel):
    item_id: str
    kind: str
    text: dict[str, str]
    verified: bool = False


class ServicePoint(BaseModel):
    name: str
    address: str
    phone: str = ""
    location: str = ""
    distance_m: int | None = None
    walking: dict | None = None
    navigation_url: str = ""
    passport_support: str = "unverified"
    item_acceptance: str = "unverified"
    checkpoint_side: str = "unverified"
    is_demo: bool = False


class AssistanceCard(BaseModel):
    en: str
    zh: str
    hotel: str = ""
