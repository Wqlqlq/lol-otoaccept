[Türkçe](README.md) | **English**

# LoL Auto Accept

A simple Windows desktop app that detects the **ACCEPT** button shown when a match is found in
the League of Legends client, using screenshots, and performs **one** mouse click at a point you
chose beforehand.

The app does only two things:

- Takes screenshots of the screen region you selected (and compares them with OpenCV template
  matching).
- Simulates a normal mouse click (`pyautogui.click`).

It **never** touches the game's files, memory, API (LCU) or process.

---

## Easiest way: ready-made exe (no Python needed)

1. Download **`LoLAutoAccept.exe`** from the
   [Releases](https://github.com/Wqlqlq/lol-otoaccept/releases/latest) page.
2. Put the exe in a folder of its own (e.g. `Documents\LoLAutoAccept`). `config.json`,
   `logs.txt` and `assets\accept_template.png` are created next to the exe.
3. Double-click it and follow the [Usage](#usage) steps below.

If you see "Windows protected your PC", click **More info** → **Run anyway**. This warning is
normal because the exe is not signed. Since it listens for a keyboard shortcut and performs
mouse clicks, some antivirus programs may raise a false alarm. The exe is built from the code
in this repository by GitHub Actions, and its SHA256 hash is listed on the release page.

If you want to run it from source code, follow the steps below.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer

## 1. Installing Python

1. Download the latest Python 3 from <https://www.python.org/downloads/windows/>.
2. On the first screen of the installer, tick **"Add python.exe to PATH"**, then click
   **Install Now**.
3. Open a new Command Prompt (cmd) or PowerShell and check:

   ```bat
   python --version
   ```

   You should see `Python 3.10` or newer.

## 2. Installing dependencies

In the project folder (where this README is), run:

```bat
pip install -r requirements.txt
```

Optionally, create a virtual environment first:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Installed packages: `opencv-python`, `numpy`, `Pillow`, `pyautogui`, `pynput`.
(`tkinter` ships with the Windows installer of Python.)

## 3. Running the app

```bat
python main.py
```

The "LoL Auto Accept" window opens. Settings are saved to `config.json` and loaded
automatically the next time the app starts.

---

## Usage

You only need to set up three things once: **Detection Area**, **Template Image** and
**Click Position**. While selecting them, the LoL client should be open at its usual size and
position.

Every selection screen **freezes** and dims the current screen image, so there is no need to
hurry. Press **ESC** or **right-click** to cancel a selection.

### Selecting the Detection Area

1. Click **Select Area**. The main window hides and the screen dims.
2. Drag a rectangle with the mouse around **the region where the ACCEPT button appears** when a
   match is found. Selecting an area slightly larger than the button is a good idea.
3. The selected area is shown in the main window, for example:
   `x=700  y=350  width=500  height=400`.

The smaller the region, the faster each check is. It cannot be smaller than the template.

### Capturing the Template

The template is the image the app searches for on screen (the ACCEPT button itself).

1. While the match found popup is on screen (e.g. when a match is found while you are in
   queue), switch to the app and click **Capture Template**. The screen freezes instantly, so
   you can take your time even if the popup closes.
2. Drag a tight rectangle around the **ACCEPT** button.
3. The image is saved as `assets/accept_template.png` and a small preview of it is shown in the
   main window.

Tips:

- Capture the template while the mouse is **not over** the button. The hover effect changes how
  it looks.
- The template must be smaller than the Detection Area (you get a warning otherwise).
- If you change the client language, resolution or window size, capture the template again.
- `assets/accept_template.png` is not included in the repository. The button looks different
  depending on resolution and language, so you need to capture it from your own screen.

### Selecting the Click Position

1. Click **Select Click Point**.
2. A crosshair and the coordinates appear on the screen.
3. **Click once** on the point to click when a match is found, i.e. the center of the ACCEPT
   button.
4. The coordinate is saved, for example: `x=960  y=620`.

### Detection Threshold and Check Interval

- **Detection Threshold** (default `0.90`): the minimum similarity required for a match
  (0.50–1.00). Raise it if you get wrong clicks. If the button is visible but not detected (the
  Confidence value stays below the threshold), lower it to `0.80–0.85` or capture the template
  again.
- **Check Interval** (default `300` ms): how often the screen is checked (50–5000 ms).

### Monitoring

- **Start Monitoring** starts watching. Monitoring runs in a separate thread, so the window
  never freezes.
- On every check, only the Detection Area is captured, and the highest similarity (confidence)
  is found with `cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED)`.
- The **Preview** on the right shows the latest capture and the current **Confidence** value.
  When a match is found, its location is outlined in green.
- The settings buttons are locked while monitoring. Stop monitoring first to change them.

Status values:

| Status           | Meaning                                                      |
| ---------------- | ------------------------------------------------------------ |
| `Idle`           | Monitoring is off                                            |
| `Monitoring`     | Watching the screen, waiting for the button                  |
| `Match detected` | The button was detected (confidence ≥ threshold)             |
| `Clicked`        | The click was made; waiting for the button to disappear      |

### Click spam protection

The button can stay on screen for several seconds, so the app does not keep clicking. Instead
of a simple cooldown, it uses a state machine:

```
WAITING ──(confidence ≥ threshold)──> DETECTED ──(click)──> WAIT_FOR_DISAPPEAR
WAIT_FOR_DISAPPEAR ──(confidence < threshold)──> WAITING
```

After a click, the button must first **disappear** from the screen before another click can
happen. So that a single flickering frame cannot cause another click, the disappearance is
confirmed only after 3 consecutive checks below the threshold. This way, if the match you
accepted falls apart and a new match is found, the app clicks again, but it never clicks twice
for the same popup.

---

## Hotkeys

| Key                    | What it does                                                         |
| ---------------------- | -------------------------------------------------------------------- |
| **F8**                 | Starts / stops monitoring. Works while the game window is active (global). |
| **ESC**                | Leaves the selection screen, only if one is open. Does not close the app. |
| **Right-click**        | Cancels the selection while a selection screen is open.             |

Hotkeys are read with `pynput` and are not blocked: the game and other programs still receive
the keys normally.

---

## Settings: `config.json`

Everything you select is saved automatically:

```json
{
  "detection_region": {
    "x": 700,
    "y": 350,
    "width": 500,
    "height": 400
  },
  "click_position": {
    "x": 960,
    "y": 620
  },
  "threshold": 0.9,
  "check_interval_ms": 300,
  "template_path": "assets/accept_template.png"
}
```

If the file is corrupted, the app shows a warning, starts with default settings and fixes the
file on the next save.

## Logs: `logs.txt`

Events are written to `logs.txt`:

```
22:14:01 Monitoring started
22:16:32 Template detected confidence=0.94
22:16:32 Clicked x=960 y=620
22:16:36 Template disappeared
22:20:15 Monitoring stopped
```

---

## Building the exe yourself

On Windows, run this in the project folder:

```bat
build_exe.bat
```

The result is `dist\LoLAutoAccept.exe` (PyInstaller, single file, no console window).

### Publishing a new version

Increase the number in the `VERSION` file (e.g. `1.0.0` → `1.0.1`) and push the change. You can
also do this on the GitHub website by opening the file and editing it with the pencil icon.
`.github/workflows/release.yml` builds the exe on Windows, checks that it starts, and publishes
it as a GitHub release named `v1.0.1`. Pushing a tag such as `v1.0.1` does the same.

The release description comes from `.github/release-notes.md`. Changing that file updates the
release page of the current version (the exe is rebuilt).

---

## Troubleshooting

- **The button is visible but not detected:** Check that the button appears in the Preview.
  No other window may cover the Detection Area, **including this app's window**. If the
  Confidence is low, lower the threshold a little or capture the template again.
- **Clicks or F8 do not work while the game is open:** If the LoL client runs as administrator,
  Windows blocks programs running with normal rights from sending clicks to it. In that case,
  start the exe as administrator, or open Command Prompt **as administrator** and run
  `python main.py`.
- **"PyAutoGUI fail-safe" error:** If the mouse is in a corner of the screen at the moment of a
  click, PyAutoGUI stops for safety. This is an emergency stop feature. Start monitoring again.
- **Coordinates are off:** Windows display scaling (125%, 150%) is supported; the app works
  with real pixel coordinates. If you changed the scaling or resolution, select the area, the
  template and the click point again.
- **Multiple monitors:** Selection and detection happen on the **primary monitor**. Open the
  LoL client on the primary monitor.

---

## File structure

```
lol-otoaccept/
├── main.py              # Main window (tkinter), entry point of the app
├── detector.py          # Template matching, state machine, monitoring thread
├── screen_selector.py   # Full-screen area / point selection screen
├── config_manager.py    # Reading/writing config.json and the settings data types
├── hotkeys.py           # Global hotkeys (F8 / ESC) with pynput
├── logger.py            # Logging to logs.txt
├── config.json          # Saved settings
├── requirements.txt
├── build_exe.bat        # Builds LoLAutoAccept.exe with PyInstaller
├── VERSION              # Version number; changing it publishes a new release
├── README.md            # Turkish README
├── README.en.md         # English README
├── .github/
│   ├── release-notes.md # Release description (Turkish + English)
│   └── workflows/
│       └── release.yml  # Builds the exe and publishes the release
└── assets/
    └── accept_template.png   # Created with "Capture Template"
```

## Disclaimer

This tool only uses screenshots and normal mouse clicks. Still, using third-party tools is
subject to the game's terms of service. You use it at your own risk.
