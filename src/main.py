import logging
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.configs import PORTAL_PASSWORD, PORTAL_USERNAME, SERVICE_NAME

# Captive portal probe address that triggers redirect.
CHECK_URL = "http://10.96.0.155"
LOGIN_SUCCESS_TITLE = "登录成功"
SUCCESS_KEYWORD = "成功"

logger = logging.getLogger(__name__)


def configure_logging(level: int | None = None) -> None:
    """
    Configure logging so verbose diagnostics are only emitted while __debug__ is True.
    Running the script via `python -O -m src.main` disables __debug__, causing the default
    log level to raise to INFO and hiding debug-only chatter.
    """
    resolved_level = level if level is not None else (logging.DEBUG if __debug__ else logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def login_with_selenium() -> None:
    """Automate the captive-portal login via Selenium."""
    logger.debug("Preparing Chrome driver options.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    script_path = os.path.abspath(__file__)
    src_dir = os.path.dirname(script_path)
    project_root = os.path.dirname(src_dir)
    driver_path = os.path.join(project_root, "chromedriver.exe")

    if not os.path.exists(driver_path):
        logger.error("chromedriver.exe not found at %s", driver_path)
        logger.error("Download chromedriver.exe manually and place it in the project root directory.")
        sys.exit(1)

    logger.debug("Launching Chrome with driver %s", driver_path)
    service = Service(driver_path)

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.debug("Headless Chrome started; requesting %s", CHECK_URL)

        driver.get(CHECK_URL)
        if driver.title == LOGIN_SUCCESS_TITLE:
            logger.info("Already logged in to the campus network.")
            return

        wait = WebDriverWait(driver, 10)
        logger.debug("Waiting for login button to become clickable.")
        login_button = wait.until(EC.element_to_be_clickable((By.ID, "loginLink")))
        logger.debug("Login page is ready.")

        logger.debug("Waiting for username field to be present.")
        username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        logger.debug("Injecting username.")
        driver.execute_script("arguments[0].value = arguments[1];", username_field, PORTAL_USERNAME)

        logger.debug("Waiting for password field to be present.")
        password_field = wait.until(EC.presence_of_element_located((By.ID, "pwd")))
        logger.debug("Injecting password.")
        driver.execute_script("arguments[0].value = arguments[1];", password_field, PORTAL_PASSWORD)

        logger.debug("Selecting service %s via selectService().", SERVICE_NAME)
        driver.execute_script("selectService(arguments[0], arguments[1], '1');", SERVICE_NAME, SERVICE_NAME)

        login_button.click()
        logger.debug("Login submitted; waiting for confirmation title.")

        while driver.title != LOGIN_SUCCESS_TITLE:
            time.sleep(1)

        current_title = driver.title
        if SUCCESS_KEYWORD in driver.current_url or SUCCESS_KEYWORD in current_title:
            logger.info("🎉 Login succeeded.")
        else:
            try:
                error_msg = driver.find_element(By.ID, "errorMsg").text
                logger.warning("Login failed: %s", error_msg)
            except Exception:
                logger.error("Login appears to have failed; no explicit error message found.")
                logger.error("Current URL: %s", driver.current_url)

    except Exception:
        logger.exception("Unexpected error during login.")
    finally:
        if driver:
            driver.quit()
            logger.debug("Browser closed.")


if __name__ == "__main__":
    configure_logging()
    login_with_selenium()
