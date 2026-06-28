"""Schedule 1 Auto Clicker: configurable Windows game-key automation."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from global_logger import get_log_file, get_logger, install_exception_hooks, setup_logging


APP_TITLE = "Schedule 1 Auto Clicker"
DEFAULT_INTERVAL_SECONDS = 3.0
DEFAULT_HOLD_MILLISECONDS = 60.0
DEFAULT_CLICK_KEY = "E"
DEFAULT_TOGGLE_KEY = "F1"
MIN_INTERVAL_SECONDS = 0.1
MAX_INTERVAL_SECONDS = 3600.0
MIN_HOLD_MILLISECONDS = 10.0
MAX_HOLD_MILLISECONDS = 2000.0
SMOKE_TEST_ARGUMENT = "--smoke-test"

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 1
MOD_NOREPEAT = 0x4000
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

LOGGER = get_logger("app")

KEY_SPECS: dict[str, tuple[int, bool]] = {
    "A": (0x1E, False), "B": (0x30, False), "C": (0x2E, False),
    "D": (0x20, False), "E": (0x12, False), "F": (0x21, False),
    "G": (0x22, False), "H": (0x23, False), "I": (0x17, False),
    "J": (0x24, False), "K": (0x25, False), "L": (0x26, False),
    "M": (0x32, False), "N": (0x31, False), "O": (0x18, False),
    "P": (0x19, False), "Q": (0x10, False), "R": (0x13, False),
    "S": (0x1F, False), "T": (0x14, False), "U": (0x16, False),
    "V": (0x2F, False), "W": (0x11, False), "X": (0x2D, False),
    "Y": (0x15, False), "Z": (0x2C, False),
    "0": (0x0B, False), "1": (0x02, False), "2": (0x03, False),
    "3": (0x04, False), "4": (0x05, False), "5": (0x06, False),
    "6": (0x07, False), "7": (0x08, False), "8": (0x09, False),
    "9": (0x0A, False),
    "Space": (0x39, False), "Enter": (0x1C, False),
    "Tab": (0x0F, False), "Escape": (0x01, False),
    "Up Arrow": (0x48, True), "Down Arrow": (0x50, True),
    "Left Arrow": (0x4B, True), "Right Arrow": (0x4D, True),
}

# F12 is reserved by Windows for debuggers.
TOGGLE_HOTKEYS: dict[str, int] = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A,
    "Insert": 0x2D, "Home": 0x24, "End": 0x23, "Pause": 0x13,
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class KeyboardInput(ctypes.Structure):
    _fields_ = (
        ("virtual_key", ctypes.wintypes.WORD),
        ("scan_code", ctypes.wintypes.WORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    )


class MouseInput(ctypes.Structure):
    _fields_ = (
        ("x", ctypes.wintypes.LONG),
        ("y", ctypes.wintypes.LONG),
        ("mouse_data", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    )


class HardwareInput(ctypes.Structure):
    _fields_ = (
        ("message", ctypes.wintypes.DWORD),
        ("parameter_low", ctypes.wintypes.WORD),
        ("parameter_high", ctypes.wintypes.WORD),
    )


class InputUnion(ctypes.Union):
    _fields_ = (
        ("keyboard", KeyboardInput),
        ("mouse", MouseInput),
        ("hardware", HardwareInput),
    )


class Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = (("type", ctypes.wintypes.DWORD), ("data", InputUnion))


user32.SendInput.argtypes = (
    ctypes.wintypes.UINT,
    ctypes.POINTER(Input),
    ctypes.c_int,
)
user32.SendInput.restype = ctypes.wintypes.UINT
user32.RegisterHotKey.argtypes = (
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
)
user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
user32.UnregisterHotKey.argtypes = (ctypes.wintypes.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL
user32.GetMessageW.argtypes = (
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
)
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = (
    ctypes.wintypes.DWORD,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def send_scan_code(scan_code: int, *, key_up: bool = False, extended: bool = False) -> None:
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP

    LOGGER.debug(
        "Sending scan code 0x%02X (%s, extended=%s)",
        scan_code,
        "up" if key_up else "down",
        extended,
    )
    keyboard_input = KeyboardInput(0, scan_code, flags, 0, 0)
    input_event = Input(INPUT_KEYBOARD, InputUnion(keyboard=keyboard_input))
    input_events = (Input * 1)(input_event)
    ctypes.set_last_error(0)
    if user32.SendInput(1, input_events, ctypes.sizeof(Input)) != 1:
        error_code = ctypes.get_last_error()
        LOGGER.error("SendInput failed; Windows error=%d", error_code)
        if error_code:
            raise ctypes.WinError(error_code)
        raise OSError("Windows blocked the simulated key press")


class AutoKeyPresser:
    def __init__(self, error_callback=None) -> None:
        self.error_callback = error_callback
        self._enabled = False
        self._interval_seconds = DEFAULT_INTERVAL_SECONDS
        self._hold_seconds = DEFAULT_HOLD_MILLISECONDS / 1000
        self._key_name = DEFAULT_CLICK_KEY
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="AutoKeyPresser",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("Auto-key worker started")

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def get_config(self) -> tuple[str, float, float]:
        with self._lock:
            return self._key_name, self._interval_seconds, self._hold_seconds

    def update_config(self, key_name: str, interval_seconds: float, hold_seconds: float) -> None:
        if key_name not in KEY_SPECS:
            raise ValueError(f"Unsupported click key: {key_name}")
        with self._lock:
            self._key_name = key_name
            self._interval_seconds = interval_seconds
            self._hold_seconds = hold_seconds
        self._wake.set()
        LOGGER.info(
            "Auto-key settings updated; key=%s interval=%.3fs hold=%.3fs",
            key_name,
            interval_seconds,
            hold_seconds,
        )

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            changed = self._enabled != enabled
            self._enabled = enabled
        self._wake.set()
        if changed:
            LOGGER.info("Auto-key presser %s", "enabled" if enabled else "disabled")
        return enabled

    def toggle(self) -> bool:
        return self.set_enabled(not self.enabled)

    @staticmethod
    def _press_key(key_name: str, hold_seconds: float) -> None:
        scan_code, extended = KEY_SPECS[key_name]
        LOGGER.debug("Beginning %s key press", key_name)
        send_scan_code(scan_code, extended=extended)
        try:
            time.sleep(hold_seconds)
        finally:
            send_scan_code(scan_code, key_up=True, extended=extended)
        LOGGER.info("%s key pressed successfully", key_name)

    def _run(self) -> None:
        LOGGER.debug("Auto-key worker entered its run loop")
        while not self._shutdown.is_set():
            with self._lock:
                enabled = self._enabled
                interval = self._interval_seconds

            if not enabled:
                self._wake.wait()
                self._wake.clear()
                continue

            interrupted = self._wake.wait(interval)
            self._wake.clear()
            if interrupted or self._shutdown.is_set():
                continue

            with self._lock:
                enabled = self._enabled
                key_name = self._key_name
                hold_seconds = self._hold_seconds
            if not enabled:
                continue

            try:
                self._press_key(key_name, hold_seconds)
            except Exception as error:
                LOGGER.exception("Key press failed; disabling auto-key presser")
                self.set_enabled(False)
                if self.error_callback:
                    self.error_callback(
                        f"Input failed: {error}. Try running as administrator."
                    )
        LOGGER.debug("Auto-key worker exited")

    def close(self) -> None:
        LOGGER.info("Stopping auto-key worker")
        self.set_enabled(False)
        self._shutdown.set()
        self._wake.set()
        self._thread.join(timeout=3)
        if self._thread.is_alive():
            LOGGER.warning("Auto-key worker did not stop within three seconds")


class GlobalHotkey:
    def __init__(self, virtual_key: int, callback, error_callback) -> None:
        self.virtual_key = virtual_key
        self.callback = callback
        self.error_callback = error_callback
        self.thread_id: int | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._listen,
            name=f"GlobalHotkey-{virtual_key}",
            daemon=True,
        )

    def start(self) -> None:
        LOGGER.info("Starting global hotkey listener for virtual key 0x%02X", self.virtual_key)
        self._thread.start()
        if not self._ready.wait(timeout=1):
            LOGGER.warning("Global hotkey listener was not ready within one second")

    def _listen(self) -> None:
        registered = False
        message = ctypes.wintypes.MSG()
        try:
            self.thread_id = kernel32.GetCurrentThreadId()
            self._ready.set()
            ctypes.set_last_error(0)
            if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, self.virtual_key):
                error = ctypes.get_last_error()
                LOGGER.error("Unable to register hotkey; Windows error=%d", error)
                self.error_callback("That toggle hotkey is already in use by another app.")
                return
            registered = True
            LOGGER.info("Global hotkey registered successfully")

            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    LOGGER.info("Global hotkey activated")
                    self.callback()
        except Exception as error:
            LOGGER.exception("Global hotkey listener failed")
            self.error_callback(f"Hotkey error: {error}")
        finally:
            self._ready.set()
            if registered and not user32.UnregisterHotKey(None, HOTKEY_ID):
                LOGGER.warning("Windows did not unregister the global hotkey")

    def close(self) -> None:
        LOGGER.info("Stopping global hotkey listener")
        if self.thread_id is not None:
            if not user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0):
                LOGGER.warning("Could not post WM_QUIT to hotkey listener")
        if self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._thread.is_alive():
            LOGGER.warning("Global hotkey listener did not stop within one second")


class AutoClickerUI:
    def __init__(self, root: tk.Tk) -> None:
        LOGGER.info("Initializing application UI")
        self.root = root
        self._closing = False
        self.logo_image: tk.PhotoImage | None = None
        self.hotkey: GlobalHotkey | None = None
        self.active_hotkey_name = DEFAULT_TOGGLE_KEY
        self.smoke_test_error: str | None = None
        self.ui_events: queue.SimpleQueue[tuple[str, str | None]] = queue.SimpleQueue()

        self.root.title(APP_TITLE)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.click_key_name = tk.StringVar(value=DEFAULT_CLICK_KEY)
        self.hotkey_name = tk.StringVar(value=DEFAULT_TOGGLE_KEY)
        self.interval_text = tk.StringVar(value=f"{DEFAULT_INTERVAL_SECONDS:g}")
        self.hold_text = tk.StringVar(value=f"{DEFAULT_HOLD_MILLISECONDS:g}")
        self.status = tk.StringVar(value="OFF")
        self.summary = tk.StringVar()
        self.help_text = tk.StringVar(value=f"Press {DEFAULT_TOGGLE_KEY} anywhere to enable")

        self.presser = AutoKeyPresser(
            error_callback=lambda text: self.ui_events.put(("error", text))
        )

        frame = ttk.Frame(root, padding=20)
        frame.grid()
        self._add_logo(frame)

        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 18, "bold")).grid(
            row=1, column=0, columnspan=2, pady=(4, 2)
        )
        ttk.Label(frame, textvariable=self.summary).grid(
            row=2, column=0, columnspan=2, pady=(0, 14)
        )
        ttk.Separator(frame).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        ttk.Label(frame, text="Key to press:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frame, textvariable=self.click_key_name, values=list(KEY_SPECS),
            width=14, state="readonly",
        ).grid(row=4, column=1, sticky="e", pady=4)

        ttk.Label(frame, text="Toggle hotkey:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frame, textvariable=self.hotkey_name, values=list(TOGGLE_HOTKEYS),
            width=14, state="readonly",
        ).grid(row=5, column=1, sticky="e", pady=4)

        ttk.Label(frame, text="Press every (seconds):").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, textvariable=self.interval_text, from_=MIN_INTERVAL_SECONDS,
            to=MAX_INTERVAL_SECONDS, increment=0.1, width=15,
        ).grid(row=6, column=1, sticky="e", pady=4)

        ttk.Label(frame, text="Hold key for (ms):").grid(row=7, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, textvariable=self.hold_text, from_=MIN_HOLD_MILLISECONDS,
            to=MAX_HOLD_MILLISECONDS, increment=10, width=15,
        ).grid(row=7, column=1, sticky="e", pady=4)

        ttk.Button(frame, text="Apply settings", command=self.apply_settings).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(14, 6)
        )
        self.toggle_button = ttk.Button(frame, text="Enable", command=self.toggle)
        self.toggle_button.grid(row=9, column=0, columnspan=2, sticky="ew", pady=6)

        self.status_label = tk.Label(
            frame, textvariable=self.status, font=("Segoe UI", 15, "bold"), fg="#b42318"
        )
        self.status_label.grid(row=10, column=0, columnspan=2, pady=(4, 0))
        ttk.Label(frame, textvariable=self.help_text, wraplength=360).grid(
            row=11, column=0, columnspan=2, pady=(5, 0)
        )

        self._install_hotkey(DEFAULT_TOGGLE_KEY)
        self._refresh()
        self.root.after(50, self._process_ui_events)
        LOGGER.info("Application UI initialized")

    def _add_logo(self, frame: ttk.Frame) -> None:
        logo_path = resource_path("assets", "schedule1_logo.png")
        try:
            original = tk.PhotoImage(file=str(logo_path))
            divisor = max(1, (original.width() + 359) // 360, (original.height() + 179) // 180)
            self.logo_image = original.subsample(divisor, divisor)
            ttk.Label(frame, image=self.logo_image).grid(row=0, column=0, columnspan=2)
            LOGGER.info("Loaded Schedule I logo from %s", logo_path)
        except (OSError, tk.TclError):
            LOGGER.exception("Unable to load Schedule I logo from %s", logo_path)

    def _install_hotkey(self, name: str) -> None:
        LOGGER.info("Installing %s as the toggle hotkey", name)
        self.hotkey = GlobalHotkey(
            TOGGLE_HOTKEYS[name],
            callback=lambda: self.ui_events.put(("toggle", None)),
            error_callback=lambda text: self.ui_events.put(("error", text)),
        )
        self.hotkey.start()
        self.active_hotkey_name = name

    def apply_settings(self) -> None:
        try:
            interval = float(self.interval_text.get())
            hold_ms = float(self.hold_text.get())
            if not MIN_INTERVAL_SECONDS <= interval <= MAX_INTERVAL_SECONDS:
                raise ValueError(
                    f"Interval must be between {MIN_INTERVAL_SECONDS:g} and "
                    f"{MAX_INTERVAL_SECONDS:g} seconds."
                )
            if not MIN_HOLD_MILLISECONDS <= hold_ms <= MAX_HOLD_MILLISECONDS:
                raise ValueError(
                    f"Hold duration must be between {MIN_HOLD_MILLISECONDS:g} and "
                    f"{MAX_HOLD_MILLISECONDS:g} milliseconds."
                )

            click_key = self.click_key_name.get()
            new_hotkey = self.hotkey_name.get()
            self.presser.update_config(click_key, interval, hold_ms / 1000)
            if new_hotkey != self.active_hotkey_name:
                if self.hotkey:
                    self.hotkey.close()
                self._install_hotkey(new_hotkey)

            self.interval_text.set(f"{interval:g}")
            self.hold_text.set(f"{hold_ms:g}")
            self._refresh()
            self.help_text.set("Settings applied successfully")
        except ValueError as error:
            LOGGER.warning("Invalid settings rejected: %s", error)
            messagebox.showerror(f"{APP_TITLE} - Invalid settings", str(error), parent=self.root)
        except Exception as error:
            LOGGER.exception("Unable to apply settings")
            messagebox.showerror(
                f"{APP_TITLE} - Error", f"Could not apply settings:\n\n{error}", parent=self.root
            )

    def _process_ui_events(self) -> None:
        try:
            while True:
                event, value = self.ui_events.get_nowait()
                if event == "toggle":
                    self.toggle()
                elif event == "error" and value:
                    LOGGER.error("Displaying application error: %s", value)
                    self._refresh()
                    self.help_text.set(value)
        except queue.Empty:
            pass
        except Exception:
            LOGGER.exception("Failed while processing queued UI events")
        if not self._closing:
            self.root.after(50, self._process_ui_events)

    def run_smoke_test(self) -> None:
        LOGGER.info("Running configurable-settings smoke test")
        try:
            self.click_key_name.set("W")
            self.hotkey_name.set("F9")
            self.interval_text.set("0.5")
            self.hold_text.set("20")
            self.apply_settings()
        except Exception as error:
            self.smoke_test_error = str(error)
            LOGGER.exception("Configurable-settings smoke test failed")
        finally:
            self.root.after(500, self.close)

    def toggle(self) -> None:
        self.presser.toggle()
        self._refresh()

    def _refresh(self) -> None:
        enabled = self.presser.enabled
        key_name, interval, hold_seconds = self.presser.get_config()
        self.summary.set(
            f"Casino helper | Press {key_name} every {interval:g}s | "
            f"Hold {hold_seconds * 1000:g}ms"
        )
        self.status.set("ON" if enabled else "OFF")
        self.status_label.configure(fg="#067647" if enabled else "#b42318")
        self.toggle_button.configure(text="Disable" if enabled else "Enable")
        action = "disable" if enabled else "enable"
        self.help_text.set(f"Press {self.active_hotkey_name} anywhere to {action}")

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        LOGGER.info("Application shutdown requested")
        try:
            self.presser.close()
            if self.hotkey:
                self.hotkey.close()
        except Exception:
            LOGGER.exception("Error while shutting down application components")
        finally:
            self.root.destroy()
            LOGGER.info("Application window destroyed")


def main() -> None:
    log_file = setup_logging()
    install_exception_hooks()
    LOGGER.info(
        "Starting %s; Python=%s frozen=%s log=%s",
        APP_TITLE,
        sys.version.split()[0],
        bool(getattr(sys, "frozen", False)),
        log_file or "unavailable",
    )

    root: tk.Tk | None = None
    try:
        root = tk.Tk()
        app = AutoClickerUI(root)
        if SMOKE_TEST_ARGUMENT in sys.argv:
            LOGGER.info("Smoke-test mode enabled")
            root.after(100, app.run_smoke_test)
        root.mainloop()
        if app.smoke_test_error:
            raise RuntimeError(f"Smoke test failed: {app.smoke_test_error}")
        LOGGER.info("Tk main loop ended normally")
    except Exception as error:
        LOGGER.exception("Fatal application error")
        try:
            messagebox.showerror(
                f"{APP_TITLE} - Error",
                f"The application encountered an error:\n\n{error}\n\n"
                f"Log file: {get_log_file() or 'unavailable'}",
                parent=root,
            )
        except Exception:
            LOGGER.exception("Unable to display the fatal-error dialog")
        raise
    finally:
        LOGGER.info("%s process is exiting", APP_TITLE)


if __name__ == "__main__":
    main()
