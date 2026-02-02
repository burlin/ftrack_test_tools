"""
Convenient launcher for Ftrack Browser in separate process.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Launch browser in separate process"""
    script_dir = Path(__file__).parent
    browser_script = script_dir / "run_browser_background.py"
    
    if not browser_script.exists():
        print(f"[ERROR] Browser script not found: {browser_script}")
        sys.exit(1)
    
    print("=" * 80)
    print("LAUNCHING FTRACK BROWSER")
    print("=" * 80)
    print(f"Script: {browser_script}")
    print(f"Log file: {script_dir / 'browser_test.log'}")
    print("=" * 80)
    print("\nBrowser will open in a separate window.")
    print("Check browser_test.log for detailed logs.\n")
    
    # Launch in separate process
    try:
        subprocess.Popen(
            [sys.executable, str(browser_script)],
            cwd=str(script_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        print("[OK] Browser process started")
        print("\nTo view logs:")
        print(f"  Get-Content {script_dir / 'browser_test.log'} -Tail 50")
    except Exception as e:
        print(f"[ERROR] Failed to start browser: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
