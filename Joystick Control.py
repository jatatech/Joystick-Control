import os
import sys
import json

from . import config
from .lib import fusionAddInUtils as futil
from adsk.core import LogLevels

ADDIN_DIR = os.path.dirname(os.path.realpath(__file__))
BACKEND_PYGAME = "pygame"
BACKEND_PYJOYSTICK = "pyjoystick"

installedPygame = False
selectedJoystickBackend = None
backendBootstrapError = None


pyjoystickRunEventLoop = None


def loadPyJoystickEventLoop():
    global pyjoystickRunEventLoop
    if pyjoystickRunEventLoop is None:
        from .Modules.pyjoystick.sdl2 import run_event_loop as importedRunEventLoop
        pyjoystickRunEventLoop = importedRunEventLoop
    return pyjoystickRunEventLoop


def selectJoystickBackend():
    global installedPygame
    global selectedJoystickBackend
    global backendBootstrapError
    global pygame

    try:
        import pygame as importedPygame

        pygame = importedPygame
        installedPygame = True
        selectedJoystickBackend = BACKEND_PYGAME
        backendBootstrapError = None
        futil.log(f"{config.ADDIN_NAME}: using existing pygame install", LogLevels.InfoLogLevel)
        return
    except Exception as pygameError:
        installedPygame = False
        futil.log(
            f"{config.ADDIN_NAME}: pygame is unavailable ({pygameError}); trying vendored pyjoystick/SDL2 backend",
            LogLevels.WarningLogLevel,
        )

    try:
        loadPyJoystickEventLoop()
        selectedJoystickBackend = BACKEND_PYJOYSTICK
        backendBootstrapError = None
        futil.log(
            f"{config.ADDIN_NAME}: using vendored pyjoystick/SDL2 backend from {ADDIN_DIR!r}",
            LogLevels.InfoLogLevel,
        )
    except Exception as backendError:
        selectedJoystickBackend = None
        backendBootstrapError = backendError
        futil.log(
            f"{config.ADDIN_NAME}: failed to initialize any joystick backend ({backendError})",
            LogLevels.ErrorLogLevel,
        )


selectJoystickBackend()


from .Modules.pyjoystick.interface import KeyTypes, Key, Joystick

from adsk.core import Vector3D, Matrix3D, Application, Point3D, Camera, ViewOrientations
from time import sleep
from math import pow, pi, radians
from adsk import doEvents
from threading import Event, Thread, Lock
from typing import Literal

# Special number to tell camera to go orientation home
HOME_ORIENTATION = -1
# Special number to tell the camera to constrain the upVector to a primary axis
CONSTRAIN_ORIENTATION = -2
CONTROLLER_PROFILE_DEFAULT = "default"
CONTROLLER_PROFILE_JOYCON_RIGHT = "joycon_right"

# Configure as you wish
ZOOM_SCALE = 0.1
PAN_AXIS_SCALE = 0.1
ROTATION_AXIS_SCALE = 0.01
PAN_ZOOM_COMPENSATION = 0.0005
AXIS_DEADZONE = 0.15
CAMERA_VECTOR_EPSILON = 1e-6
JOYCON_PAN_SENSITIVITY = 0.75
JOYCON_ROTATION_HORIZONTAL_SENSITIVITY = 0.34
JOYCON_ROTATION_VERTICAL_SENSITIVITY = 0.3
JOYCON_ZOOM_SENSITIVITY = 0.3
JOYCON_PAN_RESPONSE_EXPONENT = 1.8
JOYCON_ROTATION_HORIZONTAL_RESPONSE_EXPONENT = 1.65
JOYCON_ROTATION_VERTICAL_RESPONSE_EXPONENT = 1.8
JOYCON_ZOOM_RESPONSE_EXPONENT = 1.8
JOYCON_STICK_X_AXIS = 1
JOYCON_STICK_Y_AXIS = 0
JOYCON_BUTTON_X = 0
JOYCON_BUTTON_A = 1
JOYCON_BUTTON_Y = 2
JOYCON_BUTTON_B = 3
JOYCON_BUTTON_HOME = 5
JOYCON_BUTTON_PLUS = 6
JOYCON_BUTTON_R = 16
JOYCON_BUTTON_ZR = 18
JOYCON_BUTTON_STICK = 17
JOYCON_BUTTON_SR = 13
JOYCON_BUTTON_SL = 14

if not installedPygame:
    PAN_X_AXIS = 0
    PAN_Y_AXIS = 1
    ZOOM_POS_AXIS = 2
    ROTATE_X_AXIS = 3
    ROTATE_Y_AXIS = 4
    ZOOM_NEG_AXIS = 5
else:
    PAN_X_AXIS = 0
    PAN_Y_AXIS = 1
    ROTATE_X_AXIS = 2
    ROTATE_Y_AXIS = 3
    ZOOM_POS_AXIS = 4
    ZOOM_NEG_AXIS = 5

HAT_TO_VIEW = {
    Key.HAT_NAME_UP: ViewOrientations.TopViewOrientation,
    Key.HAT_NAME_DOWN: ViewOrientations.BottomViewOrientation,
    Key.HAT_NAME_LEFT: ViewOrientations.LeftViewOrientation,
    Key.HAT_NAME_RIGHT: ViewOrientations.RightViewOrientation,
}
BUTTON_TO_VIEW = {
    0: ViewOrientations.FrontViewOrientation,
    1: ViewOrientations.BackViewOrientation,
    2: HOME_ORIENTATION,
    9: CONSTRAIN_ORIENTATION,
}
JOYCON_BUTTON_TO_VIEW = {
    JOYCON_BUTTON_A: ViewOrientations.RightViewOrientation,
    JOYCON_BUTTON_B: ViewOrientations.BottomViewOrientation,
    JOYCON_BUTTON_X: ViewOrientations.TopViewOrientation,
    JOYCON_BUTTON_Y: ViewOrientations.LeftViewOrientation,
    JOYCON_BUTTON_HOME: HOME_ORIENTATION,
    JOYCON_BUTTON_STICK: CONSTRAIN_ORIENTATION,
    JOYCON_BUTTON_PLUS: ViewOrientations.FrontViewOrientation,
    JOYCON_BUTTON_SR: ViewOrientations.LeftViewOrientation,
}

