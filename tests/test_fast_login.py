"""Offline portal and Windows process tests. All identities below are synthetic."""

import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import requests

import configs
import fast_login as login

WIFI = login.WifiIdentity("Wi-Fi", "Hohai University", "001122aabbcc")
OTHER_WIFI = login.WifiIdentity("Wi-Fi", "Other network", "001122aabbcc")
INDEX = "synthetic-old-session"
SUCCESS_URL = "http://eportal.hhu.edu.cn/eportal/success.jsp?userIndex=synthetic-new-session"
OFFLINE_HTML = "top.self.location.href='http://eportal.hhu.edu.cn/eportal/index.jsp?ticket=test';"
LIMIT = {"result": "fail", "message": "limit_users_Err"}


class MemoryStore:
    def __init__(self, state=None):
        self.state = copy.deepcopy(state or {})
        self.writes = []

    def load(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.state = copy.deepcopy(state)
        self.writes.append(copy.deepcopy(state))


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setattr(configs, "PORTAL_USERNAME", "synthetic-account")
    monkeypatch.setattr(configs, "PORTAL_PASSWORD", "synthetic-password")
    monkeypatch.setattr(configs, "SERVICE_NAME", "synthetic-service")
    monkeypatch.setattr(configs, "TARGET_SSID", WIFI.ssid)


@pytest.fixture
def store():
    return MemoryStore(
        {
            "session": {
                "userId": "synthetic-account",
                "userMac": WIFI.mac,
                "userIndex": INDEX,
            }
        }
    )


def client(store, **kwargs):
    return login.CampusLogin(
        requests.Session(),
        store,
        wifi=lambda: WIFI,
        sleep=lambda _: None,
        now=lambda: 1000,
        **kwargs,
    )


def offline(mock, responses=None):
    mock.get(login.CHECK_URL, responses or [{"text": OFFLINE_HTML}])
    mock.get(SUCCESS_URL, text="")


def online_response():
    return {"status_code": 302, "headers": {"Location": SUCCESS_URL}}


def api(mock, method, *responses, **kwargs):
    return mock.post(login.API_URL + method, *responses, **kwargs)


def self_info():
    return {
        "result": "wait",
        "userId": "synthetic-account",
        "userMac": "00:11:22:AA:BB:CC",
        "userIndex": INDEX,
    }


def test_payload_keeps_original_double_encoding_and_fields():
    payload = login.login_payload("student+id", "pass&字", "校园", "ticket=a&b=2")
    assert "userId=student%252Bid" in payload
    assert "password=pass%2526%25E5%25AD%2597" in payload
    assert "queryString=ticket%253Da%2526b%253D2" in payload
    assert payload.endswith("operatorPwd=&operatorUserId=&validcode=&passwordEncrypt=false")


def test_netsh_english_chinese_and_interface_blocks(monkeypatch):
    text = """
    Name : Wi-Fi
    Physical address : 00:11:22:AA:BB:CC
    SSID : Hohai University
    BSSID : ff:ff:ff:ff:ff:ff
    名称 : Wi-Fi 2
    物理地址 : 00-11-22-DD-EE-FF
    SSID : Other network
    """
    interfaces = login.parse_wifi_interfaces(text)
    assert interfaces == [WIFI, login.WifiIdentity("Wi-Fi 2", "Other network", "001122ddeeff")]
    monkeypatch.setattr(
        login.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=text.encode("utf-8")),
    )
    monkeypatch.setattr(login.ctypes.windll.kernel32, "GetOEMCP", lambda: 65001)
    assert login.current_wifi() is None


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.invalid/success.jsp",
        "http://eportal.hhu.edu.cn.evil.invalid/eportal/success.jsp",
        "http://eportal.hhu.edu.cn:8080/eportal/success.jsp",
        "https://eportal.hhu.edu.cn/eportal/success.jsp",
        "http://eportal.hhu.edu.cn/not-success.jsp",
        "http://user@eportal.hhu.edu.cn/eportal/success.jsp",
    ],
)
def test_online_requires_exact_portal_origin_and_path(url):
    response = requests.Response()
    response.url = url
    response._content = b"success"
    assert login.decode_probe(response).status == "unavailable"


def test_json_whitespace_and_authentication_confirmation(requests_mock, store):
    offline(requests_mock, [{"text": OFFLINE_HTML}, online_response()])
    api(requests_mock, "login", text=' { "result" : "success" } ')
    runner = client(store)
    assert runner.session.trust_env is False
    assert runner.run() == 0
    assert store.state["session"]["userIndex"] == "synthetic-new-session"
    assert not any("password" in json.dumps(state) for state in store.writes)


