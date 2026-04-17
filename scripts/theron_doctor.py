from __future__ import annotations

import json
import os
import subprocess
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _masked_present(value: str) -> str:
    return "<set>" if value else "<missing>"


def _probe(url: str) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return True, json.dumps(payload, sort_keys=True)
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        return False, str(exc)


def main() -> int:
    theron_backend = _get("THERON_BACKEND", "theron_gateway")
    theron_model = _get("THERON_MODEL", "theron/latest")
    theron_base_url = _get("THERON_BASE_URL", "http://127.0.0.1:8010/v1")
    theron_health_url = _get("THERON_HEALTH_URL", theron_base_url.removesuffix("/v1") + "/health")
    theron_openclaw_bin = _get("THERON_OPENCLAW_BIN", os.path.expanduser("~/.local/bin/openclaw"))
    theron_openclaw_agent_id = _get("THERON_OPENCLAW_AGENT_ID", "main")
    gateway_mode = _get("THERON_GATEWAY_MODE", "mock")
    bot_name = _get("THERON_BOT_NAME", "Theron")

    api_id = _get("THERON_TELEGRAM_API_ID")
    api_hash = _get("THERON_TELEGRAM_API_HASH")
    session_string = _get("THERON_TELEGRAM_SESSION_STRING")
    session_file = _get("THERON_TELEGRAM_SESSION_FILE")

    print("Theron Doctor")
    print(f"backend={theron_backend}")
    print(f"model={theron_model}")
    print(f"base_url={theron_base_url}")
    print(f"health_url={theron_health_url}")
    print(f"openclaw_bin={theron_openclaw_bin}")
    print(f"openclaw_agent_id={theron_openclaw_agent_id}")
    print(f"gateway_mode={gateway_mode}")
    print(f"bot_name={bot_name}")
    print(f"telegram_api_id={_masked_present(api_id)}")
    print(f"telegram_api_hash={_masked_present(api_hash)}")
    print(f"telegram_session_string={_masked_present(session_string)}")
    print(f"telegram_session_file={session_file or '<missing>'}")
    print()

    if theron_backend == "openclaw_local":
        if not os.path.exists(theron_openclaw_bin):
            print("local_agent=down openclaw binary missing")
            print()
            print("next_step=install_or_point_to_openclaw")
            return 1
        result = subprocess.run(
            [theron_openclaw_bin, "agents", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            text = result.stdout
            if theron_openclaw_agent_id in text:
                print(f"local_agent=ok {theron_openclaw_agent_id}")
                print()
                print("next_step=ready")
                print("Theron local OpenClaw transport looks ready for in-lab generation.")
                return 0
            print("local_agent=down agent id not found")
            print()
            print("next_step=configure_agent_identity")
            return 1
        detail = result.stderr.strip()
        print(f"local_agent=down {detail or 'agents list failed'}")
        print()
        print("next_step=fix_local_openclaw")
        return 1

    reachable, detail = _probe(theron_health_url)
    if reachable:
        print(f"gateway_health=ok {detail}")
    else:
        print(f"gateway_health=down {detail}")

    if reachable:
        try:
            payload = json.loads(detail)
        except Exception:
            payload = {}
        if "mode" not in payload or "bot_name" not in payload:
            print()
            print("next_step=port_conflict_or_wrong_service")
            print("The health endpoint answered, but it does not look like the Theron gateway.")
            print("Set THERON_BASE_URL / THERON_HEALTH_URL to the dedicated Theron gateway port and start scripts/theron_gateway.py there.")
            return 1

    missing = []
    if gateway_mode == "telegram":
        if not api_id:
            missing.append("THERON_TELEGRAM_API_ID")
        if not api_hash:
            missing.append("THERON_TELEGRAM_API_HASH")
        if not (session_string or session_file):
            missing.append("THERON_TELEGRAM_SESSION_STRING or THERON_TELEGRAM_SESSION_FILE")

    if missing:
        print()
        print("next_step=missing_credentials")
        for item in missing:
            print(f"- {item}")
        return 1

    if not reachable:
        print()
        print("next_step=start_gateway")
        print("Run:")
        print("  ./.venv/bin/python scripts/theron_gateway.py")
        return 1

    print()
    print("next_step=ready")
    print("Theron transport looks ready for in-lab generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
