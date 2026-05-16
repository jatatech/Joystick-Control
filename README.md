# Joystick Control for Fusion 360

An add-in for Fusion 360 that allows you to use joysticks (and other gamepad controls) to control the active viewport.

# Install

1. Download and unzip the repo.
2. In Fusion, open the Scripts and Add-Ins panel (in the Utilities tab) (or, faster, hit Shift+S)
3. Switch to Add-Ins tab
4. Press the green + button
5. Select the repo folder
6. (optional) you probably want to set it to "Run on Startup" so you don't need to start the add-in the next time you restart Fusion 360

# Usage

Set up with controls that make sense to me (using an XBox360 controller):
 - Left joystick controls panning up/down/left/right
 - Right joystick controls rotating up/down/left/right (NOTE: I'm not happy with how vertical rotation works, happy to accept a pull request that would make it operate like the "constrained orbit" control, it current operates like the "free move" control)
 - Triggers control zoom (NOTE: a bit buggy the first time you use a trigger to zoom, probably something with my view extent math)
 - D-pad (hat) moves to specific view:
   - Up: top
   - Down: bottom
   - Left: left
   - Right: right
 - Buttons also do views:
   - B: front

  ## macOS SDL2 requirement

  If you are using the vendored `pyjoystick` / SDL2 backend on macOS, SDL2 must already be installed on the machine. A typical setup is:

  ```bash
  brew install sdl2
  ```

  The add-in checks common Homebrew and framework locations for SDL2.
   - A: back
   - X: home
 - Since I'm frustrated by "ever so slightly tilted" rotations that I can't figure out, I added a "constrain to primary axis" to the right joystick press (I think that's called "R3" in gamepad buttons?)
  The add-in supports two runtime backends:

  - an existing external `pygame` install, if one is already available to Fusion
  - the vendored `pyjoystick` / SDL2 backend bundled in this repo

  The add-in does not create a virtual environment or install Python packages during startup.

  ## Generic controller defaults

  The original Xbox-style defaults are still supported:

  - Left stick: pan
  - Right stick: orbit
  - Triggers: zoom
  - D-pad / hat: top, bottom, left, right views
  - Face buttons: front, back, home
  - Stick press: constrain orientation to the nearest primary axis

The add-in now supports a single right Joy-Con profile (auto-detected from joystick name) and is intended to work on both Windows and macOS:

- Stick (default): rotate view
- **Y**: bottom view
- **Stick press**: constrain orientation to nearest primary axis
- **+**: right view
  The add-in supports a single right Joy-Con profile, auto-detected from joystick metadata or raw input signatures.

If your Joy-Con reports different button numbers on your machine/driver, update the `JOYCON_*` constants near the top of `Joystick Control.py`.
  - Hold **R** + stick: pan view
  - Hold **ZR** + stick up/down: zoom in/out

Given Fusion 360's weird setup for using libraries, I found it easier to use some simpler libraries, and found [pyjoystick](https://github.com/justengel/pyjoystick). It took some slight modification to get it working using local references to other libraries. I'm not sure how the `import pygame` in there works, but it seems to work on my local machine. Fusion 360 supposedly operates in a 64 bit architecture container, and I've tested that the sdl dll lookup for windows works. I don't know if it works for mac.

  - **X**: top view
  - **A**: right view
  - **B**: bottom view
  - **Y**: left view
  - **+**: front view
  - **Stick press**: constrain orientation to nearest primary axis
  - **SR**: left view

  The standard view buttons now snap to deterministic upright orientations so repeated presses do not leave the camera slightly rolled.

  # Settings UI

  The add-in now exposes a `Joystick Settings` command in Fusion's Add-Ins panel. These values can be adjusted from Fusion's UI and are saved to a local `joystick_settings.json` file next to the add-in:

  - axis deadzone
  - pan sensitivity
  - orbit horizontal sensitivity
  - orbit vertical sensitivity
  - zoom sensitivity
  - pan response exponent
  - orbit horizontal response exponent
  - orbit vertical response exponent
  - zoom response exponent

  The saved settings file is machine-local and is intentionally ignored by git.

  # Known limitations

  - A small first-use zoom jump can still happen from some starting camera states.
  - Orbiting near straight top/down views can still feel slightly jumpy because the camera is close to a singular orientation.

  # Implementation notes

  The add-in uses vendored copies of `pyjoystick` and SDL-related Python modules because Fusion's Python environment is not well-suited to dynamic dependency installation.

  The vendored SDL2 path has local patches for:

  - macOS SDL2 library discovery
  - Joy-Con instance metadata handling in the vendored `pyjoystick` SDL wrapper

  Camera mutations are marshalled back onto Fusion's main thread using a custom event so joystick input does not update the viewport from background threads.

  If your Joy-Con reports different button numbers on your machine or driver, update the `JOYCON_*` constants near the top of `Joystick Control.py`.
The add-in is marked as supporting mac. On startup it now chooses an already-installed `pygame` if one is available, otherwise it falls back to the vendored `pyjoystick`/SDL2 path.
  # Release notes

  The current release baseline focuses on runtime stability and controller usability:

  - no startup-time package installation or virtualenv bootstrap
  - working macOS vendored SDL2 fallback path
  - Joy-Con (R) profile support
  - main-thread camera updates for Fusion stability
  - deterministic upright view snaps
  - Fusion UI settings dialog for tuning