def test_success_json_without_online_probe_is_failure(requests_mock, store):
    offline(requests_mock)
    api(requests_mock, "login", json={"result": "success"})
    assert client(store).run() == 1
    assert not store.writes


def test_accepted_login_waits_for_portal_visibility_without_reposting(requests_mock, store):
    offline(requests_mock, [{"text": OFFLINE_HTML}, {"text": OFFLINE_HTML}, online_response()])
    request = api(requests_mock, "login", json={"result": "success"})
    assert client(store).run() == 0
    assert request.call_count == 1


def test_plain_rejection_cools_down_without_session_lookup(requests_mock, store):
    offline(requests_mock)
    request = api(requests_mock, "login", json={"result": "fail", "message": "invalid_password"})
    runner = client(store)
    assert runner.run() == 5
    assert store.state["loginRetryAfter"] == 1300
    assert runner.run() == 5
    assert request.call_count == 1
    assert all(
        "logout" not in req.url and "getOnlineUserInfo" not in req.url
        for req in requests_mock.request_history
    )


@pytest.mark.parametrize("lookup_result", ["success", "wait"])
def test_limit_recovers_only_verified_own_session(requests_mock, store, lookup_result):
    offline(requests_mock, [{"text": OFFLINE_HTML}, {"text": OFFLINE_HTML}, online_response()])
    api(requests_mock, "login", [{"json": LIMIT}, {"json": {"result": "success"}}])
    info = self_info()
    info["result"] = lookup_result
    api(requests_mock, "getOnlineUserInfo", json=info)
    logout = api(requests_mock, "logout", json={"result": "success"})
    assert client(store).run() == 0
    assert logout.last_request.text == "userIndex=synthetic-old-session"
    assert store.state["recoveryRetryAfter"] == 1300
    assert "loginRetryAfter" not in store.state
    assert store.state["session"]["userIndex"] == "synthetic-new-session"


@pytest.mark.parametrize(
    "field,value",
    [
        ("userId", "another-account"),
        ("userMac", "00:11:22:DD:EE:FF"),
        ("userIndex", "another-session"),
        ("result", "fail"),
        ("userMac", "invalid"),
    ],
)
def test_portal_identity_mismatch_never_logs_out(requests_mock, store, field, value):
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    info = self_info()
    info[field] = value
    api(requests_mock, "getOnlineUserInfo", json=info)
    assert client(store).run() == 5
    assert all("method=logout" not in req.url for req in requests_mock.request_history)


@pytest.mark.parametrize(
    "saved",
    [
        None,
        {},
        {"userId": "another-account", "userMac": WIFI.mac, "userIndex": INDEX},
        {"userId": "synthetic-account", "userMac": "001122ddeeff", "userIndex": INDEX},
    ],
)
def test_missing_or_foreign_saved_session_stops_before_lookup(requests_mock, saved):
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    assert client(MemoryStore({"session": saved})).run() == 5
    assert all(
        "getOnlineUserInfo" not in req.url and "method=logout" not in req.url
        for req in requests_mock.request_history
    )


def test_logout_lost_response_keeps_pre_submission_cooldown(requests_mock, store):
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    api(requests_mock, "getOnlineUserInfo", json=self_info())

    def lose_response(request, context):
        assert store.state["recoveryRetryAfter"] == 1300
        raise requests.Timeout("synthetic response lost")

    logout = api(requests_mock, "logout", text=lose_response)
    runner = client(store)
    assert runner.run() == 5
    assert runner.run() == 5
    assert logout.call_count == 1
    assert store.state["session"]["userIndex"] == INDEX


def test_existing_recovery_cooldown_survives_a_fresh_limit(requests_mock, store):
    store.state["recoveryRetryAfter"] = 1299
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    assert client(store).run() == 5
    assert all(
        "method=logout" not in req.url and "getOnlineUserInfo" not in req.url
        for req in requests_mock.request_history
    )


def test_switching_wifi_before_credentials_sends_no_post(requests_mock, store):
    offline(requests_mock)
    runner = client(store)
    identities = iter([WIFI, OTHER_WIFI])
    runner.wifi = lambda: next(identities)
    assert runner.run() == 1
    assert all(req.method == "GET" for req in requests_mock.request_history)


