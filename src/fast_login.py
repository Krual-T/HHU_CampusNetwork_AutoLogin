"""One bounded Windows captive-portal check, login, or own-session recovery."""

import argparse
import ctypes
import html
import json
import math
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import requests

import configs

CHECK_URL = "http://10.96.0.155"
API_URL = "http://eportal.hhu.edu.cn/eportal/InterFace.do?method="
PORTAL_HOSTS = {"10.96.0.155", "eportal.hhu.edu.cn"}
GET_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"}
POST_HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
ATTEMPTS = 3
COOLDOWN_SECONDS = 300


def emit(status):
    """Only fixed status codes reach logs; URLs, responses, and exceptions stay private."""
    if sys.stdout is not None:
        print(f"[HHU_LOGIN] {status}")


def normalize_mac(value):
    value = str(value).replace(":", "").replace("-", "").lower()
    return value if re.fullmatch(r"[0-9a-f]{12}", value) else ""


@dataclass(frozen=True)
class WifiIdentity:
    name: str
    ssid: str
    mac: str


def parse_wifi_interfaces(text):
    """Keep interface blocks together so multiple adapters cannot mix identities."""
    interfaces = []
    current = {}
    labels = {"name": "name", "名称": "name", "physical address": "mac", "物理地址": "mac"}
    for line in text.splitlines():
        match = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        label, value = match.groups()
        key = labels.get(label.lower(), "ssid" if label.upper() == "SSID" else None)
        if key == "name":
            if current:
                interfaces.append(current)
            current = {"name": value}
        elif key and current:
            current[key] = value
    if current:
        interfaces.append(current)
    return [
        WifiIdentity(item["name"], item["ssid"], normalize_mac(item.get("mac", "")))
        for item in interfaces
        if item.get("ssid") and normalize_mac(item.get("mac", ""))
    ]


def current_wifi():
    result = subprocess.run(
        ["netsh", "wlan", "show", "interfaces"],
        capture_output=True,
        check=True,
        timeout=5,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # netsh uses the active Windows OEM code page; GBK was used by the original script.
    code_page = ctypes.windll.kernel32.GetOEMCP()
    interfaces = parse_wifi_interfaces(result.stdout.decode(f"cp{code_page}", errors="replace"))
    return interfaces[0] if len(interfaces) == 1 else None


class NamedMutex:
    """Use the global namespace to cover both SYSTEM and interactive sessions."""

    def __init__(self, name=r"Global\HohaiAutoLogin"):
        self.name = name
        self.handle = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]

    def __enter__(self):
        ctypes.set_last_error(0)
        handle = self.kernel.CreateMutexW(None, True, self.name)
        error = ctypes.get_last_error()
        if not handle:
            if error == 5:  # An instance owned by another account may deny access.
                return False
            raise OSError("Single-instance mutex unavailable")
        if error == 183:
            self.kernel.CloseHandle(handle)
            return False
        self.handle = handle
        return True

    def __exit__(self, *_):
        if self.handle:
            self.kernel.ReleaseMutex(self.handle)
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def secure_directory(path):
    """Restrict saved account/session metadata to the running account and SYSTEM."""
    path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        check=True,
        timeout=5,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    sid = re.search(rb"S-1-\d+(?:-\d+)+", result.stdout)
    if not sid:
        raise OSError("Current account SID unavailable")
    grants = [f"*{sid.group().decode('ascii')}:(OI)(CI)F"]
    if sid.group() != b"S-1-5-18":
        grants.append("*S-1-5-18:(OI)(CI)F")
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", *grants],
        capture_output=True,
        check=True,
        timeout=5,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


class StateStore:
    def __init__(self, path=None):
        if path is None:
            local_appdata = os.environ.get("LOCALAPPDATA")
            if not local_appdata:
                raise OSError("LOCALAPPDATA unavailable")
            path = Path(local_appdata) / "HohaiAutoLogin" / "session.json"
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data):
        if self.load() == data:
            return
        secure_directory(self.path.parent)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as stream:
                pending = Path(stream.name)
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, self.path)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)


@dataclass(frozen=True)
class Probe:
    status: str
    query: str = ""
    user_index: str = ""


