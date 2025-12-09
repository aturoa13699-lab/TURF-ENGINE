"""Registry builder stub.
Wire this to Racing Australia + Racing & Sports ingestion to generate turf.track_registry.v1.
"""
from __future__ import annotations
from typing import Dict, List
from .models import TrackRegistry, StateTracks, TrackEntry


def build_registry_stub() -> TrackRegistry:
    # Replace with real RA/R&S ingestion
    return TrackRegistry(
        shape_id="turf.track_registry.v1",
        version="0.1.0",
        generated_at_local="2025-12-09T10:45:00+11:00",
        source_of_truth=["RACING_AU_FREEFIELDS", "RACING_AND_SPORTS_TRACK_LISTS"],
        states={
            "NSW": StateTracks(tracks=[
                TrackEntry(canonical="Royal Randwick", code="RANDWICK", aliases=["Randwick", "Royal Randwick Racecourse", "Sydney Randwick"]),
                TrackEntry(canonical="Rosehill Gardens", code="ROSEHILL", aliases=["Rosehill", "Rosehill Racecourse", "Rosehill Gdns"]),
                TrackEntry(canonical="Wagga", code="WAGGA", aliases=["Wagga Wagga", "Murrumbidgee Turf Club", "Wagga (Riverside)", "Wagga Riverside", "MTC Wagga"]),
                TrackEntry(canonical="Ballina", code="BALLINA", aliases=["Ballina Jockey Club", "Ballina JC"]),
            ])
        }
    )
