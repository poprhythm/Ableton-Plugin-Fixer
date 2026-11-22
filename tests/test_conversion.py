"""
Tests for the VST2 -> VST3 parameter conversion helpers.

Run from the repository root:  python -m unittest discover tests
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apf  # noqa: E402

PRESET_TEXT = """#pgm=Test
/*@Meta
Author:
'someone'
*/
#AM=ExampleSynth
#cm=Filter
Model=0
Freq=47.50
Res=4.50
#cm=Clock
Mult=92.00
Base=2
"""

PROFILE = {
    "blank_unmapped": True,
    "parameters": {
        "148": {"min": 30, "max": 150, "section": "Filter", "key": "Freq"},
        "257": {"min": 0, "max": 3, "section": "Clock", "key": "Base", "stepped": True},
        "256": {"min": 50, "max": 200, "section": "Clock", "key": "Missing"},
    },
}


def slot(name, pid, manual, rng=("0", "1"), extra_tags=False):
    tags = ""
    if extra_tags:  # what a Live 11 file already contains
        tags = (
            '<LastUserRange><First Value="Invalid" /><Last Value="Invalid" /></LastUserRange>'
            '<LastInternalRange><First Value="0" /><Last Value="1" /></LastInternalRange>'
        )
    flank = '<ParameterIdFlankBool Value="false" />' if extra_tags else ""
    return ET.fromstring(
        f'<PluginFloatParameter Id="0"><ParameterName Value="{name}" />'
        f'<ParameterId Value="{pid}" />{flank}<VisualIndex Value="3" />'
        f'<ParameterValue><LomId Value="21" /><KeyMidi><Channel Value="16" /></KeyMidi>'
        f'<Manual Value="{manual}" />'
        f'<MidiControllerRange><Min Value="{rng[0]}" /><Max Value="{rng[1]}" /></MidiControllerRange>'
        f'<AutomationTarget Id="17912" /><ModulationTarget Id="17913" /></ParameterValue>'
        f"{tags}</PluginFloatParameter>"
    )


def value(slot_elem, path):
    return slot_elem.find(path).get("Value")


class PresetTextTests(unittest.TestCase):
    def test_sections_and_keys(self):
        preset = apf.parse_preset_text(PRESET_TEXT)
        self.assertEqual(preset["Filter"]["Freq"], "47.50")
        self.assertEqual(preset["Clock"]["Base"], "2")
        self.assertNotIn("Author", preset.get("Filter", {}))


class SlotConversionTests(unittest.TestCase):
    def setUp(self):
        self.replacer = apf.PluginReplacer("unused.als")
        self.preset = apf.parse_preset_text(PRESET_TEXT)

    def convert(self, s):
        return self.replacer._convert_slot(s, self.preset, PROFILE)

    def test_value_comes_from_preset_and_range_is_rescaled(self):
        s = slot("Filter: Cutoff", "148", "0.1", rng=("0", "0.18"))
        self.assertEqual(self.convert(s)[0], "converted")
        self.assertEqual(value(s, "ParameterValue/Manual"), "47.5")
        self.assertEqual(value(s, "ParameterValue/MidiControllerRange/Min"), "30")
        self.assertEqual(value(s, "ParameterValue/MidiControllerRange/Max"), "51.6")
        self.assertEqual(value(s, "LastUserRange/First"), "30")
        self.assertEqual(value(s, "LastUserRange/Last"), "150")
        # a real parameter keeps its MIDI mapping
        self.assertIsNotNone(s.find("ParameterValue/KeyMidi"))

    def test_stepped_parameter_is_whole_number(self):
        s = slot("Clock: Steps", "257", "0.5479452014")
        self.convert(s)
        self.assertEqual(value(s, "ParameterValue/Manual"), "2")

    def test_falls_back_to_linear_rescale_when_preset_lacks_key(self):
        s = slot("Clock: Scale", "256", "0.5")
        self.convert(s)
        self.assertEqual(value(s, "ParameterValue/Manual"), "125")

    def test_unmapped_parameter_is_blanked_and_keeps_target_ids(self):
        s = slot("Filter: ModDepth", "151", "0.658")
        self.assertEqual(self.convert(s)[0], "blanked")
        self.assertEqual(value(s, "ParameterName"), "")
        self.assertEqual(value(s, "ParameterId"), "-1")
        self.assertIsNone(s.find("ParameterValue/KeyMidi"))
        self.assertEqual(s.find("ParameterValue/AutomationTarget").get("Id"), "17912")
        self.assertEqual(s.find("ParameterValue/ModulationTarget").get("Id"), "17913")

    def test_tags_written_exactly_once_for_live10_and_live11_slots(self):
        for extra in (False, True):
            s = slot("Filter: Cutoff", "148", "0.1", extra_tags=extra)
            self.convert(s)
            tags = [c.tag for c in s]
            for tag in apf.PluginReplacer.SLOT_TAGS:
                self.assertEqual(tags.count(tag), 1, f"{tag} (live11 tags={extra})")
            # flank bool must directly follow ParameterId
            self.assertEqual(tags[tags.index("ParameterId") + 1], "ParameterIdFlankBool")

    def test_profile_without_parameter_knowledge_leaves_slots_alone(self):
        s = slot("Example: Mix", "42", "0.3")
        before = ET.tostring(s)
        status = self.replacer._convert_slot(s, {}, {"parameters": {}})[0]
        self.assertEqual(status, "untouched")
        self.assertEqual(ET.tostring(s), before)


class ValidationTests(unittest.TestCase):
    def test_duplicate_tag_is_refused(self):
        replacer = apf.PluginReplacer("unused.als")
        root = ET.fromstring("<Ableton><X /></Ableton>")
        bad = slot("a", "148", "0.1", extra_tags=True)
        ET.SubElement(bad, "ParameterIdFlankBool").set("Value", "false")
        root.append(bad)
        with self.assertRaises(ValueError):
            replacer._validate_conversion(root, replacer._target_ids(root))

    def test_changed_target_ids_are_refused(self):
        replacer = apf.PluginReplacer("unused.als")
        root = ET.fromstring("<Ableton><X /></Ableton>")
        root.append(slot("a", "148", "0.1"))
        before = replacer._target_ids(root)
        root.find(".//AutomationTarget").set("Id", "999")
        with self.assertRaises(ValueError):
            replacer._validate_conversion(root, before)

    def test_clean_project_passes(self):
        replacer = apf.PluginReplacer("unused.als")
        root = ET.fromstring("<Ableton><X /></Ableton>")
        root.append(slot("a", "148", "0.1", extra_tags=True))
        replacer._validate_conversion(root, replacer._target_ids(root))


class ProfileTests(unittest.TestCase):
    def test_no_profiles_ship_with_the_tool(self):
        # plugin knowledge is supplied by the user, never bundled
        self.assertEqual(apf.load_profiles("does_not_exist.json"), [])

    def test_profiles_load_from_a_given_file_and_match_by_name(self):
        import json, tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            path.write_text(json.dumps({"profiles": [{"name": "Example", "match": ["example"]}]}))
            profiles = apf.load_profiles(str(path))  # absolute path
        replacer = apf.PluginReplacer("unused.als", profiles=profiles)
        self.assertEqual(replacer._find_profile("Example(x64)", "Example")["name"], "Example")
        self.assertIsNone(replacer._find_profile("Other", "Other"))

    def test_example_file_is_valid_and_not_loaded_by_default(self):
        import json

        example = Path(__file__).resolve().parent.parent / "plugin_profiles.example.json"
        data = json.loads(example.read_text(encoding="utf-8"))
        self.assertEqual(data["profiles"][0]["name"], "ExamplePlugin")


if __name__ == "__main__":
    unittest.main()
