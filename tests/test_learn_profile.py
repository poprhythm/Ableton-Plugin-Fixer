"""
Tests for learn_profile.py. Run from the repository root:  python -m unittest discover tests
"""

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import learn_profile  # noqa: E402

STATE = b"#pgm=Init\n#cm=Filter\nCutoff=47.50\nReso=0.00\n#cm=Clock\nBase=1\nMult=0.00\n"


def sample_project(controller=True, state=STATE, label="Mystery", manual="0"):
    ctrl = f"<ControllerState>{state.hex()}</ControllerState>" if controller else "<ControllerState />"

    def slot(name, pid, manual, low, high):
        return (
            f'<PluginFloatParameter Id="0"><ParameterName Value="{name}" /><ParameterId Value="{pid}" />'
            f'<ParameterValue><Manual Value="{manual}" /></ParameterValue>'
            f'<LastUserRange><First Value="{low}" /><Last Value="{high}" /></LastUserRange>'
            "</PluginFloatParameter>"
        )

    xml = (
        "<Ableton><PluginDevice><PluginDesc><Vst3PluginInfo><Name Value=\"Example\" />"
        f"<Preset><Vst3Preset><ProcessorState>{state.hex()}</ProcessorState>{ctrl}</Vst3Preset></Preset>"
        "</Vst3PluginInfo></PluginDesc><ParameterList>"
        + slot("Cutoff", "10", "47.5", "30", "150")
        + slot(label, "11", manual, "0", "100")  # default 0 matches two state entries: ambiguous
        + slot("Unmapped", "-1", "0.1234567687", "Invalid", "Invalid")
        + slot("", "12", "0", "0", "1")
        + "</ParameterList></PluginDevice></Ableton>"
    )
    return xml.encode("utf-8")


class LearnTests(unittest.TestCase):
    def learn(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.als"
            path.write_bytes(gzip.compress(sample_project(**kw)))
            return learn_profile.learn(learn_profile.read_project(str(path)))

    def test_parameters_ranges_and_state_location_are_learned(self):
        (profile,) = self.learn()
        self.assertEqual(profile["name"], "Example")
        self.assertEqual(profile["match"], ["example"])
        self.assertTrue(profile["fill_controller_state"])
        self.assertEqual(profile["state_format"], "cm-sections")
        self.assertEqual(
            profile["parameters"]["10"],
            {"name": "Cutoff", "min": 30.0, "max": 150.0, "section": "Filter", "key": "Cutoff"},
        )

    def test_ambiguous_value_gets_range_but_no_state_location(self):
        (profile,) = self.learn()
        self.assertNotIn("section", profile["parameters"]["11"])
        self.assertTrue(any("Mystery" in n for n in profile["_notes"]))

    def test_ambiguous_value_is_resolved_by_key_resembling_the_name(self):
        # three entries hold 1, but only "Base" resembles the label "TimeBase"
        state = b"#cm=Filter\nCutoff=47.50\nOther=1\nAlso=1\n#cm=Clock\nBase=1\n"
        (profile,) = self.learn(state=state, label="TimeBase", manual="1")
        spec = profile["parameters"]["11"]
        self.assertEqual((spec["section"], spec["key"]), ("Clock", "Base"))
        self.assertTrue(any("chose Clock.Base" in n for n in profile["_notes"]))

    def test_ambiguous_value_with_no_resembling_key_is_left_unlocated(self):
        state = b"#cm=Filter\nCutoff=47.50\nOther=1\nAlso=1\n"
        (profile,) = self.learn(state=state, label="TimeBase", manual="1")
        self.assertNotIn("section", profile["parameters"]["11"])

    def test_name_resemblance_rules(self):
        resembles = learn_profile._name_resembles_key
        self.assertTrue(resembles("Multiply", "Mult"))
        self.assertTrue(resembles("FilterFM", "FFM"))
        self.assertFalse(resembles("Resonance", "Cutoff"))
        self.assertFalse(resembles("Gain", "A"))  # too short to trust

    def test_placeholder_and_unnamed_slots_are_ignored(self):
        (profile,) = self.learn()
        self.assertEqual(sorted(profile["parameters"]), ["10", "11"])

    def test_empty_controller_state_is_detected(self):
        (profile,) = self.learn(controller=False)
        self.assertFalse(profile["fill_controller_state"])

    def test_merge_updates_existing_profile_and_keeps_other_data(self):
        (profile,) = self.learn()
        existing = {
            "profiles": [
                {"name": "example", "verified": True, "parameters": {"99": {"name": "Old", "min": 0, "max": 1}}}
            ]
        }
        merged = learn_profile.merge(existing, [profile])
        (entry,) = merged["profiles"]
        self.assertTrue(entry["verified"])
        self.assertEqual(sorted(entry["parameters"]), ["10", "11", "99"])
        self.assertNotIn("_notes", entry)


if __name__ == "__main__":
    unittest.main()
