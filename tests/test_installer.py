"""Exercise the installer configuration command and the packaged config loader."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def config_installer(tmp_path_factory):
    project = Path(__file__).resolve().parents[1]
    compiler = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    compiler /= "NSIS/makensis.exe"
    if not compiler.is_file():
        pytest.skip("NSIS is required for installer integration")
    installer = (project / "installer.nsi").read_text(encoding="utf-8-sig")
    config_section = installer.split(
        "    ; --- B. Create .env from template and user input ---\n", 1
    )[1].split("    ; --- C. Create Uninstaller and Registry ---", 1)[0]
    build_dir = tmp_path_factory.mktemp("installer-probe")
    probe = build_dir / "config-probe.exe"
    script = build_dir / "config-probe.nsi"
    script.write_text(
        f'''Unicode true
Name "Configuration probe"
OutFile "{probe}"
RequestExecutionLevel user
SilentInstall silent
!define ENV_TEMPLATE_NAME ".env.example"
!define ENV_CONFIG_NAME ".env"
Var USERNAME
Var PASSWORD
Var SERVICE_NAME
Function .onInit
    ReadEnvStr $INSTDIR HHU_TEST_DIRECTORY
    ReadEnvStr $USERNAME HHU_TEST_USERNAME
    ReadEnvStr $PASSWORD HHU_TEST_PASSWORD
    ReadEnvStr $SERVICE_NAME HHU_TEST_SERVICE
FunctionEnd
Section
    SetOutPath $INSTDIR
    File "{project / ".env.example"}"
{config_section}
SectionEnd
''',
        encoding="utf-8",
    )
    subprocess.run(
        [str(compiler), "/INPUTCHARSET", "UTF8", str(script)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return probe


@pytest.mark.skipif(sys.platform != "win32", reason="Windows installer integration")
@pytest.mark.parametrize(
    "password",
    [
        "ordinary-password",
        "cash$HOME-and-$(throw 'must remain data')",
        "quotes'\"and\\backslashes\\",
        "  spaces # hash ; semicolon & pipe |  ",
        "${USERNAME}-${USERPROFILE}",
        "unicode-密码-🔑",
    ],
)
def test_installer_preserves_credentials(tmp_path, password, config_installer):
    project = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "space $HOME's folder"
    expected = {
        "PORTAL_USERNAME": "synthetic'account$HOME",
        "PORTAL_PASSWORD": password,
        "SERVICE_NAME": "中国移动(CMCC NET)",
    }
    environment = os.environ.copy()
    for key in expected:
        environment.pop(key, None)
    environment.update(
        HHU_TEST_DIRECTORY=str(config_dir),
        HHU_TEST_USERNAME=expected["PORTAL_USERNAME"],
        HHU_TEST_PASSWORD=password,
        HHU_TEST_SERVICE=expected["SERVICE_NAME"],
    )
    subprocess.run(
        [str(config_installer)],
        env=environment,
        check=True,
        capture_output=True,
        timeout=30,
    )
    environment["PYTHONPATH"] = str(project / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; sys.frozen = True; sys.executable = sys.argv[1]; "
                "import configs; print(json.dumps({key: getattr(configs, key) "
                "for key in ('PORTAL_USERNAME', 'PORTAL_PASSWORD', 'SERVICE_NAME')}))"
            ),
            str(config_dir / "HohaiAutoLogin.exe"),
        ],
        env=environment,
        check=True,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert json.loads(loaded.stdout) == expected
