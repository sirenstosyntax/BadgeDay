"""The deploy script must not grow a JSON-key path or touch the other tills."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "play-verify" / "deploy.sh"
SERVER = Path(__file__).resolve().parent.parent / "play_verify" / "play_api.py"


def test_the_deploy_script_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_the_deploy_script_refuses_a_json_key_and_stays_on_badgeday() -> None:
    text = SCRIPT.read_text()
    assert "PLAY_SERVICE_ACCOUNT_JSON" in text
    assert "keys create" not in text
    assert 'SERVICE="badgeday-play-verify"' in text
    assert "gcloud run deploy drillground" not in text
    assert "com.badgeday.app" in text
    assert "sirens-to-syntax-play" in text
    assert "CONFIRM_PLAY_VERIFY_DEPLOY" in text
    assert "az containerapp" not in text
    assert "sk_" not in text
    assert "stripe.com" not in text.lower()
    assert ":consume" not in text


def test_the_play_client_has_no_consume_call() -> None:
    text = SERVER.read_text()
    assert "consume(" not in text
    assert ":consume" not in text
