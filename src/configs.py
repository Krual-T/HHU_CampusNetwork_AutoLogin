from dotenv import load_dotenv
import os

load_dotenv()

PORTAL_USERNAME = os.environ.get("PORTAL_USERNAME","your Student ID")
PORTAL_PASSWORD = os.environ.get("PORTAL_PASSWORD","your Plaintext Password")
SERVICE_NAME = os.environ.get("SERVICE_NAME","中国移动(CMCC NET)")
