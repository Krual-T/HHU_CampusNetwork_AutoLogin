import os
import sys
from dotenv import load_dotenv

# --- Configuration Loading ---

def get_executable_path():
    """
    Get the absolute path to the directory where the .exe is running,
    or the directory where the .py script is located.
    
    This ensures the script can find its .env file, even when
    run by Windows Task Scheduler (which has a default CWD of System32).
    """
    if getattr(sys, 'frozen', False):
        # We are running in a bundled .exe (e.g., PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # We are running in a normal Python environment (for testing)
        return os.path.dirname(os.path.abspath(__file__))

# Build the absolute path to the .env file
# This is the crucial part for reliability.
BASE_DIR = get_executable_path()
dotenv_path = os.path.join(BASE_DIR, '.env')

# Load the .env file from the correct, absolute path
load_dotenv(dotenv_path)

# --- Application Settings ---

# The target Wi-Fi network name (SSID) to trigger the login.
# Default: "Hohai University"
TARGET_SSID = os.environ.get("TARGET_SSID", "Hohai University")

# Debug mode. Set to "true" in .env to show the console window on launch.
# Any of ("true", "1", "t") will activate it.
DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")

# --- User Credentials ---
# These are loaded from the .env file after installation.

# Your portal username (e.g., Student ID).
# Default: None (will be read from .env)
PORTAL_USERNAME = os.environ.get("PORTAL_USERNAME","your student id")

# Your portal password (in plaintext).
# Default: None (will be read from .env)
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD","your campus-network password")

# (Optional) The service provider name if your portal requires it.
# e.g., "中国移动(CMCC NET)" or leave blank if not needed.
SERVICE_NAME = os.environ.get("SERVICE_NAME", "")

# --- (Optional) Sanity Check for Debugging ---
# This block will print a warning if DEBUG is on but credentials are missing.
if DEBUG and (not PORTAL_USERNAME or not PORTAL_PASSWORD):
    print(f"[DEBUG] WARNING: PORTAL_USERNAME or PORTAL_PASSWORD is not set in .env.")
    print(f"[DEBUG]   Attempted to load .env from: {dotenv_path}")
    # You might want to uncomment the line below for pausing in debug mode
    # os.system("pause")