@pytest.mark.parametrize("switch_at", ["lookup", "persist"])
def test_switching_wifi_during_recovery_never_logs_out(requests_mock, store, switch_at):
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    runner = client(store)

    def lookup(request, context):
        if switch_at == "lookup":
            runner.wifi = lambda: OTHER_WIFI
        return self_info()

    api(requests_mock, "getOnlineUserInfo", json=lookup)
    original_save = store.save

    def save(state):
        original_save(state)
        if "recoveryRetryAfter" in state and switch_at == "persist":
            runner.wifi = lambda: OTHER_WIFI

    store.save = save
    assert runner.run() == 5
    assert all("method=logout" not in req.url for req in requests_mock.request_history)


def test_probe_transient_errors_are_bounded(requests_mock, store):
    requests_mock.get(
        login.CHECK_URL,
        [{"exc": requests.ConnectionError}, {"exc": requests.Timeout}, {"text": OFFLINE_HTML}],
    )
    runner = client(store)
    pauses = []
    runner.sleep = pauses.append
    assert runner.run(check=True) == 2
    assert pauses == [1, 2]
    assert requests_mock.call_count == 3
    assert not store.writes


def test_probe_permanent_failure_stops_after_three_attempts(requests_mock, store):
    requests_mock.get(login.CHECK_URL, exc=requests.ConnectionError)
    assert client(store).run() == 1
    assert requests_mock.call_count == 3


def test_login_transient_error_checks_before_retry(requests_mock, store):
    offline(requests_mock, [{"text": OFFLINE_HTML}] * 4 + [online_response()])
    request = api(
        requests_mock, "login", [{"exc": requests.Timeout}, {"json": {"result": "success"}}]
    )
    assert client(store).run() == 0
    assert request.call_count == 2


def test_lost_login_response_already_online_avoids_repeated_login(requests_mock, store):
    offline(requests_mock, [{"text": OFFLINE_HTML}, online_response()])
    request = api(requests_mock, "login", exc=requests.Timeout)
    assert client(store).run() == 0
    assert request.call_count == 1


def test_permanent_post_failure_is_bounded(requests_mock, store):
    offline(requests_mock)
    request = api(requests_mock, "login", exc=requests.ConnectionError)
    assert client(store).run() == 1
    assert request.call_count == 3


def test_check_ignores_credentials_mutex_and_state(requests_mock, monkeypatch):
    offline(requests_mock, [online_response()])
    monkeypatch.setattr(configs, "PORTAL_USERNAME", "")
    monkeypatch.setattr(configs, "PORTAL_PASSWORD", "")
    monkeypatch.setattr(login, "current_wifi", lambda: WIFI)

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only check touched mutable state or mutex")

    monkeypatch.setattr(login, "StateStore", forbidden)
    monkeypatch.setattr(login, "NamedMutex", forbidden)
    assert login.main(["--check"]) == 0
    assert all(req.method == "GET" for req in requests_mock.request_history)


def test_missing_credentials_exit_before_network(requests_mock, monkeypatch):
    monkeypatch.setattr(configs, "PORTAL_PASSWORD", "")
    assert login.main([]) == 4
    assert requests_mock.call_count == 0


def test_state_is_atomic_json_and_only_saved_in_local_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = login.StateStore()
    assert state.load() == {}
    state.save({"session": {"userId": "synthetic-account"}, "recoveryRetryAfter": 1300})
    assert state.load()["recoveryRetryAfter"] == 1300
    assert state.path == tmp_path / "HohaiAutoLogin" / "session.json"
    assert [file.name for file in state.path.parent.iterdir()] == ["session.json"]
    state.path.write_text("invalid json", encoding="utf-8")
    assert state.load() == {}


def test_state_save_failure_prevents_logout(requests_mock, store):
    offline(requests_mock)
    api(requests_mock, "login", json=LIMIT)
    api(requests_mock, "getOnlineUserInfo", json=self_info())

    def save(state):
        if "recoveryRetryAfter" in state:
            raise OSError("synthetic state failure")

    store.save = save
    with pytest.raises(OSError):
        client(store).run()
    assert all("method=logout" not in req.url for req in requests_mock.request_history)


def test_real_named_mutex_excludes_a_second_windows_process():
    name = "Global\\HHU-offline-test-" + uuid.uuid4().hex
    code = (
        "import sys; from fast_login import NamedMutex; "
        f"mutex=NamedMutex({name!r}); "
        "acquired=mutex.__enter__(); mutex.__exit__(); sys.exit(1 if acquired else 0)"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(login.__file__).parent)
    with login.NamedMutex(name) as acquired:
        assert acquired
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            env=environment,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0
    with login.NamedMutex(name) as acquired:
        assert acquired


