from __future__ import annotations
import json
import uuid
from typing import List, Optional

import typer
from rich import print

from .models import TrackRegistry, ExecutionRequest, ExecutionScope, ScrapePlan, ScrapePlanScope
from .resolver import resolve_tracks

app = typer.Typer(help="TURF registry + resolver + scrape plan CLI")


@app.command()
def resolve(
    registry: str = typer.Option(..., help="Path to turf.track_registry.v1 JSON"),
    tracks: List[str] = typer.Option(..., help="Track strings to resolve", param_decls=["--tracks"]),
    state_hint: Optional[str] = typer.Option(None, help="Optional state hint (e.g., NSW)"),
):
    with open(registry, "r") as f:
        reg = TrackRegistry.model_validate_json(f.read())
    resolved = resolve_tracks(tracks, reg, state_hint=state_hint)
    print(json.dumps([r.model_dump() for r in resolved], indent=2))


@app.command()
def plan(
    registry: str = typer.Option(..., help="Path to turf.track_registry.v1 JSON"),
    date: str = typer.Option(..., help="YYYY-MM-DD"),
    states: List[str] = typer.Option(..., help="States, e.g., --states NSW --states VIC"),
    tracks: List[str] = typer.Option(..., help="Tracks to include in scope", param_decls=["--tracks"]),
    created_at_local: str = typer.Option("2025-12-09T11:00:00+11:00", help="Local timestamp for plan"),
    tz: str = typer.Option("Australia/Sydney", help="Timezone string"),
    track_registry_version: str = typer.Option("turf.track_registry.v1@0.1.0", help="Registry version ref"),
):
    with open(registry, "r") as f:
        reg = TrackRegistry.model_validate_json(f.read())
    # Build an execution request, enrich with resolved, then emit minimal scrape plan
    req = ExecutionRequest(
        request_id=str(uuid.uuid4()),
        created_at_local=created_at_local,
        scope=ExecutionScope(date=date, states=states, tracks_raw=tracks),
    )
    # resolve
    resolved = resolve_tracks(req.scope.tracks_raw, reg, state_hint=states[0] if len(states)==1 else None)
    req.scope.tracks_resolved = resolved
    tracks_scope = [{"canonical": r.canonical, "code": r.code, "state": r.state} for r in resolved]

    sp = ScrapePlan(
        plan_id=str(uuid.uuid4()),
        request_ref=req.request_id,
        created_at_local=created_at_local,
        tz=tz,
        track_registry_version=track_registry_version,
        scope=ScrapePlanScope(date=date, states=states, tracks=tracks_scope),
    )
    print(sp.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
