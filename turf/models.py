from __future__ import annotations
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field

# --- Registry ---

class TrackEntry(BaseModel):
    canonical: str
    code: str
    aliases: List[str]


class StateTracks(BaseModel):
    tracks: List[TrackEntry]


class TrackRegistry(BaseModel):
    shape_id: Literal["turf.track_registry.v1"]
    version: str
    generated_at_local: str
    source_of_truth: List[str]
    states: Dict[str, StateTracks]


class ResolvedTrack(BaseModel):
    input: str
    canonical: str
    state: str
    code: str
    confidence: Literal["HIGH", "MED"]
    match_source: Literal["EXACT_OR_ALIAS", "FUZZY_ALIAS"]


class TrackResolutionResult(BaseModel):
    shape_id: Literal["turf.track_resolution.v1"] = "turf.track_resolution.v1"
    input: str
    resolved: Optional[ResolvedTrack] = None
    error: Optional[str] = None

# --- Execution / Plan (minimal wiring) ---

class ExecutionScope(BaseModel):
    date: str  # YYYY-MM-DD
    states: List[str]
    tracks_raw: List[str] = []
    tracks_resolved: List[ResolvedTrack] = []


class ExecutionRequest(BaseModel):
    shape_id: Literal["turf.execution_request.v1"] = "turf.execution_request.v1"
    request_id: str
    created_at_local: str
    scope: ExecutionScope


class ScrapePlanScope(BaseModel):
    date: str
    states: List[str]
    tracks: List[dict]  # {canonical, code, state}


class ScrapePlan(BaseModel):
    shape_id: Literal["turf.scrape_plan.v1"] = "turf.scrape_plan.v1"
    plan_id: str
    request_ref: str
    created_at_local: str
    tz: str
    track_registry_version: str
    scope: ScrapePlanScope
