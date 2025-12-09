import json
from turf.models import TrackRegistry
from turf.resolver import resolve_tracks

def load_seed():
    with open('data/nsw_seed.json','r') as f:
        return TrackRegistry.model_validate_json(f.read())

def test_resolve_exact():
    reg = load_seed()
    out = resolve_tracks(["Randwick"], reg)
    assert out[0].canonical == "Royal Randwick"
    assert out[0].state == "NSW"

def test_resolve_alias():
    reg = load_seed()
    out = resolve_tracks(["wagga riverside"], reg)
    assert out[0].canonical == "Wagga"

def test_resolve_fuzzy_high():
    reg = load_seed()
    # 'werigee' should map to Werribee when present; in NSW seed it won't exist.
    # Use a typo on Ballina
    out = resolve_tracks(["balllina"], reg)
    assert out[0].canonical == "Ballina"
    assert out[0].confidence in ("HIGH","MED")