JOYCON_BUTTON_NAME_TO_VIEW = {
    "a": ViewOrientations.TopViewOrientation,
    "b": ViewOrientations.RightViewOrientation,
    "x": ViewOrientations.LeftViewOrientation,
    "y": ViewOrientations.BottomViewOrientation,
    "back": HOME_ORIENTATION,
    "guide": HOME_ORIENTATION,
    "leftstick": CONSTRAIN_ORIENTATION,
    "start": ViewOrientations.FrontViewOrientation,
}

JOYCON_GUID_KEYWORDS = (
    "7e05000007200000",
    "joy-con (r)",
    "nintendo switch right joy-con",
)

JOYCON_AXIS_NAME_X = ("leftx", "rightx")
JOYCON_AXIS_NAME_Y = ("lefty", "righty")
JOYCON_BUTTON_NAME_R = ("rightshoulder",)
JOYCON_BUTTON_NAME_ZR = ("leftshoulder", "righttrigger")
JOYCON_RAW_SIGNATURE_BUTTONS = frozenset((JOYCON_BUTTON_R, JOYCON_BUTTON_ZR, JOYCON_BUTTON_HOME, JOYCON_BUTTON_PLUS))

JOYCON_NAME_KEYWORDS = (
    "joy-con (r)",
    "joycon (r)",
    "joy-con right",
    "joycon right",
)

CAMERA_UPDATE_EVENT_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_camera_update".replace(" ", "_")
SETTINGS_FILE = os.path.join(ADDIN_DIR, "joystick_settings.json")
SETTINGS_COMMAND_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_settings".replace(" ", "_")
SETTINGS_COMMAND_NAME = "Joystick Settings"
SETTINGS_COMMAND_DESCRIPTION = "Adjust joystick sensitivity and response settings."
SETTINGS_WORKSPACE_ID = "FusionSolidEnvironment"
SETTINGS_PANEL_ID = "SolidScriptsAddinsPanel"

SETTINGS_FIELDS = (
    {
        "key": "AXIS_DEADZONE",
        "input_id": "axis_deadzone",
        "label": "Axis Deadzone",
        "min": 0.0,
        "max": 0.5,
        "step": 0.01,
    },
    {
        "key": "JOYCON_PAN_SENSITIVITY",
        "input_id": "joycon_pan_sensitivity",
        "label": "Pan Sensitivity",
        "min": 0.05,
        "max": 2.0,
        "step": 0.01,
    },
    {
        "key": "JOYCON_ROTATION_HORIZONTAL_SENSITIVITY",
        "input_id": "joycon_rotation_horizontal_sensitivity",
        "label": "Orbit Horizontal Sensitivity",
        "min": 0.05,
        "max": 2.0,
        "step": 0.01,
    },
    {
        "key": "JOYCON_ROTATION_VERTICAL_SENSITIVITY",
        "input_id": "joycon_rotation_vertical_sensitivity",
        "label": "Orbit Vertical Sensitivity",
        "min": 0.05,
        "max": 2.0,
        "step": 0.01,
    },
    {
        "key": "JOYCON_ZOOM_SENSITIVITY",
        "input_id": "joycon_zoom_sensitivity",
        "label": "Zoom Sensitivity",
        "min": 0.05,
        "max": 2.0,
        "step": 0.01,
    },
    {
        "key": "JOYCON_PAN_RESPONSE_EXPONENT",
        "input_id": "joycon_pan_response_exponent",
        "label": "Pan Response Exponent",
        "min": 0.5,
        "max": 3.0,
        "step": 0.05,
    },
    {
        "key": "JOYCON_ROTATION_HORIZONTAL_RESPONSE_EXPONENT",
        "input_id": "joycon_rotation_horizontal_response_exponent",
        "label": "Orbit Horizontal Response Exponent",
        "min": 0.5,
        "max": 3.0,
        "step": 0.05,
    },
    {
        "key": "JOYCON_ROTATION_VERTICAL_RESPONSE_EXPONENT",
        "input_id": "joycon_rotation_vertical_response_exponent",
        "label": "Orbit Vertical Response Exponent",
        "min": 0.5,
        "max": 3.0,
        "step": 0.05,
    },
    {
        "key": "JOYCON_ZOOM_RESPONSE_EXPONENT",
        "input_id": "joycon_zoom_response_exponent",
        "label": "Zoom Response Exponent",
        "min": 0.5,
        "max": 3.0,
        "step": 0.05,
    },
)
SETTINGS_FIELDS_BY_KEY = {field["key"]: field for field in SETTINGS_FIELDS}

cameraUpdateEvent = None
cameraStateLock = Lock()
cameraUpdateQueued = False
pendingOrientation = None
settingsCommandDefinition = None
settingsCommandControl = None


def getCurrentSettings() -> dict[str, float]:
    return {field["key"]: globals()[field["key"]] for field in SETTINGS_FIELDS}


def clampSettingValue(field: dict[str, float | str], value) -> float:
    try:
        numericValue = float(value)
    except (TypeError, ValueError):
        numericValue = float(globals()[field["key"]])
    return min(field["max"], max(field["min"], numericValue))


def applySettings(settings: dict[str, float]) -> None:
    for field in SETTINGS_FIELDS:
        globals()[field["key"]] = clampSettingValue(field, settings.get(field["key"], globals()[field["key"]]))