def test_main_reports_busy_and_sanitizes_unexpected_operational_errors(monkeypatch, capsys):
    class Busy:
        def __enter__(self):
            return False

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(login, "NamedMutex", Busy)
    assert login.main([]) == 0

    def broken():
        raise OSError("secret-response-must-stay-private")

    monkeypatch.setattr(login, "NamedMutex", broken)
    assert login.main([]) == 1
    output = capsys.readouterr().out
    assert "operation_failed" in output
    assert "secret-response" not in output


@pytest.mark.parametrize("port", ["", ":80", ":8080"])
def test_index_page_accepts_known_portal_page_ports(port):
    response = requests.Response()
    response.url = f"http://10.96.0.155{port}/eportal/index.jsp?ticket=test"
    response._content = b""
    assert login.decode_probe(response).status == "offline"


@pytest.mark.parametrize(
    "authority", ["user@10.96.0.155:8080", "10.96.0.155:9999", "10.96.0.155.evil.invalid:8080"]
)
def test_index_page_rejects_userinfo_unknown_ports_and_hosts(authority):
    response = requests.Response()
    response.url = f"http://{authority}/eportal/index.jsp?ticket=test"
    response._content = b""
    assert login.decode_probe(response).status == "unavailable"


def test_recovery_probe_already_online_remembers_without_extra_login(requests_mock, store):
    offline(requests_mock, [{"text": OFFLINE_HTML}, online_response()])
    request = api(requests_mock, "login", json=LIMIT)
    api(requests_mock, "getOnlineUserInfo", json=self_info())
    api(requests_mock, "logout", json={"result": "success"})
    assert client(store).run() == 0
    assert request.call_count == 1
    assert store.state["session"]["userIndex"] == "synthetic-new-session"
    assert "loginRetryAfter" not in store.state
    assert store.state["recoveryRetryAfter"] == 1300


def test_unchanged_state_skips_acl_and_disk_write(tmp_path, monkeypatch):
    state = login.StateStore(tmp_path / "private" / "session.json")
    value = {"session": {"userId": "synthetic-account"}}
    state.save(value)
    timestamp = state.path.stat().st_mtime_ns

    def forbidden(*args, **kwargs):
        pytest.fail("Unchanged state repeated ACL setup")

    monkeypatch.setattr(login, "secure_directory", forbidden)
    state.save(copy.deepcopy(value))
    assert state.path.stat().st_mtime_ns == timestamp


def test_config_source_and_frozen_paths(monkeypatch):
    assert Path(configs.get_executable_path()) == Path(__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\SyntheticApp\HohaiAutoLogin.exe")
    assert Path(configs.get_executable_path()) == Path(r"C:\SyntheticApp")


def test_normal_online_clears_login_cooldown_and_keeps_recovery_cooldown(requests_mock, store):
    offline(requests_mock, [online_response()])
    store.state["loginRetryAfter"] = 1300
    store.state["recoveryRetryAfter"] = 1350
    assert client(store).run() == 0
    assert "loginRetryAfter" not in store.state
    assert store.state["recoveryRetryAfter"] == 1350


@pytest.mark.parametrize(
    "url,status",
    [
        ("http://eportal.hhu.edu.cn/eportal/./success.jsp?userIndex=synthetic-session", "online"),
        ("http://10.96.0.155:8080/eportal/./index.jsp?ticket=synthetic", "offline"),
        (
            "http://eportal.hhu.edu.cn/eportal/success.jsp/?userIndex=synthetic-session",
            "unavailable",
        ),
    ],
)
def test_portal_dot_segments_keep_exact_canonical_endpoint(url, status):
    response = requests.Response()
    response.url = url
    response._content = b""
    assert login.decode_probe(response).status == status


def test_rejection_after_recovery_refreshes_full_cooldown(requests_mock, store):
    offline(requests_mock)
    clock = [1000]

    def reject_again(request, context):
        clock[0] = 1040
        return {"result": "fail", "message": "synthetic-rejection"}

    api(requests_mock, "login", [{"json": LIMIT}, {"json": reject_again}])
    api(requests_mock, "getOnlineUserInfo", json=self_info())
    logout = api(requests_mock, "logout", json={"result": "success"})
    runner = client(store)
    runner.now = lambda: clock[0]
    assert runner.run() == 5
    assert store.state["loginRetryAfter"] == 1340
    assert store.state["recoveryRetryAfter"] == 1300
    assert logout.call_count == 1


@pytest.mark.parametrize("port", ["", ":80"])
def test_success_page_accepts_implicit_and_explicit_http_port(port):
    response = requests.Response()
    response.url = (
        f"http://eportal.hhu.edu.cn{port}/eportal/./success.jsp?userIndex=synthetic-session"
    )
    response._content = b""
    assert login.decode_probe(response).status == "online"