def portal_url(value, path):
    url = urlsplit(value)
    # The real portal also emits /eportal/./success.jsp (RFC 3986 dot-segments).
    if posixpath.normpath(url.path) != path or url.path.endswith("/"):
        return False
    if path == "/eportal/index.jsp":
        return (
            url.scheme == "http"
            and url.hostname in PORTAL_HOSTS
            and url.port in (None, 80, 8080)
            and url.username is None
            and url.password is None
        )
    return (
        url.scheme == "http"
        and url.hostname in PORTAL_HOSTS
        and url.port in (None, 80)
        and url.username is None
        and url.password is None
    )


def decode_probe(response):
    if portal_url(response.url, "/eportal/success.jsp"):
        indices = parse_qs(urlsplit(response.url).query).get("userIndex", [])
        return Probe("online", user_index=indices[0] if len(indices) == 1 else "")
    candidates = [response.url]
    candidates.extend(
        re.findall(r"(?:top\.self\.)?location\.href\s*=\s*['\"]([^'\"]+)['\"]", response.text)
    )
    for candidate in candidates:
        candidate = html.unescape(candidate)
        if portal_url(candidate, "/eportal/index.jsp") and urlsplit(candidate).query:
            return Probe("offline", query=urlsplit(candidate).query)
    return Probe("unavailable")


def login_payload(username, password, service, query):
    values = {
        "userId": username,
        "password": password,
        "service": service,
        "queryString": query,
        "operatorPwd": "",
        "operatorUserId": "",
        "validcode": "",
        "passwordEncrypt": "false",
    }
    return "&".join(f"{key}={quote(quote(value))}" for key, value in values.items())


def deadline(state, key):
    value = state.get(key, 0)
    return value if isinstance(value, (int, float)) and math.isfinite(value) else 0