def loadSettings() -> None:
    if not os.path.exists(SETTINGS_FILE):
        return

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as settingsFile:
            loadedSettings = json.load(settingsFile)
        if not isinstance(loadedSettings, dict):
            raise ValueError("settings file must contain a JSON object")

        settings = getCurrentSettings()
        for field in SETTINGS_FIELDS:
            if field["key"] in loadedSettings:
                settings[field["key"]] = loadedSettings[field["key"]]
        applySettings(settings)
    except Exception as settingsError:
        futil.log(
            f"{config.ADDIN_NAME}: failed to load settings from {SETTINGS_FILE!r} ({settingsError})",
            LogLevels.WarningLogLevel,
        )


def saveSettings() -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as settingsFile:
        json.dump(getCurrentSettings(), settingsFile, indent=2, sort_keys=True)


def onSettingsCommandCreated(args) -> None:
    command = args.command
    inputs = command.commandInputs

    for field in SETTINGS_FIELDS:
        spinnerInput = inputs.addFloatSpinnerCommandInput(
            field["input_id"],
            field["label"],
            "",
            field["min"],
            field["max"],
            field["step"],
            globals()[field["key"]],
        )
        spinnerInput.tooltip = field["label"]

    futil.add_handler(command.execute, onSettingsCommandExecute, name=f"{config.ADDIN_NAME}_settings_execute")


def onSettingsCommandExecute(args) -> None:
    command = args.firingEvent.sender
    inputs = command.commandInputs
    updatedSettings = {}

    for field in SETTINGS_FIELDS:
        updatedSettings[field["key"]] = inputs.itemById(field["input_id"]).value

    applySettings(updatedSettings)
    saveSettings()
    futil.log(f"{config.ADDIN_NAME}: updated joystick settings from Fusion UI", LogLevels.InfoLogLevel)


def createSettingsCommand() -> None:
    global settingsCommandDefinition
    global settingsCommandControl

    ui = app.userInterface
    settingsCommandDefinition = ui.commandDefinitions.itemById(SETTINGS_COMMAND_ID)
    if settingsCommandDefinition is None:
        settingsCommandDefinition = ui.commandDefinitions.addButtonDefinition(
            SETTINGS_COMMAND_ID,
            SETTINGS_COMMAND_NAME,
            SETTINGS_COMMAND_DESCRIPTION,
        )
    futil.add_handler(
        settingsCommandDefinition.commandCreated,
        onSettingsCommandCreated,
        name=f"{config.ADDIN_NAME}_settings_created",
    )

    workspace = ui.workspaces.itemById(SETTINGS_WORKSPACE_ID)
    if workspace is None:
        futil.log(
            f"{config.ADDIN_NAME}: workspace {SETTINGS_WORKSPACE_ID!r} was not found; settings command was not added to the UI",
            LogLevels.WarningLogLevel,
        )
        return

    panel = workspace.toolbarPanels.itemById(SETTINGS_PANEL_ID)
    if panel is None:
        futil.log(
            f"{config.ADDIN_NAME}: toolbar panel {SETTINGS_PANEL_ID!r} was not found; settings command was not added to the UI",
            LogLevels.WarningLogLevel,
        )
        return

    settingsCommandControl = panel.controls.itemById(SETTINGS_COMMAND_ID)
    if settingsCommandControl is None:
        settingsCommandControl = panel.controls.addCommand(settingsCommandDefinition)


def deleteSettingsCommand() -> None:
    global settingsCommandDefinition
    global settingsCommandControl

    if settingsCommandControl is not None:
        settingsCommandControl.deleteMe()
        settingsCommandControl = None

    ui = app.userInterface if app else None
    if ui is None:
        return

    commandDefinition = ui.commandDefinitions.itemById(SETTINGS_COMMAND_ID)
    if commandDefinition is not None:
        commandDefinition.deleteMe()
    settingsCommandDefinition = None


def requestCameraUpdate() -> None:
    global cameraUpdateQueued

    with cameraStateLock:
        if cameraUpdateEvent is None or cameraUpdateQueued:
            return
        cameraUpdateQueued = True

    try:
        app.fireCustomEvent(CAMERA_UPDATE_EVENT_ID)
    except:
        with cameraStateLock:
            cameraUpdateQueued = False
        futil.handle_error(f"{config.ADDIN_NAME}: failed to fire camera update event")


def queueOrientation(nextOrientation: ViewOrientations | Literal[-1, -2]) -> None:
    global pendingOrientation

    if nextOrientation is None:
        return

    with cameraStateLock:
        pendingOrientation = nextOrientation

    requestCameraUpdate()


def processPendingCameraUpdate() -> None:
    global cameraUpdateQueued
    global pendingOrientation

    with cameraStateLock:
        cameraUpdateQueued = False
        nextOrientation = pendingOrientation
        pendingOrientation = None

    if nextOrientation is not None:
        orientCam(nextOrientation)

    moveCamForCurrentInput()


def hasActiveCameraInput() -> bool:
    with cameraStateLock:
        if pendingOrientation is not None:
            return True

    return any(axis != 0 for axis in getCurrentInputAxes())


def onCameraUpdate(args) -> None:
    processPendingCameraUpdate()


