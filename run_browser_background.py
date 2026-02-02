"""
Background launcher for browser with logging to file.
"""
import sys
import os
from pathlib import Path

# Redirect output to log file
log_file = Path(__file__).parent / "browser_test.log"
sys.stdout = open(log_file, 'w', encoding='utf-8')
sys.stderr = sys.stdout

print("=" * 80)
print("BROWSER BACKGROUND LAUNCHER")
print("=" * 80)
print(f"Log file: {log_file}")
print("=" * 80)

# Import and run browser
try:
    from run_browser import main
    main()
except Exception as e:
    import traceback
    print(f"\n[ERROR] Browser failed to start: {e}")
    print("\nTraceback:")
    traceback.print_exc()
    sys.stdout.flush()
