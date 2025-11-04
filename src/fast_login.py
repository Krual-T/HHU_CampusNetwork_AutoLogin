import os
import sys
import re
import requests
import urllib.parse
import time
import subprocess
from configs import DEBUG,TARGET_SSID,PORTAL_USERNAME,PORTAL_PASSWORD,SERVICE_NAME

def setup_debug_console():
    """
    If DEBUG=True and the script is run as a "windowless" .exe,
    this function will force the creation of a console window to display the log_debug() output.
    """
    if DEBUG and getattr(sys, 'frozen', False):
        try:
            import ctypes
            if ctypes.windll.kernel32.GetConsoleWindow() == 0:
                if ctypes.windll.kernel32.AllocConsole() != 0:
                    # 将 Python 的 stdout/stderr 重定向到这个新窗口 (UTF-8 编码以支持符号)
                    sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
                    sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
                else:
                    pass
        except Exception:
            pass

setup_debug_console()

# Headers to impersonate a Chrome browser for the GET request
GET_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

# Headers for the POST login request (mimicking AuthInterFace.js)
POST_HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01', 
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' 
}

# We use the gateway IP to trigger the redirect "maze"
CHECK_URL = "http://10.96.0.155"
# The final login API endpoint
LOGIN_URL = "http://eportal.hhu.edu.cn/eportal/InterFace.do?method=login"


# --- 2. Helper Functions ---

def log_debug(message: str):
    """
    [!!] 已美化 [!!]
    Helper function to log messages only in DEBUG mode.
    (已修复无限递归的BUG)
    """
    if DEBUG:
        prefix = "ℹ️ "  # 默认: 信息
        msg_lower = message.lower()
        
        # --- 状态关键词 (最高优先级) ---
        if "success" in msg_lower or "🎉" in message or "already logged in" in msg_lower:
            prefix = "✅ "
        elif "fail" in msg_lower or "error" in msg_lower or "❌" in message or "not connected" in msg_lower or "is not" in msg_lower:
            prefix = "❌ "
            
        # --- 动作关键词 (中优先级) ---
        elif "attempt" in msg_lower or "sending" in msg_lower or "starting" in msg_lower or "preparing" in msg_lower or "visiting" in msg_lower:
            prefix = "▶️ "
        elif "parsing" in msg_lower or "detected" in msg_lower or "extracted" in msg_lower or "found" in msg_lower:
            prefix = "🔍 "
        elif "network" in msg_lower or "ssid" in msg_lower:
            prefix = "🌐 "

        # --- 特殊关键词 ---
        elif "process finished" in msg_lower:
            prefix = "🏁 "
        elif "response" in msg_lower:
            prefix = "💬 "

        print(f"{prefix} {message}")


def get_current_ssid() -> str | None:
    """
    Uses netsh to get the current Wi-Fi SSID.
    (Fixed encoding issues for Windows)
    """
    try:
        # Run netsh command, capture raw bytes
        output = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        # Decode using 'gbk' (common for Chinese Windows) with error replacement
        stdout_str = output.stdout.decode('gbk', errors='replace')
        
        match = re.search(r"SSID\s+:\s+(.+)\r", stdout_str)
        if match:
            ssid = match.group(1).strip()
            log_debug(f"Detected current SSID: {ssid}")
            return ssid
        else:
            log_debug("No active Wi-Fi connection detected.")
            return None
    except Exception as e:
        log_debug(f"Error getting SSID: {e}")
        return None

# --- 3. Main Login Function ---

