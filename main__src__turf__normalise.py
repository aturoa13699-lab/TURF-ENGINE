import unicodedata
import re

def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def remove_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def remove_punct(s: str) -> str:
    return re.sub(r"[^\w\s]", " ", s)

def track_input_norm(name: str) -> str:
    s = norm_spaces(name)
    s = remove_accents(s)
    s = remove_punct(s)
    s = norm_spaces(s)
    return s.upper()
