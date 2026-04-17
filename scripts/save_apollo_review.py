from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database as db  # noqa: E402


PACKET_RE = re.compile(r"PACKET:\s*(\S+)", re.I)
BETTER_RE = re.compile(r"BETTER:\s*(\d+)", re.I)
WHY_RE = re.compile(r"WHY:\s*(.+)", re.I | re.S)


def _parse_reply(text: str) -> tuple[str, int, str]:
    packet_match = PACKET_RE.search(text)
    better_match = BETTER_RE.search(text)
    why_match = WHY_RE.search(text)
    if not packet_match or not better_match or not why_match:
        raise ValueError("Reply must include PACKET:, BETTER:, and WHY: fields.")
    return packet_match.group(1).strip(), int(better_match.group(1)), why_match.group(1).strip()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Save a human disagreement review back into Creativity Lab.")
    parser.add_argument("--packet-id", help="Packet id, if not parsing from --reply-text.")
    parser.add_argument("--preferred-experiment-id", type=int, help="Chosen experiment id, if not parsing from --reply-text.")
    parser.add_argument("--why", help="Rationale, if not parsing from --reply-text.")
    parser.add_argument("--reply-text", help="Raw reply text using PACKET/BETTER/WHY format.")
    parser.add_argument("--reviewer", default="human_operator", help="Reviewer label to store.")
    parser.add_argument("--review-channel", default="telegram", help="Review channel label.")
    parser.add_argument("--outbound-message-id", default=None)
    parser.add_argument("--inbound-message-id", default=None)
    args = parser.parse_args()

    if args.reply_text:
        packet_id, preferred_experiment_id, why = _parse_reply(args.reply_text)
    else:
        if not args.packet_id or args.preferred_experiment_id is None or not args.why:
            raise SystemExit("Provide either --reply-text or all of --packet-id, --preferred-experiment-id, and --why.")
        packet_id, preferred_experiment_id, why = args.packet_id, args.preferred_experiment_id, args.why

    packet = await db.get_disagreement_packet(packet_id)
    if not packet:
        raise SystemExit(f"Packet '{packet_id}' was not found.")
    valid_ids = {member.get("id") for member in packet.get("members", [])}
    if preferred_experiment_id not in valid_ids:
        raise SystemExit(f"Experiment #{preferred_experiment_id} is not a member of packet '{packet_id}'.")

    review = await db.save_comparison_review(
        packet_id,
        preferred_experiment_id=preferred_experiment_id,
        rationale=why,
        reviewer=args.reviewer,
        review_channel=args.review_channel,
        outbound_message_id=args.outbound_message_id,
        inbound_message_id=args.inbound_message_id,
        metadata={"source": "apollo_review_loop"},
    )
    print(json.dumps(review, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
