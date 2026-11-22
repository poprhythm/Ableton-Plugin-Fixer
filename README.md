<h1 align="center">Ableton Plugin Fixer</h1>
<div align="center">
  <img src="https://www.glaurossi.com/assets/apf.jpg"  />
</div>

###

## What is Ableton Plugin Fixer?
**Ableton Plugin Fixer (APF)** is a tool designed to help users replace VST2 plugins with their VST3 equivalents in Ableton Live projects. This is particularly useful for those who encounter missing plugins when opening older projects after updating to newer versions.

Many users have expressed frustration with Ableton's plugin management system, noting that it can be inefficient compared to other DAWs. APF addresses some of these concerns by providing a straightforward solution for plugin replacement.

### Key features

 - **Preserves Everything**: All parameter settings; automation, presets and midi macros/mappings.
 - **Smart Matching**: Uses fuzzy name matching and unique plugin IDs.
 - **Safe Operation**: Creates backups before making changes.

> [!CAUTION]
> This is a work in progress tool that modifies Ableton Live project files. While the tool has built-in backup functionality, always work with your own backups and test thoroughly -- I'm not responsible for any data loss or project corruption.

## Installation

1. **Requirements**
   - Python 3.7+
   - macOS or Windows 10+
   - Ableton Live

2. **Download**
   - Git Clone

     ```bash 
     git clone https://github.com/glaurossi/Ableton-Plugin-Fixer
     cd Ableton-Plugin-Fixer
     ```
   - Or download the files [here](https://github.com/glaurossi/Ableton-Plugin-Fixer/releases)

3. **Usage**
   - Open your project in the latest version of Ableton Live installed on your system
   - Save a Copy
   - Run the saved copy through `apf.py`:

      ```bash
      py apf.py
      ```
      or
      ```bash
      python apf.py project.als
      ```

<h2 align="left">Showcase</h2>
<div align="center">
  <img src="https://www.glaurossi.com/assets/apf_showcase.avif"  />
</div>

## Configuration
The tool uses a `config.json` to control some of its behavior.

| Config                   | Description                                               | Default |
|--------------------------|-----------------------------------------------------------|---------|
| `database.path`          | Path to Live's plugin database                            | null    |
| `use_unique_id`          | Match plugins by their unique ID first.                   | true    |
| `fuzzy_name_threshold`   | (0.0-1.0): How similar plugin names need to be to match.  | 0.8     |
| `prefer_newer_version`   | Sort by newer first when multiple matches exist.          | false   |
| `dry_run`                | Preview changes without modifying files                   | true    |
| `create_backup`          | Automatically backup projects before changes              | true    |
| `backup_suffix`          | File extension for backups (e.g., ".bkp", ".backup").     | .bkp    |
| `debug_level`            | Log verbosity: 1 (minimal) to 3 (everything)              | 1       |
| `log_file`               | Where to save the logs.                                   | apf.log |

## Unattended runs
```bash
python apf.py project.als --choose first --skip SomePlugin --no-pause
```
- `--choose first` takes the first replacement for every plugin (default is to ask).
- `--skip NAME` skips every instance of that plugin (repeatable).
- `--no-pause` skips the final "press Enter" (it is also skipped automatically when input is piped).

At the end APF prints an outcome table per plugin (replaced / skipped / failed with the reason / no match).
Nothing is saved if the converted project fails its checks (a parameter slot with a repeated tag, or any
automation/modulation target id that changed).

## VST3 state and parameter conversion
Swapping the plugin wrapper is not enough for every plugin. Some VST3s store their state or parameters
differently from the VST2. The project then loads with the right preset name but the wrong sound, and
configured parameters do not respond. Fixing that needs knowledge about the specific plugin, so APF does not
ship any: you supply optional **profiles** (`plugin_profiles.json`, see `plugin_profiles.example.json`) and a
helper, `learn_profile.py`, creates them from a Live set. Plugins without a profile are converted as before,
with a note that their parameter slots were left unchanged.

What a profile can ask APF to do:

- **`fill_controller_state`**: some VST3s are saved by Live with the preset in both `ProcessorState` and
  `ControllerState`. APF only wrote `ProcessorState`, which leaves such a plugin starting from defaults.
- **Parameter units**: VST2 parameter slots hold values normalized to 0-1, but some VST3s use real units
  (for example a frequency knob of 30-150). A normalized value then pins the knob at its minimum and it stops
  responding. APF rewrites each configured parameter's value (read from the device's own state text when the
  profile says where it lives, otherwise rescaled linearly), rescales the stored MIDI mapping range, and writes
  the tags Live expects (`ParameterIdFlankBool`, `LastUserRange`, `LastInternalRange`) exactly once.
  Live 11 files already contain those tags and Live 10 files do not; both work.
- **`blank_unmapped`**: configured slots whose parameter is not in the profile become blank slots instead of
  staying clamped. APF lists them so you know what to re-add by hand.

Config (`config.json`):

| Config                                | Description                                                              | Default                |
|---------------------------------------|--------------------------------------------------------------------------|------------------------|
| `conversion.fill_controller_state`    | `"profile"` (only plugins whose profile asks for it), `true` or `false`   | "profile"              |
| `conversion.convert_parameters`       | Convert parameter slots for plugins that have a profile                  | true                   |
| `conversion.profiles_path`            | Profiles file (relative to `apf.py`, or absolute)                        | plugin_profiles.json   |

### Creating a plugin profile
1. In Live, make a new set containing just the plugin's **VST3**. Use the device's *Configure* button and add
   the parameters your projects use by touching each knob. Save the set.
2. Run `python learn_profile.py sample.als --out plugin_profiles.json` (add `--plugin NAME` if the set holds
   several VST3s). It records each parameter's id and real-unit range, whether `ControllerState` is used, and,
   when the state is sectioned text, where each value lives (see the notes it prints for anything ambiguous;
   knobs left at a value that other settings share cannot be located, so set them to unusual values).
3. APF assumes a parameter's id is the same in the VST2 and the VST3. Check that for your plugin.
4. Convert a **copy** of a project, listen, then set `"verified": true` in the profile.

`plugin_profiles.json` is in `.gitignore`: it is local plugin knowledge, kept out of the repository.

## Limitations
Some plugins may have different parameter layouts across versions, so presets might not transfer over.

## TODO

- [x]  Add macOS support
- [ ]  Support VST3 plugin updates (e.g., Kontakt 7 → Kontakt 8)
- [ ]  Fix .als extension in the root element
- [x]  Implement multi-level debug
    - Debug 1 (Minimal): Current behavior; essential logs only.
    - Debug 2 (Advanced): Debug 1 + logs of every change applied to project files.
    - Debug 3 (Nerdy): Debug 1 + Debug 2 + everything else.
- [ ]  Integrate Live's PluginScanner to refresh database before processing project files

## Contributions
Any improvements, bug fixes, or feature additions are welcome. Feel free to do so by [submitting a PR](https://github.com/glaurossi/Ableton-Plugin-Fixer/pulls).

## Issues

Found a bug or have a feature request? [Open an issue](https://github.com/glaurossi/Ableton-Plugin-Fixer/issues).

<h2 align="left">Star History</h2>
<p align="center">
  <a href="https://www.star-history.com/#glaurossi/Ableton-Plugin-Fixer">
    <img src="https://api.star-history.com/svg?repos=glaurossi/Ableton-Plugin-Fixer" alt="Star History Chart" width="800">
  </a>
</p>

## License

MIT License - see [LICENSE](LICENSE) file for details.