class PyJoystickThread(Thread):
    """
    pyjoystick's ThreadEventManager doesn't seem to work, so we're just running
    it in our own thread here.
    """

    def __init__(self, event: Event):
        Thread.__init__(self)
        self.stopped = event

    def handle_key_event(self, key: Key):
        """
        Assigns axis values into the global axisValues variable so the RenderThread
        can pick them up

        Args:
            key (Key): joystick keys
        """
        if key.keytype is KeyTypes.AXIS:
            maybeSetJoyconProfileFromRawEvent(axis=key.number, joystick=getattr(key, "joystick", None))
            axisValues[key.number] = key.get_proper_value()
            controlName = getKeyControlName(key)
            if controlName:
                axisValuesByControlName[controlName] = key.get_proper_value()
            requestCameraUpdate()
        elif key.keytype is KeyTypes.HAT:
            hatCam(key.get_hat_name())
        elif key.keytype is KeyTypes.BUTTON:
            maybeSetJoyconProfileFromRawEvent(button=key.number, joystick=getattr(key, "joystick", None))
            controlName = getKeyControlName(key)
            if key.value:
                pressedButtons.add(key.number)
                if controlName:
                    pressedControlNames.add(controlName)
                buttonCam(key.number, controlName)
            else:
                pressedButtons.discard(key.number)
                if controlName:
                    pressedControlNames.discard(controlName)
                requestCameraUpdate()

    def add(self, joy: Joystick):
        """
        pyjoystick doesn't work without this callback, so use it to detect profile.
        """
        setControllerProfileFromJoystick(joy)
        return

    def remove(self, joy: Joystick):
        """
        pyjoystick doesn't work without this callback.
        """
        return

    def run(self):
        try:
            run_event_loop = loadPyJoystickEventLoop()
            run_event_loop(
                add_joystick=self.add,
                remove_joystick=self.remove,
                handle_key_event=self.handle_key_event,
                alive=alive,
            )
        except:
            futil.handle_error(f"{config.ADDIN_NAME}: pyjoystick fallback failed to start. Install pygame or SDL2 and restart the add-in.", True)
            self.stopped.set()

class PyGameThread(Thread):
    def __init__(self, event: Event):
        Thread.__init__(self)
        self.stopped = event

    def run(self):
        try:
            self.pygameJoysticks = {}
            pygame.joystick.init()
            for index in range(pygame.joystick.get_count()):
                joy = pygame.joystick.Joystick(index)
                self.pygameJoysticks[joy.get_instance_id()] = joy
                setControllerProfileFromName(joy.get_name())
            while alive():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.stopped = True  

                    # Handle hotplugging, also initializes the joysticks when plugged in (otherwise we don't get the other events)
                    if event.type == pygame.JOYDEVICEADDED:
                        joy = pygame.joystick.Joystick(event.device_index)
                        self.pygameJoysticks[joy.get_instance_id()] = joy
                        setControllerProfileFromName(joy.get_name())

                    if event.type == pygame.JOYDEVICEREMOVED:
                        if event.instance_id in self.pygameJoysticks:
                            del self.pygameJoysticks[event.instance_id]

                    if event.type == pygame.JOYBUTTONDOWN:
                        maybeSetJoyconProfileFromRawEvent(button=event.button, joystick=self.pygameJoysticks.get(event.instance_id))
                        pressedButtons.add(event.button)
                        buttonCam(event.button)

                    if event.type == pygame.JOYBUTTONUP:
                        pressedButtons.discard(event.button)
                        requestCameraUpdate()

                    if event.type == pygame.JOYHATMOTION:
                        hatCam(pygameToHatName(event.value))

                    if event.type == pygame.JOYAXISMOTION:
                        maybeSetJoyconProfileFromRawEvent(axis=event.axis, joystick=self.pygameJoysticks.get(event.instance_id))
                        axisValues[event.axis] = event.value
                        requestCameraUpdate()
        except:
            pass

class RenderThread(Thread):
    """
    Handles translating the current axes into movements of the camera
    """

    def __init__(self, event: Event):
        super().__init__()
        self.stopped = event

    def run(self):
        while alive():
            try:
                if hasActiveCameraInput():
                    requestCameraUpdate()
                sleep(0.01)
            except:
                pass


def run(context):
    try:
        global stopFlag
        global axisValues
        global axisValuesByControlName
        global pressedButtons
        global pressedControlNames
        global controllerProfile
        global app
        global cameraUpdateEvent
        global cameraUpdateQueued
        global pendingOrientation
        app = Application.get()
        axisValues = {}
        axisValuesByControlName = {}
        pressedButtons = set()
        pressedControlNames = set()
        controllerProfile = CONTROLLER_PROFILE_DEFAULT
        stopFlag = Event()
        cameraUpdateQueued = False
        pendingOrientation = None
        loadSettings()
        createSettingsCommand()
        cameraUpdateEvent = app.registerCustomEvent(CAMERA_UPDATE_EVENT_ID)
        futil.add_handler(cameraUpdateEvent, onCameraUpdate, name=f"{config.ADDIN_NAME}_camera_update")

        if selectedJoystickBackend == BACKEND_PYGAME:
            pygame.init()
            pygameJoystickThread = PyGameThread(stopFlag)
            pygameJoystickThread.start()
        elif selectedJoystickBackend == BACKEND_PYJOYSTICK:
            joystickThread = PyJoystickThread(stopFlag)
            joystickThread.start()
        else:
            futil.handle_error(
                f"{config.ADDIN_NAME}: no joystick backend is available. Install pygame separately or install SDL2 for the vendored pyjoystick backend. Bootstrap error: {backendBootstrapError}",
                True,
            )
            return
        renderThread = RenderThread(stopFlag)
        renderThread.start()

    except:
        futil.handle_error("run")


def stop(context):
    try:
        global cameraUpdateEvent
        global cameraUpdateQueued
        global pendingOrientation
        # Remove all of the event handlers your app has created
        deleteSettingsCommand()
        futil.clear_handlers()
        stopFlag.set()
        cameraUpdateQueued = False
        pendingOrientation = None
        if cameraUpdateEvent is not None:
            app.unregisterCustomEvent(CAMERA_UPDATE_EVENT_ID)
            cameraUpdateEvent = None

    except:
        futil.handle_error("stop")


