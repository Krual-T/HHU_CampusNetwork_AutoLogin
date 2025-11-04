import os
import time
import sys
import subprocess
import re
from configs import PORTAL_USERNAME, PORTAL_PASSWORD, SERVICE_NAME,DEBUG,TARGET_SSID

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

def get_current_ssid():
    """
    使用 netsh 命令获取当前连接的 Wi-Fi SSID (已修复编码问题)
    """
    try:
        # [!!] 修改 1: 移除 text=True 和 encoding='gbk' [!!]
        # 我们现在捕获原始字节(bytes)
        output = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True,
            check=True
        )
        
        # [!!] 修改 2: 手动进行“容错”解码 [!!]
        # 这会把 'gbk' 无法识别的字节(如 0xaa) 替换为 '?'，从而避免崩溃
        stdout_str = output.stdout.decode('gbk', errors='replace')

        # [!!] 修改 3: 对“清理后”的字符串进行搜索 [!!]
        match = re.search(r"SSID\s+:\s+(.+)\r", stdout_str)
        if match:
            ssid = match.group(1).strip()
            log_debug(f"检测到当前 SSID: {ssid}")
            return ssid
        else:
            log_debug("未检测到活动的 Wi-Fi 连接。")
            return None
    except Exception as e:
        # [!!] 现在的错误捕获会更清晰 [!!]
        log_debug(f"获取 SSID 时出错: {e}")
        return None


def log_debug(message):
    """一个简单的辅助函数，只在 DEBUG 模式下打印"""
    if DEBUG:
        print(message)

# --- 2. 检查 .env 变量 (我们用断言来代替 print) ---
# 断言（assert）是一种“速错”机制，如果条件为假，它会立即停止脚本并报错
# 这比我们之前使用的 if...sys.exit(1) 更简洁
assert PORTAL_USERNAME, "错误：PORTAL_USERNAME 未在 .env 或 src/configs 中设置"
assert PORTAL_PASSWORD, "错误：PORTAL_PASSWORD 未在 .env 或 src/configs 中设置"
assert SERVICE_NAME, "错误：SERVICE_NAME 未在 .env 或 src/configs 中设置"

# 用于触发重定向的检测地址
CHECK_URL = "http://10.96.0.155" # 使用您本地的 IP (很好)

def login_with_selenium():
    """
    使用 Selenium (Chrome 驱动) 自动登录 (带 Debug 模式的健壮版)
    """
    current_ssid = get_current_ssid()
    if current_ssid != TARGET_SSID:
        # 使用 print 而不是 log_debug，因为这是一个明确的“跳过”信息
        print(f"当前网络非 '{TARGET_SSID}' (是 {current_ssid})。无需登录，退出。")
        return # 正常退出
    log_debug("初始化 Chrome 驱动...")
    
    # --- 3. 设置 Chrome 选项 ---
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # [!!] 修复: 移除导致 JS 崩溃的激进优化 [!!]
    # chrome_options.add_argument("--disable-gpu") 
    # chrome_options.add_argument("--disable-extensions")
    # chrome_options.add_argument("--blink-settings=imagesEnabled=false") # 这是上次JS崩溃的元凶

    chrome_options.add_argument("--log-level=3") 
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    # --- 4. 驱动路径 (不变) ---
    script_path = os.path.abspath(__file__)
    src_dir = os.path.dirname(script_path)
    project_root = os.path.dirname(src_dir)
    DRIVER_PATH = os.path.join(project_root, "chromedriver.exe")

    if not os.path.exists(DRIVER_PATH):
        print(f"错误：未在以下路径找到驱动: {DRIVER_PATH}")
        sys.exit(1)
        
    log_debug(f"正在使用本地驱动: {DRIVER_PATH}")
    service = Service(DRIVER_PATH)
    
    driver = None
    try:
        # --- 5. 启动浏览器 ---
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_debug("浏览器已启动 (无头模式)。正在访问检测网址...")
        
        driver.get(CHECK_URL)
        
        # [!!] 修复: 您添加的“已登录”检查 (很好!) [!!]
        # 我们用 .title.startswith() 来防止页面标题后面有其他字符
        if driver.title.startswith('登录成功'):
            print('检测到已登录校园网，无需重复操作。')
            return # 成功退出
            
        # --- 6. 使用我们验证过的“发令枪”逻辑 ---
        wait = WebDriverWait(driver, 10) 
        
        log_debug("等待登录页面重定向并*完全*加载 (等待登录按钮变为可点击)...")
        login_button = wait.until(
            EC.element_to_be_clickable((By.ID, "loginLink"))
        )
        log_debug("登录页面已完全加载。")

        # --- 7. 原子化注入 (修复竞态条件) ---
        # [!!] 修复: 移除了多余的 wait.until()，因为页面已加载 [!!]
        log_debug("使用 JavaScript 强行填充用户名...")
        driver.execute_script(f"document.getElementById('username').value = '{PORTAL_USERNAME}';")

        log_debug("使用 JavaScript 强行填充密码...")
        driver.execute_script(f"document.getElementById('pwd').value = '{PORTAL_PASSWORD}';")
        
        log_debug(f"正在直接调用 selectService('{SERVICE_NAME}','{SERVICE_NAME}','1')...")
        driver.execute_script(
            f"selectService('{SERVICE_NAME}','{SERVICE_NAME}','1');"
        )
        log_debug("服务商已设置。")
        
        # --- 8. 点击登录 ---
        log_debug("正在点击登录...")
        # [!!] 修复: 移除了重复的 .click() [!!]
        login_button.click()
        
        # --- 9. [!!] 智能断言 (修复无限循环) [!!] ---
        log_debug("点击完成，智能等待登录结果...")
        
        try:
            # 这就是我们的“断言”：
            # 在10秒内，URL 必须包含 "success" 
            # 或者 "errorInfo_center" 必须出现
            wait.until(
                EC.any_of(
                    EC.url_contains("success"), 
                    EC.presence_of_element_located((By.ID, "errorInfo_center")) 
                )
            )
        except Exception:
             log_debug("等待结果超时，继续检查...")
        
        # --- 10. 最终验证 ---
        current_title = driver.title
        log_debug(f"当前页面标题: {current_title}")
        
        if "success" in driver.current_url or "成功" in current_title:
            print("\n🎉 登录成功！") # 保留这个，作为非 debug 模式的输出
        else:
            try:
                # 检查错误信息
                error_msg_element = driver.find_element(By.ID, "errorInfo_center")
                error_msg = error_msg_element.text
                if error_msg:
                     print(f"\n❌ 登录失败: {error_msg}") # 保留这个
                else:
                     print("\n❌ 登录似乎失败了（未找到错误消息）。") # 保留这个
            except:
                print(f"\n❌ 登录似乎失败了。当前 URL: {driver.current_url}") # 保留这个

    except Exception as e:
        import traceback
        print(f"脚本执行出错: {traceback.format_exc()}")
        
    finally:
        # --- 11. 关闭浏览器 ---
        if driver:
            driver.quit()
            log_debug("浏览器已关闭。")

if __name__ == "__main__":
    login_with_selenium()