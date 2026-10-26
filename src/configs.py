"""Configuration shared by the source entry point and the packaged executable."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def get_executable_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent)
    return str(Path(__file__).resolve().parent.parent)


BASE_DIR = get_executable_path()
dotenv_path = Path(BASE_DIR) / ".env"
load_dotenv(dotenv_path, override=False, interpolate=False)

TARGET_SSID = os.environ.get("TARGET_SSID", "Hohai University")
DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
PORTAL_USERNAME = os.environ.get("PORTAL_USERNAME", "")
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD", "")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "")