def deadZone(axis: float) -> float:
    """
    Check if an axis is inside the AXIS_DEADZONE and return 0 if so.
    """
    if (abs(axis)) < AXIS_DEADZONE:
        return 0
    return axis


def getAxisValue(axis: int, default: float = 0.0) -> float:
    return axisValues.get(axis, default)


def getAxisValueByControlName(controlNames: tuple[str, ...], default: float = 0.0) -> float:
    for controlName in controlNames:
        if controlName in axisValuesByControlName:
            return axisValuesByControlName[controlName]
    return default


def isPressed(button: int) -> bool:
    return button in pressedButtons


def isPressedControl(controlNames: tuple[str, ...]) -> bool:
    return any(controlName in pressedControlNames for controlName in controlNames)


def isJoyconRightController() -> bool:
    return controllerProfile == CONTROLLER_PROFILE_JOYCON_RIGHT


def getKeyControlName(key: Key) -> str | None:
    controlName = getattr(key, "controller_key_name", None)
    if not controlName:
        joystick = getattr(key, "joystick", None)
        controllerMapping = getattr(joystick, "controller_mapping", {}) or {}
        for mappedControlName, mappedKey in controllerMapping.items():
            if mappedKey.keytype == key.keytype and mappedKey.number == key.number:
                controlName = mappedControlName
                break
    if not controlName:
        return None
    try:
        return controlName.decode("utf-8").lower()
    except AttributeError:
        return str(controlName).lower()


def getJoystickGuidString(joy: Joystick) -> str:
    guid = getattr(joy, "guid", b"")
    try:
        return guid.decode("utf-8").lower()
    except AttributeError:
        return str(guid).lower()


def getJoystickControlNames(joy: Joystick) -> set[str]:
    keyMapping = getattr(joy, "key_mapping", {}) or {}
    return {str(controlName).lower() for controlName in keyMapping.values() if controlName}


def looksLikeJoyconRight(joy: Joystick | None, name: str | None) -> bool:
    lowerName = (name or "").lower()
    if any(keyword in lowerName for keyword in JOYCON_NAME_KEYWORDS):
        return True
    if joy is None:
        return False

    guid = getJoystickGuidString(joy)
    if any(keyword in guid for keyword in JOYCON_GUID_KEYWORDS):
        return True

    controlNames = getJoystickControlNames(joy)
    return {"a", "b", "x", "y", "leftx", "lefty"}.issubset(controlNames)


def getPygameGuidString(joy) -> str:
    if joy is None or not hasattr(joy, "get_guid"):
        return ""
    try:
        return str(joy.get_guid()).lower()
    except:
        return ""


def maybeSetJoyconProfileFromRawEvent(button: int | None = None, axis: int | None = None, joystick=None) -> None:
    global controllerProfile

    if controllerProfile == CONTROLLER_PROFILE_JOYCON_RIGHT:
        return

    if joystick is not None:
        try:
            if looksLikeJoyconRight(joystick, joystick.get_name() if hasattr(joystick, "get_name") else joystick.get_name()):
                controllerProfile = CONTROLLER_PROFILE_JOYCON_RIGHT
                logDetectedControllerProfile(getattr(joystick, "get_name", lambda: "")(), joystick, "Joy-Con (R)")
                return
        except:
            pass

        pygameGuid = getPygameGuidString(joystick)
        if any(keyword in pygameGuid for keyword in JOYCON_GUID_KEYWORDS):
            controllerProfile = CONTROLLER_PROFILE_JOYCON_RIGHT
            futil.log(f"{config.ADDIN_NAME}: detected Joy-Con (R) profile from pygame guid={pygameGuid!r}", LogLevels.InfoLogLevel)
            return

    if button is not None and button in JOYCON_RAW_SIGNATURE_BUTTONS:
        controllerProfile = CONTROLLER_PROFILE_JOYCON_RIGHT
        futil.log(
            f"{config.ADDIN_NAME}: detected Joy-Con (R) profile from raw button signature {button}",
            LogLevels.InfoLogLevel,
        )
        return

    if axis is not None and axis in (JOYCON_STICK_X_AXIS, JOYCON_STICK_Y_AXIS):
        try:
            lowerName = (getattr(joystick, "get_name", lambda: "")() or "").lower()
        except:
            lowerName = ""
        if lowerName == "":
            futil.log(
                f"{config.ADDIN_NAME}: observed unnamed controller axis {axis}; waiting for a Joy-Con signature button to confirm profile",
                LogLevels.InfoLogLevel,
            )


def logDetectedControllerProfile(name: str | None, joy: Joystick | None, profile: str) -> None:
    nameForLog = name or ""
    if joy is None:
        futil.log(f"{config.ADDIN_NAME}: detected {profile} controller profile from '{nameForLog}'")
        return

    guid = getJoystickGuidString(joy)
    controls = sorted(getJoystickControlNames(joy))
    futil.log(
        f"{config.ADDIN_NAME}: detected {profile} controller profile from name={nameForLog!r}, guid={guid!r}, controls={controls}",
        LogLevels.InfoLogLevel,
    )


def setControllerProfileFromJoystick(joy: Joystick):
    name = joy.get_name() if joy is not None else None
    setControllerProfileFromName(name, joy)


def setControllerProfileFromName(name: str, joy: Joystick | None = None):
    global controllerProfile
    if looksLikeJoyconRight(joy, name):
        controllerProfile = CONTROLLER_PROFILE_JOYCON_RIGHT
        logDetectedControllerProfile(name, joy, "Joy-Con (R)")
    elif controllerProfile != CONTROLLER_PROFILE_JOYCON_RIGHT:
        controllerProfile = CONTROLLER_PROFILE_DEFAULT
        logDetectedControllerProfile(name, joy, "default")


