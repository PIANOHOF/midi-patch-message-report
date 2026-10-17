#!/usr/bin/env python3
"""Read-only inventory of MIDI 1.0 bank-select and program-change messages."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import io
import json
from pathlib import Path
import sys
from typing import Any

import mido

MAX_BYTES = 32 * 1024 * 1024
CSV_FIELDS = ["sequence", "tick", "track", "event_index", "port", "port_declared",
              "channel", "message", "value_raw", "program_display_1_based",
              "cross_track_same_tick"]


def report_midi(mid: mido.MidiFile, *, channel: int | None = None,
                port: int | None = None) -> dict[str, Any]:
    """Return file messages, never an effective bank, preset or receiver state."""
    if mid.type not in (0, 1, 2):
        raise ValueError("Only Standard MIDI File types 0, 1 and 2 are supported")
    if mid.type == 0 and len(mid.tracks) != 1:
        raise ValueError("Type 0 must contain exactly one track")
    if not mid.tracks or mid.ticks_per_beat == 0:
        raise ValueError("Missing tracks or invalid zero time division")
    if channel is not None and not 1 <= channel <= 16:
        raise ValueError("Channel must be 1..16")
    if port is not None and not 0 <= port <= 255:
        raise ValueError("Logical file port must be 0..255")

    events = []
    scanned = sysex = resets = 0
    counts: Counter[str] = Counter()
    for ti, track in enumerate(mid.tracks, start=1):
        tick = 0
        file_port, declared = 0, False
        for ei, message in enumerate(track, start=1):
            scanned += 1
            if not isinstance(message.time, int) or message.time < 0:
                raise ValueError("Track delta times must be nonnegative integer ticks")
            tick += message.time
            if message.is_meta:
                if message.type == "midi_port":
                    file_port, declared = message.port, True
                continue
            if message.type == "sysex":
                sysex += 1
            if message.type == "control_change" and message.control == 121:
                resets += 1
            if message.type == "program_change":
                kind, value = "program_change", message.program
            elif message.type == "control_change" and message.control in (0, 32):
                kind = "bank_select_msb" if message.control == 0 else "bank_select_lsb"
                value = message.value
            else:
                continue
            counts[kind] += 1
            events.append({"sequence": ti if mid.type == 2 else 1, "tick": tick,
                           "track": ti, "event_index": ei, "port": file_port,
                           "port_declared": declared, "channel": message.channel + 1,
                           "message": kind, "value_raw": value,
                           "program_display_1_based": value + 1 if kind == "program_change" else None,
                           "cross_track_same_tick": False})

    groups: dict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        groups[(event["sequence"], event["tick"], event["port"], event["channel"])].append(event)
    ties = []
    for (sequence, tick, file_port, chan), group in sorted(groups.items()):
        tracks = sorted({event["track"] for event in group})
        if len(tracks) > 1:
            ties.append({"sequence": sequence, "tick": tick, "port": file_port,
                         "channel": chan, "tracks": tracks})
            for event in group:
                event["cross_track_same_tick"] = True
    events.sort(key=lambda event: (event["sequence"], event["tick"], event["track"], event["event_index"]))
    selected = [event for event in events
                if (channel is None or event["channel"] == channel)
                and (port is None or event["port"] == port)]
    return {"schema_version": 1, "file_type": mid.type,
            "time_division_raw": mid.ticks_per_beat,
            "time_division_kind": "ppqn" if mid.ticks_per_beat > 0 else "smpte_raw",
            "sequence_mode": "independent_tracks" if mid.type == 2 else "synchronous_tracks",
            "track_count": len(mid.tracks), "messages_scanned": scanned,
            "patch_message_counts_before_filters": {kind: counts[kind] for kind in
                ("bank_select_msb", "bank_select_lsb", "program_change")},
            "filters": {"channel": channel, "port": port},
            "returned_patch_messages": len(selected), "events": selected,
            "cross_track_same_tick_groups_before_filters": ties,
            "sysex_messages_not_decoded": sysex,
            "reset_all_controllers_messages_not_interpreted": resets,
            "interpretation": "File messages only; no effective bank, preset name, audible sound, device response or hardware diagnosis is inferred. Cross-track tie sort is presentation, not proven execution order."}


def inspect_file(path: str | Path, *, channel: int | None = None,
                 port: int | None = None) -> dict[str, Any]:
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Input exceeds the 32 MiB read limit")
    if not data.startswith(b"MThd"):
        raise ValueError("Expected a Standard MIDI File beginning with MThd")
    return report_midi(mido.MidiFile(file=io.BytesIO(data)), channel=channel, port=port)


def write_csv(report: dict[str, Any], destination: Any) -> None:
    writer = csv.DictWriter(destination, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(report["events"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="A local .mid file; read only, maximum 32 MiB")
    parser.add_argument("--channel", type=int, help="Report channel 1..16 only")
    parser.add_argument("--port", type=int, help="Report logical file port 0..255 only")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args(argv)
    try:
        report = inspect_file(args.file, channel=args.channel, port=args.port)
    except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot inspect MIDI file: {exc}", file=sys.stderr)
        return 2
    if args.format == "csv":
        write_csv(report, sys.stdout)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