class CampusLogin:
    def __init__(self, session, store, wifi=None, sleep=time.sleep, now=time.time):
        self.session = session
        self.session.trust_env = False
        self.session.headers.update(GET_HEADERS)
        self.store = store
        self.wifi = wifi or current_wifi
        self.sleep = sleep
        self.now = now

    def same_wifi(self, identity):
        return identity.ssid == configs.TARGET_SSID and self.wifi() == identity

    def probe(self, wait_online=False):
        result = Probe("unavailable")
        for attempt in range(ATTEMPTS):
            try:
                response = self.session.get(CHECK_URL, timeout=5, allow_redirects=True)
                response.raise_for_status()
                result = decode_probe(response)
                if result.status == "online" or (result.status == "offline" and not wait_online):
                    return result
            except requests.RequestException:
                pass
            if attempt + 1 < ATTEMPTS:
                self.sleep(attempt + 1)
        return result

    def api(self, method, data):
        response = self.session.post(
            API_URL + method, data=data, headers=POST_HEADERS, timeout=5, allow_redirects=False
        )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise TypeError("Unexpected portal JSON")
        return value

    def remember(self, identity, result, state):
        if result.user_index and self.same_wifi(identity):
            state["session"] = {
                "userId": configs.PORTAL_USERNAME,
                "userMac": identity.mac,
                "userIndex": result.user_index,
            }
            self.store.save(state)

    def authenticate(self, identity, query):
        for attempt in range(ATTEMPTS):
            if not self.same_wifi(identity):
                return {"result": "network_changed"}
            try:
                return self.api(
                    "login",
                    login_payload(
                        configs.PORTAL_USERNAME,
                        configs.PORTAL_PASSWORD,
                        configs.SERVICE_NAME,
                        query,
                    ),
                )
            except (requests.RequestException, ValueError, TypeError):
                # A lost POST response can follow a successful login. Check before resubmitting.
                result = self.probe(wait_online=True)
                if result.status == "online":
                    return {"result": "success"}
            if attempt + 1 < ATTEMPTS:
                self.sleep(attempt + 1)
        return {"result": "unavailable"}

    def recover(self, identity, state):
        saved = state.get("session")
        if not isinstance(saved, dict):
            emit("limit_no_saved_session")
            return False
        index = saved.get("userIndex")
        if (
            not isinstance(index, str)
            or not index
            or saved.get("userId") != configs.PORTAL_USERNAME
            or saved.get("userMac") != identity.mac
            or not self.same_wifi(identity)
        ):
            emit("limit_identity_unconfirmed")
            return False
        if self.now() < deadline(state, "recoveryRetryAfter"):
            emit("recovery_cooldown")
            return False
        try:
            info = self.api("getOnlineUserInfo", {"userIndex": index})
        except (requests.RequestException, ValueError, TypeError):
            emit("session_lookup_failed")
            return False
        if (
            info.get("result") not in ("success", "wait")
            or info.get("userId") != saved["userId"]
            or normalize_mac(info.get("userMac", "")) != saved["userMac"]
            or info.get("userIndex") != index
        ):
            emit("limit_identity_unconfirmed")
            return False
        if not self.same_wifi(identity):
            emit("network_changed")
            return False
        state["recoveryRetryAfter"] = self.now() + COOLDOWN_SECONDS
        self.store.save(state)  # Persist before POST, including when its response is lost.
        # Recheck after the filesystem/ACL operations as well.
        if not self.same_wifi(identity):
            emit("network_changed")
            return False
        try:
            result = self.api("logout", {"userIndex": index})
        except (requests.RequestException, ValueError, TypeError):
            emit("logout_unconfirmed_cooldown")
            return False
        if result.get("result") != "success":
            emit("logout_unconfirmed_cooldown")
            return False
        state.pop("session", None)
        self.store.save(state)
        emit("own_session_logout_confirmed")
        return True

    def run(self, check=False):
        identity = self.wifi()
        if identity is None or identity.ssid != configs.TARGET_SSID:
            emit("other_network_or_ambiguous_wifi")
            return 2 if check else 0
        result = self.probe()
        if check:
            emit(result.status)
            return 0 if result.status == "online" and self.same_wifi(identity) else 2
        if not configs.PORTAL_USERNAME or not configs.PORTAL_PASSWORD:
            emit("missing_credentials")
            return 4
        state = self.store.load()
        if result.status == "online":
            if not self.same_wifi(identity):
                emit("network_changed")
                return 1
            state.pop("loginRetryAfter", None)
            self.remember(identity, result, state)
            emit("online")
            return 0
        if result.status != "offline":
            emit("probe_unavailable")
            return 1
        if self.now() < deadline(state, "loginRetryAfter"):
            emit("login_cooldown")
            return 5
        reply = self.authenticate(identity, result.query)
        # Every explicit rejection starts a cooldown, including a terminal-limit response.
        if reply.get("result") == "fail":
            state["loginRetryAfter"] = self.now() + COOLDOWN_SECONDS
            self.store.save(state)
            limited = "limit_users_err" in str(reply.get("message", "")).lower()
            if not limited or not self.recover(identity, state):
                emit("login_rejected")
                return 5
            result = self.probe()
            if result.status == "online" and self.same_wifi(identity):
                state.pop("loginRetryAfter", None)
                self.remember(identity, result, state)
                emit("online")
                return 0
            if result.status != "offline":
                emit("recovery_probe_unavailable")
                return 1
            reply = self.authenticate(identity, result.query)
            if reply.get("result") == "fail":
                state["loginRetryAfter"] = self.now() + COOLDOWN_SECONDS
                self.store.save(state)
                emit("login_rejected")
                return 5
        if reply.get("result") != "success":
            emit("authentication_unconfirmed")
            return 1
        result = self.probe(wait_online=True)
        if result.status != "online" or not self.same_wifi(identity):
            emit("authentication_unconfirmed")
            return 1
        state.pop("loginRetryAfter", None)
        self.remember(identity, result, state)
        emit("online")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only connectivity check")
    args = parser.parse_args(argv)
    try:
        # --check avoids the mutex and all persistent state operations.
        with requests.Session() as session:
            if args.check:
                return CampusLogin(session, None).run(check=True)
            if not configs.PORTAL_USERNAME or not configs.PORTAL_PASSWORD:
                emit("missing_credentials")
                return 4
            with NamedMutex() as acquired:
                if not acquired:
                    emit("another_instance_running")
                    return 0
                return CampusLogin(session, StateStore()).run()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, requests.RequestException):
        emit("operation_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
