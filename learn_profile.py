#!/usr/bin/env python3
"""
learn_profile.py - build an APF conversion profile for a plugin from a Live set.

1. In Live, make a set containing the plugin's VST3. Use the device's Configure
   button to add the parameters your projects use (touch each knob). Save the set.
2. Run:  python learn_profile.py sample.als --out plugin_profiles.json
   (use --plugin NAME if the set contains several VST3 plugins)

APF can then convert VST2 -> VST3 for that plugin without the parameters ending
up in the wrong units (see "VST3 state and parameter conversion" in the README).
Review the result, convert a COPY of a project, listen, then set "verified": true.
"""

import argparse
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import apf


def read_project(path: str) -> ET.Element:
    raw = Path(path).read_bytes()
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass  # plain XML
    return ET.fromstring(raw.decode("utf-8"))


def decode_state(preset: ET.Element, tag: str) -> Optional[bytes]:
    elem = preset.find(tag)
    if elem is None or not (elem.text or "").strip():
        return None
    try:
        return bytes.fromhex("".join(elem.text.split()))
    except ValueError:
        return None


def _number(text: str) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _name_resembles_key(label: str, key: str) -> bool:
    """
    True if a state key looks like an abbreviation of a parameter label:
    contained in it ("Mult" in "Multiply"), or the label's capitals spell it
    ("FFM" for "FilterFM").
    """
    label_l, key_l = label.lower(), key.lower()
    initials = "".join(c for c in label if c.isupper()).lower()
    return len(key_l) >= 3 and (key_l in label_l or key_l == initials)


def learn(root: ET.Element, plugin_filter: str = "") -> List[Dict[str, Any]]:
    """
    Return one profile per distinct VST3 plugin found in the project.
    """
    profiles: Dict[str, Dict[str, Any]] = {}
    notes: Dict[str, List[str]] = {}

    for device in root.iter("PluginDevice"):
        info = device.find("PluginDesc/Vst3PluginInfo")
        name_elem = info.find("Name") if info is not None else None
        if name_elem is None:
            continue
        name = name_elem.get("Value", "")
        if plugin_filter and plugin_filter.lower() not in name.lower():
            continue

        preset = info.find("Preset/Vst3Preset")
        sections: Dict[str, Dict[str, str]] = {}
        controller_used = False
        if preset is not None:
            controller_used = decode_state(preset, "ControllerState") is not None
            state = decode_state(preset, "ProcessorState")
            if state is not None:
                text = state.decode("latin-1")
                if "#cm=" in text:
                    sections = apf.parse_preset_text(text)

        profile = profiles.setdefault(
            name,
            {
                "name": name,
                "match": [name.lower()],
                "verified": False,
                "fill_controller_state": controller_used,
                "blank_unmapped": False,
                "parameters": {},
            },
        )
        notes.setdefault(name, [])
        if sections:
            profile["state_format"] = "cm-sections"

        for slot in device.findall("ParameterList/PluginFloatParameter"):
            pname = slot.find("ParameterName")
            pid = slot.find("ParameterId")
            if pname is None or pid is None:
                continue
            label, ident = pname.get("Value", ""), pid.get("Value", "")
            if not label or ident == "-1":
                continue
            low = _number(slot.find("LastUserRange/First").get("Value"))
            high = _number(slot.find("LastUserRange/Last").get("Value"))
            if low is None or high is None:
                notes[name].append(f"{label} (id {ident}): no real-unit range saved; skipped")
                continue

            spec: Dict[str, Any] = {"name": label, "min": low, "max": high}
            manual = _number(slot.find("ParameterValue/Manual").get("Value"))
            if sections and manual is not None:
                hits = [
                    (sec, key)
                    for sec, items in sections.items()
                    for key, val in items.items()
                    if _number(val) is not None and abs(_number(val) - manual) < 1e-6
                ]
                chosen = None
                if len(hits) == 1:
                    chosen = hits[0]
                elif hits:
                    # several entries hold this value: accept one only if exactly one
                    # key resembles the parameter's name
                    similar = [h for h in hits if _name_resembles_key(label, h[1])]
                    if len(similar) == 1:
                        chosen = similar[0]
                        notes[name].append(
                            f"{label} (id {ident}): {len(hits)} entries hold {manual}; chose "
                            f"{chosen[0]}.{chosen[1]} because its name resembles the parameter. "
                            "Check it."
                        )
                if chosen:
                    spec["section"], spec["key"] = chosen
                elif hits:
                    notes[name].append(
                        f"{label} (id {ident}): value {manual} matches {len(hits)} state "
                        "entries; change the knob to an unusual value and learn again to locate it"
                    )
            profile["parameters"][ident] = spec

    for name, profile in profiles.items():
        profile["_notes"] = notes[name]
    return list(profiles.values())


def merge(existing: Dict[str, Any], learned: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge learned profiles into an existing profiles file; a learned parameter
    replaces the stored one with the same id, everything else is kept.
    """
    existing.setdefault("profiles", [])
    by_name = {p.get("name", "").lower(): p for p in existing["profiles"]}
    for new in learned:
        clean = {k: v for k, v in new.items() if k != "_notes"}
        old = by_name.get(new["name"].lower())
        if old is None:
            existing["profiles"].append(clean)
            continue
        old.setdefault("parameters", {}).update(clean["parameters"])
        for key in ("fill_controller_state", "state_format"):
            if key in clean:
                old[key] = clean[key]
    return existing


def main() -> int:
    parser = argparse.ArgumentParser(description="Learn an APF plugin profile from a Live set")
    parser.add_argument("project", help="Live set saved with the plugin's VST3 and Configure parameters")
    parser.add_argument("--plugin", default="", help="only plugins whose name contains this")
    parser.add_argument("--out", help="profiles file to create or update (default: print)")
    args = parser.parse_args()

    learned = learn(read_project(args.project), args.plugin)
    if not learned:
        print("No VST3 plugin found in that project.", file=sys.stderr)
        return 1

    for profile in learned:
        print(f"{profile['name']}: {len(profile['parameters'])} parameter(s), "
              f"fill_controller_state={profile['fill_controller_state']}, "
              f"state_format={profile.get('state_format', 'none')}")
        for note in profile["_notes"]:
            print(f"  note: {note}")

    if not args.out:
        print(json.dumps({"profiles": [{k: v for k, v in p.items() if k != "_notes"} for p in learned]}, indent=2))
        return 0

    out = Path(args.out)
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    out.write_text(json.dumps(merge(existing, learned), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