def getPanXAxis() -> float:
    """
    Get the axis for X panning. Configure this by updating PAN_X_AXIS
    """
    return deadZone(getAxisValue(PAN_X_AXIS))


def getPanYAxis() -> float:
    """
    Get the axis for Y panning. Configure this by updating PAN_Y_AXIS
    """
    return deadZone(getAxisValue(PAN_Y_AXIS)) * -1


def getRotateXAxis() -> float:
    """
    Get the axis for X rotation. Configure this by updating ROTATE_X_AXIS
    """
    return deadZone(getAxisValue(ROTATE_X_AXIS))


def getRotateYAxis() -> float:
    """
    Get the axis for Y rotation. Configure this by updating ROTATE_Y_AXIS
    """
    return deadZone(getAxisValue(ROTATE_Y_AXIS)) * -1


def getZoomAxis() -> float:
    """
    Get the axis for zoom. Configure this by updating ZOOM_POS_AXIS and ZOOM_NEG_AXIS
    """
    if not installedPygame:
        return deadZone(getAxisValue(ZOOM_POS_AXIS) - getAxisValue(ZOOM_NEG_AXIS))
    return deadZone(((getAxisValue(ZOOM_POS_AXIS) + 1)/2) - ((getAxisValue(ZOOM_NEG_AXIS) + 1)/2))


def applyJoyconResponseCurve(axis: float, exponent: float) -> float:
    if axis == 0:
        return 0.0
    sign = 1.0 if axis > 0 else -1.0
    return sign * pow(abs(axis), exponent)


def getJoyconModeAxes() -> tuple[float, float, float, float, float]:
    stickX = deadZone(getAxisValueByControlName(JOYCON_AXIS_NAME_X, getAxisValue(JOYCON_STICK_X_AXIS)))
    stickY = deadZone(getAxisValueByControlName(JOYCON_AXIS_NAME_Y, getAxisValue(JOYCON_STICK_Y_AXIS)))

    curvedPanX = applyJoyconResponseCurve(stickX, JOYCON_PAN_RESPONSE_EXPONENT)
    curvedPanY = applyJoyconResponseCurve(stickY, JOYCON_PAN_RESPONSE_EXPONENT)
    curvedRotateX = applyJoyconResponseCurve(stickX, JOYCON_ROTATION_HORIZONTAL_RESPONSE_EXPONENT)
    curvedRotateY = applyJoyconResponseCurve(stickY, JOYCON_ROTATION_VERTICAL_RESPONSE_EXPONENT)
    curvedZoom = applyJoyconResponseCurve(stickY, JOYCON_ZOOM_RESPONSE_EXPONENT)

    panX = 0.0
    panY = 0.0
    rotateX = 0.0
    rotateY = 0.0
    zoom = 0.0

    if isPressedControl(JOYCON_BUTTON_NAME_ZR) or isPressed(JOYCON_BUTTON_ZR):
        zoom = curvedZoom * -JOYCON_ZOOM_SENSITIVITY
    elif isPressedControl(JOYCON_BUTTON_NAME_R) or isPressed(JOYCON_BUTTON_R):
        panX = curvedPanX * JOYCON_PAN_SENSITIVITY
        panY = curvedPanY * JOYCON_PAN_SENSITIVITY
    else:
        rotateX = curvedRotateX * JOYCON_ROTATION_HORIZONTAL_SENSITIVITY
        rotateY = curvedRotateY * JOYCON_ROTATION_VERTICAL_SENSITIVITY

    return (panX, panY, rotateX, rotateY, zoom)


def getCurrentInputAxes() -> tuple[float, float, float, float, float]:
    if isJoyconRightController():
        return getJoyconModeAxes()
    return (getPanXAxis(), getPanYAxis(), getRotateXAxis(), getRotateYAxis(), getZoomAxis())


def moveCamForCurrentInput() -> None:
    panX, panY, rotateX, rotateY, zoom = getCurrentInputAxes()
    moveCamForAxes(panX, panY, rotateX, rotateY, zoom)


def hatCam(hatName: str):
    """
    Orient the camera for a given hat direction press
    """
    queueOrientation(HAT_TO_VIEW.get(hatName))


def buttonCam(button: int, controlName: str | None = None):
    """
    Orient the camera for a given button press
    """
    if isJoyconRightController():
        if controlName:
            queueOrientation(JOYCON_BUTTON_NAME_TO_VIEW.get(controlName))
            if controlName in JOYCON_BUTTON_NAME_TO_VIEW:
                return
        queueOrientation(JOYCON_BUTTON_TO_VIEW.get(button))
        return
    queueOrientation(BUTTON_TO_VIEW.get(button))


def orientCam(nextOrientation: ViewOrientations | Literal[-1, -2]) -> Camera :
    """
    Orient the activeViewport's camera to the chosen orientation

    Args:
        nextOrientation (int): Should be one of the ViewOrientations, or HOME_ORIENTATION to send the viewport to the configured home
    """
    if nextOrientation is None:
        return
    cam = app.activeViewport.camera
    cam.isSmoothTransition = False
    if nextOrientation == HOME_ORIENTATION:
        app.activeViewport.goHome()
        return
    elif nextOrientation == CONSTRAIN_ORIENTATION:
        upVector = getFrontVector().crossProduct(getLeftVector())
        cam.upVector = getConstrainedVector(upVector)
        cam.isSmoothTransition = True
    else:
        cam.viewOrientation = nextOrientation
        setCam(cam)

        orientationUpVector = getOrientationUpVector(nextOrientation)
        if orientationUpVector is None:
            return

        cam = app.activeViewport.camera
        cam.isSmoothTransition = False
        cam.upVector = orientationUpVector
        setCam(cam)
        return
    setCam(cam)


