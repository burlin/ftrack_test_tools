"""
Safe launcher for browser that handles errors gracefully.
Use this when running in interactive terminal or through pipes.
"""
import sys
import os
from pathlib import Path

# Ensure tools is in path for run_browser import
_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

# Redirect stderr to stdout for better pipe handling
# But keep stdout for Qt messages
if not sys.stdout.isatty():
    # If stdout is redirected, create a separate log file
    log_file = Path(__file__).parent / "browser_safe.log"
    sys.stderr = open(log_file, 'w', encoding='utf-8')
    print(f"[run_browser_safe] Logging to {log_file}", file=sys.stderr)

try:
    from run_browser import main
    main()
except KeyboardInterrupt:
    print("\n[run_browser_safe] Interrupted by user", file=sys.stderr)
    sys.exit(0)
except Exception as e:
    import traceback
    print(f"[run_browser_safe] Fatal error: {e}", file=sys.stderr)
    print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
    sys.exit(1)
