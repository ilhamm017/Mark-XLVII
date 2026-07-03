import time
import subprocess
import platform
import shutil

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

def find_and_focus_window(app_name: str) -> bool:
    if _SYSTEM == "Linux":
        try:
            if not shutil.which("wmctrl"):
                return False
            res = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3)
            if res.returncode != 0:
                return False
            app_name_lower = app_name.lower().strip()
            keyword_map = {
                "code": "visual studio code",
                "vscode": "visual studio code",
                "chrome": "chrome",
                "google-chrome": "chrome",
                "chromium-browser": "chromium",
                "firefox": "firefox",
                "spotify": "spotify",
                "terminal": "terminal",
                "whatsapp": "whatsapp",
                "telegram": "telegram",
                "discord": "discord",
            }
            search_keyword = keyword_map.get(app_name_lower, app_name_lower)
            for line in res.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    window_title = parts[3].lower()
                    if search_keyword in window_title:
                        window_id = parts[0]
                        subprocess.run(["wmctrl", "-i", "-a", window_id])
                        return True
        except Exception as e:
            print(f"[open_app] Linux focus window check failed: {e}")
        return False

    if _SYSTEM != "Windows":
        return False
    try:
        import win32gui
        import win32process
        import win32con
        import win32api
        import ctypes
        import psutil
        import time
    except ImportError:
        return False

    app_name_lower = app_name.lower().strip()
    
    # Map common app names to typical window title keywords
    keyword_map = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "msedge": "edge",
        "edge": "edge",
        "brave": "brave",
        "safari": "safari",
        "opera": "opera",
        "whatsapp": "whatsapp",
        "telegram": "telegram",
        "discord": "discord",
        "slack": "slack",
        "zoom": "zoom",
        "msteams": "teams",
        "teams": "teams",
        "spotify": "spotify",
        "code": "visual studio code",
        "vscode": "visual studio code",
        "notepad": "notepad",
        "notepad.exe": "notepad",
        "calc": "calculator",
        "calc.exe": "calculator",
        "calculator": "calculator",
        "mspaint": "paint",
        "paint": "paint",
        "wt": "terminal",
        "cmd": "command prompt",
        "cmd.exe": "command prompt",
        "powershell": "powershell",
        "powershell.exe": "powershell",
        "notion": "notion",
        "obsidian": "obsidian",
        "steam": "steam",
        "task manager": "task manager",
        "taskmgr.exe": "task manager",
        "settings": "settings",
        "ms-settings:": "settings",
        "systemsettings.exe": "settings",
    }
    
    search_keyword = keyword_map.get(app_name_lower, app_name_lower)
    
    # Enumerate all visible windows on the taskbar (same logic as taskbar_manager)
    hwnds = []
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True
                
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            # Filter criteria: must not be tool windows, must be main windows
            is_tool = (ex_style & win32con.WS_EX_TOOLWINDOW) != 0
            is_app = (ex_style & win32con.WS_EX_APPWINDOW) != 0
            has_parent = win32gui.GetParent(hwnd) != 0
            
            # Exclude overlays / HUD windows (like A.L.I.C.E itself)
            if "a.l.i.c.e" in title.lower() or "hud overlay" in title.lower():
                return True
                
            if not is_tool and (not has_parent or is_app):
                # Search keyword case-insensitive match on window title
                if search_keyword in title.lower():
                    hwnds.append(hwnd)
        return True
        
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        print(f"[open_app] EnumWindows failed: {e}")
        return False
        
    if not hwnds:
        return False
        
    # Get the first matching window and switch to it
    hwnd = hwnds[0]
    
    try:
        # 1. Restore if minimized
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.1)
            
        # 2. Try standard BringToForeground/SetForegroundWindow
        win32gui.SetForegroundWindow(hwnd)
        
        # 3. Force foreground using Win32 API attach thread input trick
        # This is needed on Windows 10/11 because of foreground locking policy
        fore_hwnd = win32gui.GetForegroundWindow()
        if fore_hwnd != hwnd:
            try:
                fore_thread = win32process.GetWindowThreadProcessId(fore_hwnd)[0]
                app_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
                
                if fore_thread != app_thread:
                    win32process.AttachThreadInput(fore_thread, app_thread, True)
                    if win32gui.SetForegroundWindow(hwnd):
                        win32gui.SetFocus(hwnd)
                        success = True
                    win32process.AttachThreadInput(fore_thread, app_thread, False)
            except Exception:
                pass

        # 7. BringWindowToTop & SetActiveWindow
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetActiveWindow(hwnd)
        except Exception:
            pass
            
        return True
            
    except Exception:
        pass
        
    return False

def _launch_windows(app_name: str) -> bool:

    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:
    name_lower = app_name.lower().strip()
    if name_lower in ["chrome", "google-chrome", "google-chrome-stable", "browser", "browseros", "chromium", "chromium-browser"]:
        for alt in ["chromium-browser", "google-chrome", "google-chrome-stable", "chromium", "firefox", "brave", "brave-browser"]:
            if shutil.which(alt):
                app_name = alt
                break

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    # Redirect web browser app launch to BrowserOS if it is running
    browseros_running = False
    if _SYSTEM == "Windows":
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:9200/health", timeout=1) as resp:
                browseros_running = (resp.status == 200)
        except Exception:
            pass

    app_name_lower = app_name.lower().strip()
    is_browser_app = app_name_lower in ["chrome", "google chrome", "browser", "browseros", "edge", "msedge", "firefox", "brave", "opera", "operagx"]

    if browseros_running and is_browser_app:
        print(f"[open_app] BrowserOS is running. Redirecting '{app_name}' request to BrowserOS focus.")
        try:
            from actions.browser_control import focus_browseros
            if focus_browseros():
                return "BrowserOS is already running. Focused BrowserOS window."
        except Exception as e:
            print(f"[open_app] Failed to focus BrowserOS: {e}")

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    if _SYSTEM in ["Windows", "Linux"]:
        try:
            if find_and_focus_window(normalized) or find_and_focus_window(app_name):
                return f"Switched to running instance of {app_name}."
        except Exception as e:
            print(f"[open_app] Focus window check failed: {e}")

    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"