def moveCamForAxes(
    panXAxis: float = 0,
    panYAxis: float = 0,
    rotateXAxis: float = 0,
    rotateYAxis: float = 0,
    zoomAxis: float = 0,
) -> None:
    if (
        panXAxis == 0
        and panYAxis == 0
        and rotateXAxis == 0
        and rotateYAxis == 0
        and zoomAxis == 0
    ):
        return

    cam = app.activeViewport.camera
    initialViewExtents = cam.viewExtents
    referenceUpVector = getWorldUpVector()

    horizontalRotationMatrix = Matrix3D.create()
    verticalRotationMatrix = Matrix3D.create()
    target = cam.target.copy()
    eye = cam.eye.copy()

    frontVector = getFrontVector()
    leftVector = getOrbitLeftVector(frontVector, referenceUpVector, getLeftVector())
    upVector = getLeveledUpVector(frontVector, referenceUpVector, cam.upVector)

    horizontalRotationMatrix.setToRotation(
        axisToRadian(-rotateYAxis), leftVector, target
    )

    # failed attempts to get the correct upVector
    # upVector = newUpFromInvertedHorizontal(cam, horizontalRotationMatrix)
    # upVector = newUpFromCrossProduct(frontVector, leftVector)
    # upVector = newUpFromRotatedFrontVector(eye, target, leftVector)

    zoomVector = getZoomVector(zoomAxis, frontVector)
    verticalPanVector = getVerticalPanVector(scalePanAxis(panYAxis), upVector)
    horizontalPanVector = getHorizontalPanVector(scalePanAxis(panXAxis), leftVector)

    verticalRotationMatrix.setToRotation(axisToRadian(rotateXAxis), referenceUpVector, target)

    panVector = horizontalPanVector.copy()
    panVector.add(verticalPanVector)
    panVector.scaleBy(frontVector.length * PAN_ZOOM_COMPENSATION)

    # Translate target and eye to "pan"
    target.translateBy(panVector)
    eye.translateBy(panVector)

    if zoomVector.length > 0:
        eye.translateBy(zoomVector)
        newFrontVector = target.vectorTo(eye)
        if frontVector.length > CAMERA_VECTOR_EPSILON and newFrontVector.length > CAMERA_VECTOR_EPSILON:
            cam.viewExtents = initialViewExtents * (newFrontVector.length / frontVector.length)

    # Rotate only the eye
    eye.transformBy(horizontalRotationMatrix)
    eye.transformBy(verticalRotationMatrix)
    upVector = getLeveledUpVector(target.vectorTo(eye), referenceUpVector, upVector)

    # Apply changes
    cam.upVector = upVector
    cam.isSmoothTransition = False
    cam.target = target
    cam.eye = eye
    setCam(cam)


def getOrientationUpVector(
    orientation: ViewOrientations | Literal[-1, -2],
) -> Vector3D | None:
    if orientation in (
        ViewOrientations.FrontViewOrientation,
        ViewOrientations.BackViewOrientation,
        ViewOrientations.LeftViewOrientation,
        ViewOrientations.RightViewOrientation,
    ):
        return getWorldUpVector()
    if orientation in (
        ViewOrientations.TopViewOrientation,
        ViewOrientations.BottomViewOrientation,
    ):
        return Vector3D.create(0, 1, 0)
    return None


def newUpFromInvertedHorizontal(
    cam: Camera, horizontalRotationMatrix: Matrix3D
) -> Vector3D:
    """
    Doesn't work...

    Idea was to invert the horizontal rotation we used to move the eye and apply
    that to the previous upVector so it rotates in line
    """
    invertedRotation = horizontalRotationMatrix.copy()
    invertedRotation.invert()
    newUp = cam.upVector.copy()
    newUp.transformBy(invertedRotation)
    return newUp


def newUpFromRotatingHorizontal(
    cam: Camera, horizontalRotationMatrix: Matrix3D
) -> Vector3D:
    """
    Apply the horizontal rotation matrix to the previous upVector
    """
    newUp = cam.upVector.copy()
    newUp.transformBy(horizontalRotationMatrix)
    return newUp


def newUpFromCrossProduct(frontVector: Vector3D, leftVector: Vector3D) -> Vector3D:
    """
    Doesn't work...

    Idea was to get the cross product from the frontVector and leftVector (which should be the correct up vector?)
    """
    return frontVector.crossProduct(leftVector)


def newUpFromRotatedFrontVector(eye: Point3D, target: Point3D, leftVector: Vector3D):
    """
    Doesn't work...

    Idea was to take the current frontVector and rotate it 90 degress along the leftVector to create a proper upVector
    """
    newUp = eye.vectorTo(target)
    perpendicularMatrix = Matrix3D.create()
    perpendicularMatrix.setToRotation(radians(90), leftVector, eye)
    newUp.transformBy(perpendicularMatrix)


def alive():
    """
    Determine if the add-in is still alive

    Returns:
        bool: if the add-in is alive
    """
    if stopFlag.isSet():
        return False
    return True


def scalePanAxis(axis: float) -> float:
    """
    Scale a pan axis such that it accelerates making 0->1 a nice curve

    Args:
        axis (float): the pan axis as a float

    Returns:
        float: scaled axis to the curve
    """
    return pow(axis / 2 * 10, 3) * PAN_AXIS_SCALE


def axisToRadian(axis: float) -> float:
    """
    Get radians for a given axis

    Args:
        axis (float): the rotation axis as a float

    Returns:
        float: radians to rotate the camera
    """
    return pi * 2 * axis * ROTATION_AXIS_SCALE


