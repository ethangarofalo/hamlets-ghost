from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database as db  # noqa: E402


OPENCLAW_BIN = os.path.expanduser(os.getenv("OPENCLAW_BIN", "~/.local/bin/openclaw"))
HUMAN_REVIEW_CHANNEL = os.getenv("HUMAN_REVIEW_CHANNEL", "telegram")
HUMAN_REVIEW_TARGET = os.getenv("HUMAN_REVIEW_TARGET", "")
MESSAGE_LIMIT = 3500


def _judge_line(summary: dict) -> str:
    winner = summary.get("winner_experiment_id")
    margin = summary.get("margin")
    if winner is None:
        return f"- {summary['judge'].title()}: no clear winner"
    return f"- {summary['judge'].title()}: prefers #{winner} (Δ {margin:.2f})"


def _chunk_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        addition = len(line) + 1
        if current and current_len + addition > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = addition
        else:
            current.append(line)
            current_len += addition
    if current:
        chunks.append("\n".join(current))
    return chunks


def _format_packet(packet: dict) -> list[str]:
    judge_lines = "\n".join(_judge_line(row) for row in packet.get("judge_preferences", []))
    summary = (
        "APOLLO REVIEW REQUEST\n\n"
        f"Packet: {packet['packet_id']}\n"
        f"Lane: {packet.get('lane') or '--'}\n"
        f"Family: {packet.get('family') or '--'}\n"
        f"Condition: {packet.get('condition') or '--'}\n\n"
        "Noticeable disagreement among judges:\n"
        f"{judge_lines}\n\n"
        "Question: Which was better and why?\n\n"
        "Reply in this format:\n"
        f"PACKET: {packet['packet_id']}\n"
        "BETTER: <experiment_id>\n"
        "WHY: <your reasoning>"
    )
    messages = [summary]
    for member in packet.get("members", []):
        body = (
            f"OPTION #{member['id']} · {member.get('packet_role_id') or member.get('role_id') or 'generator'}\n"
            f"Status: {member.get('status')} / {member.get('promotion_status')}\n"
            f"Muse: {member.get('scores', {}).get('muse', '--')} · "
            f"Athena: {member.get('scores', {}).get('athena', '--')} · "
            f"Apollo: {member.get('scores', {}).get('apollo', '--')}\n\n"
            f"{member.get('artifact') or '(no artifact)'}"
        )
        messages.extend(_chunk_text(body))
    return messages


def _send_message(*, channel: str, target: str, message: str, dry_run: bool) -> dict:
    cmd = [
        OPENCLAW_BIN,
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    raw = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(raw or f"openclaw message send failed with code {result.returncode}")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


async def _load_packet(packet_id: str | None) -> dict:
    if packet_id:
        packet = await db.get_disagreement_packet(packet_id)
        if not packet:
            raise SystemExit(f"Packet '{packet_id}' was not found or is not in the disagreement queue.")
        return packet
    rows = await db.list_disagreement_packets(limit=1, unresolved_only=True)
    if not rows:
        raise SystemExit("No unresolved disagreement packets found.")
    packet = await db.get_disagreement_packet(rows[0]["packet_id"])
    if not packet:
        raise SystemExit("Could not load the next disagreement packet.")
    return packet


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send the next disagreement packet to a human review channel.")
    parser.add_argument("--packet-id", help="Specific packet_id to send. Defaults to the next unresolved disagreement.")
    parser.add_argument("--channel", default=HUMAN_REVIEW_CHANNEL, help="Messaging channel, for example telegram.")
    parser.add_argument("--target", default=HUMAN_REVIEW_TARGET, help="OpenClaw messaging target, for example your Telegram username.")
    parser.add_argument("--dry-run", action="store_true", help="Print/send payload in dry-run mode without delivering.")
    args = parser.parse_args()

    if not args.target:
        raise SystemExit("Set HUMAN_REVIEW_TARGET in .env or pass --target.")

    packet = await _load_packet(args.packet_id)
    outputs = []
    for message in _format_packet(packet):
        outputs.append(_send_message(channel=args.channel, target=args.target, message=message, dry_run=args.dry_run))
    print(json.dumps({
        "packet_id": packet["packet_id"],
        "channel": args.channel,
        "target": args.target,
        "messages_sent": len(outputs),
        "results": outputs,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
