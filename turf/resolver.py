from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable, Tuple

from rapidfuzz.distance import Levenshtein

from .models import TrackRegistry, ResolvedTrack, TrackResolutionResult
from .normalise import track_input_norm


@dataclass
class TrackResolverIndex:
    exact_map: Dict[str, Dict[str, str]]
    candidates_by_state: Dict[str, List[Dict[str, str]]]


def build_track_resolver_index(registry: TrackRegistry) -> TrackResolverIndex:
    exact_map: Dict[str, Dict[str, str]] = {}
    candidates_by_state: Dict[str, List[Dict[str, str]]] = {}

    for state, state_tracks in registry.states.items():
        cand_list: List[Dict[str, str]] = []
        for t in state_tracks.tracks:
            canon_norm = track_input_norm(t.canonical)
            meta = {"canonical": t.canonical, "state": state, "code": t.code}
            exact_map[canon_norm] = meta
            cand_list.append({"norm": canon_norm, **meta})
            for alias in t.aliases:
                alias_norm = track_input_norm(alias)
                exact_map[alias_norm] = meta
                cand_list.append({"norm": alias_norm, **meta})
        candidates_by_state[state] = cand_list

    return TrackResolverIndex(exact_map=exact_map, candidates_by_state=candidates_by_state)


class TrackResolveError(Exception):
    pass


def _iter_candidates(index: TrackResolverIndex, state_hint: Optional[str]) -> Iterable[Dict[str, str]]:
    if state_hint and state_hint in index.candidates_by_state:
        yield from index.candidates_by_state[state_hint]
    else:
        for cand_list in index.candidates_by_state.values():
            yield from cand_list


def resolve_track(
    raw: str,
    index: TrackResolverIndex,
    state_hint: Optional[str] = None,
    max_high: int = 2,
    max_med: int = 3,
) -> TrackResolutionResult:
    norm = track_input_norm(raw)

    if norm in index.exact_map:
        meta = index.exact_map[norm]
        return TrackResolutionResult(
            input=raw,
            resolved=ResolvedTrack(
                input=raw,
                canonical=meta["canonical"],
                state=meta["state"],
                code=meta["code"],
                confidence="HIGH",
                match_source="EXACT_OR_ALIAS",
            )
        )

    best: Optional[Tuple[int, Dict[str, str]]] = None
    for cand in _iter_candidates(index, state_hint):
        d = Levenshtein.distance(norm, cand["norm"])
        if best is None or d < best[0]:
            best = (d, cand)

    if best is None:
        return TrackResolutionResult(input=raw, error="NO_CANDIDATES")

    dist, cand = best
    if dist <= max_high:
        conf = "HIGH"
    elif dist <= max_med:
        conf = "MED"
    else:
        return TrackResolutionResult(input=raw, error=f"NO_MATCH (best='{cand['canonical']}', dist={dist})")

    return TrackResolutionResult(
        input=raw,
        resolved=ResolvedTrack(
            input=raw,
            canonical=cand["canonical"],
            state=cand["state"],
            code=cand["code"],
            confidence=conf,
            match_source="FUZZY_ALIAS",
        )
    )


def resolve_tracks(inputs: List[str], registry: TrackRegistry, state_hint: Optional[str] = None) -> List[ResolvedTrack]:
    index = build_track_resolver_index(registry)
    out: List[ResolvedTrack] = []
    for raw in inputs:
        res = resolve_track(raw, index=index, state_hint=state_hint)
        if res.resolved is None:
            raise TrackResolveError(f"Could not resolve '{raw}': {res.error}")
        out.append(res.resolved)
    return out