def getZoomVector(zoomAxis: float, frontVector: Vector3D) -> Vector3D:
    """
    Get a vector for a zoom movement

    Args:
        zoomAxis (float): the zoom axis as a float
        frontVector (Vector3d): the vector between the eye and target from the camera

    Returns:
        Vector3D: A vector representing how far to move the eye towards the target
    """
    zoomVector = frontVector.copy()
    zoomVector.scaleBy(zoomAxis * ZOOM_SCALE)
    return zoomVector


def getVerticalPanVector(scale: float, upVector: Vector3D) -> Vector3D:
    """
    Get a vertical vector for a pan movement

    Args:
        scaledAxis (float): the vertical pan axis as a float
        upvector (Vector3d): the vector pointing up (expects a constrained vector)

    Returns:
        Vector3D: A vector representing how far to move the camera (eye and target) to pan up/down
    """
    vecV = constrain(upVector.copy())
    vecV.scaleBy(scale)
    return vecV


def getHorizontalPanVector(
    scaledAxis: float,
    leftVector: Vector3D,
) -> Vector3D:
    """
    Get a horizontal vector for a pan movement

    Args:
        scaledAxis (float): the horizontal pan axis as a float
        leftVector (Vector3d): the vector pointing left (expects a constrained vector)

    Returns:
        Vector3D: A vector representing how far to move the camera (eye and target) to pan left/right
    """
    vecH = constrain(leftVector.copy())
    vecH.scaleBy(scaledAxis)
    return vecH


def getFrontVector() -> Vector3D:
    cam = app.activeViewport.camera
    return cam.target.vectorTo(cam.eye)


def getLeftVector() -> Vector3D:
    """
    Get a vector that points left from the current camera view

    Args:
        upVector (Vector3D): vector pointing up from camera view
        target (Point3d): target for the camera view
        eye (Point3d): eye for the camera view

    Returns:
        Vector3D: A left pointing vector
    """
    cam = app.activeViewport.camera
    return cam.upVector.crossProduct(cam.target.vectorTo(cam.eye))


def getWorldUpVector() -> Vector3D:
    """
    Fusion uses a Z-up world, so keep orbit aligned to that stable axis.
    """
    return Vector3D.create(0, 0, 1)


def getOrbitLeftVector(
    frontVector: Vector3D,
    referenceUpVector: Vector3D,
    fallbackLeftVector: Vector3D,
) -> Vector3D:
    """
    Build a stable orbit-left vector from a reference up axis.
    """
    leftVector = referenceUpVector.crossProduct(frontVector)
    if leftVector.length <= CAMERA_VECTOR_EPSILON:
        return fallbackLeftVector.copy()
    return leftVector


def getLeveledUpVector(
    frontVector: Vector3D,
    referenceUpVector: Vector3D,
    fallbackUpVector: Vector3D,
) -> Vector3D:
    """
    Rebuild the camera up vector so orbit stays level relative to a stable reference axis.
    """
    if frontVector.length <= CAMERA_VECTOR_EPSILON:
        return fallbackUpVector.copy()

    normalizedFrontVector = frontVector.copy()
    normalizedFrontVector.scaleBy(1 / normalizedFrontVector.length)

    leveledUpVector = referenceUpVector.copy()
    projectionOntoFront = normalizedFrontVector.copy()
    projectionOntoFront.scaleBy(leveledUpVector.dotProduct(normalizedFrontVector))
    leveledUpVector.subtract(projectionOntoFront)

    if leveledUpVector.length <= CAMERA_VECTOR_EPSILON:
        leveledUpVector = fallbackUpVector.copy()
        projectionOntoFront = normalizedFrontVector.copy()
        projectionOntoFront.scaleBy(leveledUpVector.dotProduct(normalizedFrontVector))
        leveledUpVector.subtract(projectionOntoFront)
        if leveledUpVector.length <= CAMERA_VECTOR_EPSILON:
            return referenceUpVector.copy()

    if leveledUpVector.dotProduct(fallbackUpVector) < 0:
        leveledUpVector.scaleBy(-1)

    leveledUpVector.scaleBy(1 / leveledUpVector.length)
    return leveledUpVector


def constrain(vector: Vector3D) -> Vector3D:
    """
    Scale a vector such that the max absolute value of any component will be 1

    Args:
        vector (Vector3D): vector to scale

    Returns:
        Vector3D: A scaled vector
    """
    maxPos = max(vector.asArray())
    maxNeg = abs(min(vector.asArray()))
    maxAbs = max(maxNeg, maxPos)
    vector.scaleBy(1 / maxAbs)
    return vector


def getConstrainedVector(vector) -> Vector3D:
    """
    Get a pure primary direction that the vector is closest to
    """
    absX = abs(vector.x)
    absY = abs(vector.y)
    absZ = abs(vector.z)
    biggest = max(absX, absY, absZ)
    if (biggest == absX):
        if vector.x > 0:
            return Vector3D.create(1, 0, 0)
        return Vector3D.create(-1, 0, 0)
    elif (biggest == absY):
        if vector.y > 0:
            return Vector3D.create(0, 1, 0)
        return Vector3D.create(0, -1, 0)
    else:
        if vector.z > 0:
            return Vector3D.create(0, 0, 1)
        return Vector3D.create(0, 0, -1)


def setCam(cam: Camera):
    """
    Set the activeViewport to the given cam, makes sure to let F360 do it's work to update the view

    Args:
        cam (Camer): camera to set the viewport to
    """
    app.activeViewport.camera = cam
    doEvents()
    app.activeViewport.refresh()

def pygameToHatName(value):
    """
    Convert pygame hat tuple to hat name
    """
    match value:
        case (-1, 0): return Key.HAT_NAME_LEFT
        case (0, 1): return Key.HAT_NAME_UP
        case (1, 0): return Key.HAT_NAME_RIGHT
        case (0, -1): return Key.HAT_NAME_DOWN
