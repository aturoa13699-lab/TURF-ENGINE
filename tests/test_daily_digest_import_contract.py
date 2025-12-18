import inspect

import turf.daily_digest as d


def test_daily_digest_signature_has_write_per_meeting() -> None:
    sig = inspect.signature(d.build_daily_digest)
    assert "write_per_meeting" in str(sig)
