"""
Test resolve_location_id with the value from the log.
Run from project root: python tools/test_resolve_location_id.py
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "ftrack_plugins"))

# Value from user log (transfer target location not found)
FROM_LOG = "6c73a09a-0931-450a-b824-260c9f79"
# Full uuid (same prefix + full last segment)
FULL_UUID = "6c73a09a-0931-450a-b824-260c9f79eb37"

def main():
    from ftrack_inout.publisher.core.transfer_after_publish import (
        _normalize_location_id,
        resolve_location_id,
        _UUID_RE,
        _UUID_DASHED_RE,
    )

    print("=" * 60)
    print("Input from log:", repr(FROM_LOG))
    print("  len(with dashes):", len(FROM_LOG))
    print("  len(no dashes):  ", len(FROM_LOG.replace("-", "")))
    print()
    print("Full uuid:        ", repr(FULL_UUID))
    print("  len(with dashes):", len(FULL_UUID))
    print("  len(no dashes):  ", len(FULL_UUID.replace("-", "")))
    print()

    # Regex match?
    print("_UUID_RE.match(FROM_LOG):           ", _UUID_RE.match(FROM_LOG))
    print("_UUID_RE.match(FROM_LOG.replace('-','')):", _UUID_RE.match(FROM_LOG.replace("-", "")))
    print("_UUID_DASHED_RE.match(FROM_LOG):    ", _UUID_DASHED_RE.match(FROM_LOG))
    print("_UUID_DASHED_RE.match(FULL_UUID):   ", _UUID_DASHED_RE.match(FULL_UUID))
    print()

    # _normalize_location_id
    norm_log = _normalize_location_id(FROM_LOG)
    norm_full = _normalize_location_id(FULL_UUID)
    print("_normalize_location_id(FROM_LOG): ", repr(norm_log))
    print("_normalize_location_id(FULL_UUID):", repr(norm_full))
    print()

    # With session
    session = None
    try:
        from ftrack_inout.common.session_factory import get_shared_session
        session = get_shared_session()
    except Exception as e:
        print("Session not available:", e)
        print("(Set FTRACK_SERVER, FTRACK_API_KEY, FTRACK_API_USER to test resolve_location_id with session)")
        return

    if session:
        res_log = resolve_location_id(session, FROM_LOG)
        res_full = resolve_location_id(session, FULL_UUID)
        print("resolve_location_id(session, FROM_LOG): ", repr(res_log))
        print("resolve_location_id(session, FULL_UUID):", repr(res_full))
    print()
    print("CONCLUSION: FROM_LOG is truncated (32 chars, 28 hex). Full UUID is 36 chars.")
    print("Truncation happens BEFORE resolve_location_id (e.g. HDA string parm length = 32).")
    print("Fix: set transfer_target_location string parameter length to at least 37 in HDA.")
    print("=" * 60)

if __name__ == "__main__":
    main()