def do_login():
    """Executes the full login process."""
    
    # Step 1: Check Network Name
    current_ssid = get_current_ssid()
    if current_ssid != TARGET_SSID:
        # This is a final status, so it always prints.
        log_debug(f"Current network is not '{TARGET_SSID}' (it's {current_ssid}). Skipping login.")
        return

    log_debug(f"Connected to target network: {TARGET_SSID}. Starting login...")
    
    session = requests.Session()
    session.headers.update(GET_HEADERS) # Set default headers for the session

    # Step 2: Get dynamic parameters (with retry logic)
    landing_page_html = None 
    
    for attempt in range(1, 4): # Max 3 attempts
        log_debug(f"  Attempt {attempt} to get dynamic parameters (visiting {CHECK_URL})...")
        try:
            r = session.get(CHECK_URL, timeout=5, allow_redirects=True)
            
            # Check if we are already logged in
            if "success" in r.url:
                log_debug("Already logged in. No action needed.")
                return 

            # Check if we landed on the "JS Jump Pad" page
            if "123.123.123.123" in r.url:
                log_debug(f"  Successfully landed on 'JS Jump Pad' page: {r.url}")
                landing_page_html = r.text 
                break # Success, exit the loop
            else:
                log_debug(f"  Did not redirect to 'JS Jump Pad' page. Current URL: {r.url}")
        
        except requests.exceptions.RequestException as e:
            log_debug(f"  Attempt {attempt} network connection failed: {e}")
        
        if attempt < 3:
            log_debug("  Retrying in 2 seconds...")
            time.sleep(2)
    
    # Check if the loop failed
    if landing_page_html is None:
        log_debug("❌ Login Failed: Could not get 'JS Jump Pad' page after 3 attempts. Exiting.")
        return

    # Step 3: Parse the "Golden Ticket" (the JS redirect)
    log_debug("  Parsing 'JS Jump Pad' to get index.jsp URL...")
    match = re.search(r"top\.self\.location\.href='(http.*?index\.jsp\?.*?)'", landing_page_html)
    
    if not match:
        log_debug("❌ Login Failed: Could not extract index.jsp URL from 'JS Jump Pad' source. Exiting.")
        return
    
    final_login_url = match.group(1)
    log_debug(f"  Successfully extracted 'Golden Ticket' URL: {final_login_url[:50]}...")
    
    parsed_url = urllib.parse.urlparse(final_login_url)
    query_string = parsed_url.query 
    log_debug(f"  Successfully got dynamic token: queryString={query_string[:20]}...")

    # Step 4: Prepare Payload (No Encryption Needed)
    log_debug("Preparing final payload...")
    
    # Double URL-encode all fields (as done by doauthen.js)
    user_id_encoded = urllib.parse.quote(urllib.parse.quote(PORTAL_USERNAME))
    password_encoded = urllib.parse.quote(urllib.parse.quote(PORTAL_PASSWORD)) 
    service_encoded = urllib.parse.quote(urllib.parse.quote(SERVICE_NAME))
    query_string_encoded = urllib.parse.quote(urllib.parse.quote(query_string)) 
    # We explicitly state that we are NOT sending an encrypted password
    encrypt_encoded = urllib.parse.quote(urllib.parse.quote('false')) 

    # Manually build the content string (to bypass requests' auto-encoding)
    content_string = (
        f"userId={user_id_encoded}"
        f"&password={password_encoded}"
        f"&service={service_encoded}"
        f"&queryString={query_string_encoded}"
        f"&operatorPwd="
        f"&operatorUserId="
        f"&validcode="
        f"&passwordEncrypt={encrypt_encoded}" # This key is from AuthInterFace.js
    )
    
    # Step 5: Send Login Request
    try:
        log_debug("Sending login request...")
        r_login = session.post(
            LOGIN_URL, 
            data=content_string, # Send the raw string
            timeout=5,
            headers=POST_HEADERS # Use the special POST headers
        )
        
        r_login.encoding = 'utf-8' # Force UTF-8 to fix garbled text
        response_text = r_login.text
        
        log_debug(f"Server Response: {response_text}")
        
        if '"result":"success"' in response_text:
            log_debug("\n🎉 Login Successful!")
        else:
            msg_match = re.search(r'"message":"(.*?)"', response_text)
            if msg_match:
                message = msg_match.group(1)
                log_debug(f"\n❌ Login Failed: {message}")
            else:
                log_debug("\n❌ Login Failed: Unknown response.")
                
    except requests.exceptions.RequestException as e:
        log_debug(f"Login request failed: {e}")

# --- 4. Main Execution ---
if __name__ == "__main__":
    try:
        do_login()
    except Exception as e:
        log_debug(f"An unexpected top-level error occurred: {e}")
    
    if DEBUG:
        print("\n" + "="*40)
        log_debug(f"Debug mode: Process finished.")
        print("="*40)
        os.system("pause")