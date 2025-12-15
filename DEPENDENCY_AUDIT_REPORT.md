# Dependency Audit Report
**Date:** 2025-12-15
**Project:** TURF-ENGINE (turf-registry-resolver)

## Executive Summary

The project has **0 security vulnerabilities** but contains **2 unused dependencies** (13% bloat) and several **outdated packages** that should be updated to their latest versions.

---

## 🔒 Security Vulnerabilities

✅ **PASSED** - No known security vulnerabilities detected by pip-audit

All dependencies and their transitive dependencies are free from known CVEs.

---

## 📦 Outdated Packages

The following packages have newer versions available:

| Package | Current Min Version | Latest Version | Status |
|---------|-------------------|----------------|--------|
| `pydantic` | ≥2.5 | **2.12.5** | ⚠️ Outdated |
| `rapidfuzz` | ≥3.9 | **3.14.3** | ⚠️ Outdated |
| `typer` | ≥0.12 | **0.20.0** | ⚠️ Outdated |
| `rich` | ≥13.7 | **14.2.0** | ⚠️ Outdated |
| `httpx` | ≥0.28.1 | **0.28.1** | ✅ Current (but unused) |
| `selectolax` | ≥0.4.6 | **0.4.6** | ✅ Current |
| `lxml` | ≥5.3.0 | **6.0.2** | ⚠️ Outdated (and unused) |
| `pytest` | ≥8.0 | **9.0.2** | ⚠️ Outdated |

---

## 🧹 Dependency Bloat Analysis

### ❌ Unused Dependencies (REMOVE)

**1. `httpx` (≥0.28.1)**
- **Status:** Not imported anywhere in the codebase
- **Reason for inclusion:** Likely intended for future web scraping
- **Current usage:** The project only parses HTML files from disk (demo_meeting.html, demo_odds.html)
- **Recommendation:** **REMOVE** - Add back when actual web scraping is implemented
- **Impact:** Reduces dependencies and installation size

**2. `lxml` (≥5.3.0)**
- **Status:** Not imported anywhere in the codebase
- **Reason for inclusion:** Possibly thought to be a dependency of selectolax
- **Actual facts:** selectolax has ZERO dependencies and was built as a faster alternative to lxml
- **Recommendation:** **REMOVE** - Not needed by selectolax or any other part of the project
- **Impact:** Removes unnecessary C-extension dependency

### ⚠️ Potentially Over-Engineered Dependencies

**`rich` (≥13.7)**
- **Current usage:** Only used for `from rich import print` in turf/cli.py:9
- **Consideration:** rich is a heavy dependency (~150KB) used only for colored terminal output
- **Alternative:** Could use standard `print()` or lighter alternatives like `colorama`
- **Recommendation:** **KEEP** - While light usage, rich provides good UX for CLI applications and typer integrates well with it

---

## 📊 Dependency Usage Summary

### Core Dependencies (KEEP)
| Package | Usage | Justification |
|---------|-------|---------------|
| `pydantic` | turf/models.py | Data validation and modeling (essential) |
| `rapidfuzz` | turf/resolver.py | Fuzzy track name matching (core feature) |
| `typer` | turf/cli.py, cli/turf_cli.py | CLI framework (core feature) |
| `rich` | turf/cli.py | Terminal output formatting (UX enhancement) |
| `selectolax` | turf/parse_ra.py, turf/parse_odds.py | Fast HTML parsing (core feature) |

### Development Dependencies (KEEP)
| Package | Usage | Justification |
|---------|-------|---------------|
| `pytest` | test_*.py files | Testing framework (essential for dev) |

### Discrepancy: requirements.txt vs pyproject.toml
- `pytest` is in requirements.txt but NOT in pyproject.toml dependencies
- **Recommendation:** Move pytest to `[project.optional-dependencies]` under a `dev` or `test` group

---

## 🎯 Recommendations

### 1. Remove Unused Dependencies (HIGH PRIORITY)

Remove `httpx` and `lxml` from both requirements.txt and pyproject.toml:

**Before:**
```toml
dependencies = [
    "pydantic>=2.5",
    "rapidfuzz>=3.9",
    "typer>=0.12",
    "rich>=13.7",
    "httpx>=0.28.1",      # ❌ Remove
    "selectolax>=0.4.6",
    "lxml>=5.3.0"         # ❌ Remove
]
```

**After:**
```toml
dependencies = [
    "pydantic>=2.5",
    "rapidfuzz>=3.9",
    "typer>=0.12",
    "rich>=13.7",
    "selectolax>=0.4.6"
]
```

### 2. Update to Latest Versions (MEDIUM PRIORITY)

Update minimum versions to benefit from bug fixes and improvements:

```toml
dependencies = [
    "pydantic>=2.12.5",
    "rapidfuzz>=3.14.3",
    "typer>=0.20.0",
    "rich>=14.2.0",
    "selectolax>=0.4.6"
]
```

### 3. Reorganize Test Dependencies (MEDIUM PRIORITY)

Move pytest to optional dependencies in pyproject.toml:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=9.0.2"
]
```

Then update installation instructions:
```bash
pip install -e ".[dev]"  # For development
pip install -e .         # For production use
```

### 4. Add When Needed (FUTURE)

If you implement actual web scraping in the future:
```toml
# Add back when implementing web scraping
# "httpx>=0.28.1",
```

---

## 📈 Impact Summary

| Metric | Current | After Changes | Improvement |
|--------|---------|---------------|-------------|
| Total dependencies | 8 | 6 | -25% |
| Unused dependencies | 2 | 0 | -100% |
| Up-to-date packages | 2/8 (25%) | 5/5 (100%) | +75% |
| Security vulnerabilities | 0 | 0 | ✅ |

---

## 🔄 Implementation Steps

1. **Backup current state**
   ```bash
   cp requirements.txt requirements.txt.backup
   cp pyproject.toml pyproject.toml.backup
   ```

2. **Update pyproject.toml** (apply recommendations 1-3)

3. **Update requirements.txt** to match pyproject.toml

4. **Test the changes**
   ```bash
   python -m venv test_env
   source test_env/bin/activate
   pip install -e ".[dev]"
   pytest
   ```

5. **Verify all CLI commands work**
   ```bash
   turf --help
   turf resolve --help
   turf ra parse --help
   ```

6. **Commit changes**
   ```bash
   git add pyproject.toml requirements.txt
   git commit -m "Remove unused dependencies and update to latest versions"
   ```

---

## Sources

- [selectolax PyPI](https://pypi.org/project/selectolax/)
- [selectolax GitHub](https://github.com/rushter/selectolax)
- [Beyond lxml: Faster parsing with selectolax](https://dev.to/mohammadraziei/beyond-lxml-faster-and-more-pythonic-parsing-with-pygixml-and-selectolax-278h)

---

## Conclusion

This project maintains good dependency hygiene with no security vulnerabilities. By removing the 2 unused dependencies (httpx and lxml) and updating to the latest package versions, the project will be leaner, more maintainable, and better positioned for future development.
