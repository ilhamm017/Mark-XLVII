import time
import subprocess
import platform
import shutil
from pathlib import Path
from configparser import ConfigParser

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

# ── Desktop file database (Linux) ──────────────────────────────────────────
_DESKTOP_DB: list[dict] | None = None

_DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local" / "share" / "applications",
    Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
    Path("/var/lib/flatpak/exports/share/applications"),
]


def _scan_desktop_files(force: bool = False) -> list[dict]:
    global _DESKTOP_DB
    if _DESKTOP_DB is not None and not force:
        return _DESKTOP_DB

    db: list[dict] = []
    seen_names: set[str] = set()

    for d in _DESKTOP_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.name.endswith(".desktop"):
                continue
            try:
                cp = ConfigParser(strict=False, interpolation=None)
                cp.read_string(f.read_text(encoding="utf-8", errors="ignore"))
                entry = {}
                if cp.has_section("Desktop Entry"):
                    for k, v in cp.items("Desktop Entry"):
                        entry[k] = v

                name = (entry.get("name", "") or "").strip()
                exec_line = (entry.get("exec", "") or "").strip()
                if not name or not exec_line:
                    continue

                generic = (entry.get("genericname", "") or "").strip()
                keywords_raw = (entry.get("keywords", "") or "").strip()
                categories = (entry.get("categories", "") or "").strip()
                no_display = entry.get("nodisplay", "false").lower() in ("true", "1")

                if no_display or name.lower() in seen_names:
                    continue
                if name.lower().startswith("quit ") or name.lower().startswith("open a new"):
                    continue

                seen_names.add(name.lower())
                db.append({
                    "name": name,
                    "generic_name": generic,
                    "keywords": [k.strip() for k in keywords_raw.split(";") if k.strip()],
                    "categories": [c.strip() for c in categories.split(";") if c.strip()],
                    "exec": exec_line,
                    "desktop_file": f.stem,
                })
            except Exception:
                continue

    _DESKTOP_DB = db
    print(f"[open_app] Desktop DB: indexed {len(db)} applications")
    return db


def _match_desktop(query: str) -> dict | None:
    q = query.lower().strip()
    db = _scan_desktop_files()
    if not db:
        return None

    # 1) Exact match on Name
    for app in db:
        if app["name"].lower() == q:
            return app

    # 2) Exact match on desktop file stem
    for app in db:
        if app["desktop_file"].lower() == q:
            return app

    # 3) Exact match on GenericName
    for app in db:
        if app["generic_name"].lower() == q:
            return app

    # 4) query is a substring of Name (longer query = more weight)
    candidates = []
    for app in db:
        nl = app["name"].lower()
        if q in nl:
            candidates.append((len(nl) - len(q), app))
    if candidates:
        candidates.sort()
        return candidates[0][1]

    # 5) query is a substring of GenericName
    candidates = []
    for app in db:
        gl = app["generic_name"].lower()
        if gl and q in gl:
            candidates.append((len(gl) - len(q), app))
    if candidates:
        candidates.sort()
        return candidates[0][1]

    # 6) query matches a keyword
    for app in db:
        for kw in app["keywords"]:
            if q == kw.lower():
                return app

    # 7) substring match on keywords
    candidates = []
    for app in db:
        for kw in app["keywords"]:
            kl = kw.lower()
            if q in kl:
                candidates.append((len(kl) - len(q), app))
    if candidates:
        candidates.sort()
        return candidates[0][1]

    return None


def _launch_desktop(app: dict) -> bool:
    desktop_name = app["desktop_file"]
    # Prefer gtk-launch (uses .desktop file)
    if shutil.which("gtk-launch"):
        try:
            r = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass

    # Fallback: parse Exec line and run
    exec_line = app["exec"]
    # Remove field codes like %f, %F, %u, %U, %i, %c, %k
    import re
    exec_cleaned = re.sub(r"%[fFuUick]", "", exec_line).strip()
    import shlex
    try:
        cmd_list = shlex.split(exec_cleaned)
        subprocess.Popen(cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        return True
    except Exception:
        pass

    return False


def list_installed_apps(category: str = "", query: str = "") -> str:
    db = _scan_desktop_files()

    if not db:
        return "No installed applications found (could not read .desktop files)."

    filtered = db
    if category:
        cat_lower = category.lower()
        filtered = [
            a for a in filtered
            if any(cat_lower in c.lower() for c in a["categories"])
        ]
    if query:
        q = query.lower()
        filtered = [
            a for a in filtered
            if q in a["name"].lower()
            or q in a["generic_name"].lower()
            or any(q in k.lower() for k in a["keywords"])
        ]

    if not filtered:
        msg = "No applications"
        if category:
            msg += f" in category '{category}'"
        if query:
            msg += f" matching '{query}'"
        return msg + "."

    grouped: dict[str, list[str]] = {}
    for app in filtered:
        cat = (app["categories"] or ["Other"])[0]
        grouped.setdefault(cat, []).append(app["name"])

    lines = [f"Installed applications ({len(filtered)} found):"]
    for cat in sorted(grouped):
        apps = sorted(grouped[cat])
        lines.append(f"  [{cat}]")
        for name in apps:
            lines.append(f"    • {name}")

    if len(lines) > 100:
        lines = lines[:98]
        lines.append(f"  ... and {len(filtered) - 98} more.")

    return "\n".join(lines)

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

            # Build keyword from desktop DB + binary name
            search_keywords = [app_name_lower]
            matched = _match_desktop(app_name)
            if matched:
                search_keywords.append(matched["name"].lower())
                for kw in matched["keywords"]:
                    search_keywords.append(kw.lower())
                exec_name = matched["exec"].split("/")[-1].split()[0].lower().replace("%f", "").replace("%u", "").strip()
                if exec_name:
                    search_keywords.append(exec_name)

            # Also try xdotool if wmctrl fails
            has_xdotool = shutil.which("xdotool")

            for keyword in search_keywords:
                # Try wmctrl first
                for line in res.stdout.splitlines():
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        window_title = parts[3].lower()
                        if keyword and keyword in window_title:
                            window_id = parts[0]
                            subprocess.run(["wmctrl", "-i", "-a", window_id])
                            return True

                # Try xdotool search as fallback
                if has_xdotool:
                    try:
                        xd_res = subprocess.run(
                            ["xdotool", "search", "--name", f"--{keyword}",
                             "--class", f"--{keyword}", "--limit", "1"],
                            capture_output=True, text=True, timeout=3
                        )
                        if xd_res.returncode == 0 and xd_res.stdout.strip():
                            wid = xd_res.stdout.strip().split()[0]
                            subprocess.run(["xdotool", "windowactivate", wid])
                            return True
                    except Exception:
                        pass

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

def _scan_windows_apps() -> dict[str, Path]:
    import os
    apps = {}
    paths = []
    
    # Common Start Menu
    program_data = os.environ.get("ProgramData", "C:\\ProgramData")
    paths.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu")
    
    # User Start Menu
    app_data = os.environ.get("APPDATA")
    if app_data:
        paths.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu")
        
    for base_path in paths:
        if not base_path.is_dir():
            continue
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith(".lnk") or file.lower().endswith(".url"):
                    name = Path(file).stem
                    full_path = Path(root) / file
                    apps[name.lower()] = full_path
    return apps

def _match_windows_lnk(app_name: str) -> Path | None:
    apps = _scan_windows_apps()
    q = app_name.lower().strip()
    
    # 1) Exact match
    if q in apps:
        return apps[q]
        
    # 2) Substring match
    candidates = []
    for name, path in apps.items():
        if q in name:
            candidates.append((len(name) - len(q), path))
    if candidates:
        candidates.sort()
        return candidates[0][1]
        
    return None

def _launch_windows(app_name: str) -> bool:
    import os

    # 1) Try standard PATH binary lookup
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # 2) Try Start Menu shortcut matching (.lnk / .url files)
    try:
        lnk_path = _match_windows_lnk(app_name)
        if lnk_path:
            print(f"[open_app] Found Windows Start Menu shortcut: {lnk_path}")
            os.startfile(lnk_path)
            time.sleep(1.5)
            return True
    except Exception as e:
        print(f"[open_app] Start Menu shortcut launch failed: {e}")

    # 3) Try protocol schemes (e.g. ms-settings:)
    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True, creationflags=0x08000000)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # 4) Last resort: Try pyautogui but ONLY if it is a known common alias
    known_aliases = [
        "chrome", "google chrome", "firefox", "edge", "msedge", "brave", "safari", "opera",
        "whatsapp", "telegram", "discord", "slack", "zoom", "teams", "skype", "signal",
        "spotify", "vlc", "netflix", "vscode", "visual studio code", "code", "terminal",
        "cmd", "powershell", "postman", "git", "figma", "blender", "word", "excel",
        "powerpoint", "libreoffice", "notepad", "textedit", "explorer", "file explorer",
        "finder", "task manager", "settings", "calculator", "paint", "instagram", "tiktok",
        "notion", "obsidian", "capcut", "steam", "epic"
    ]
    if app_name.lower().strip() in known_aliases:
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
    import os
    name_lower = app_name.lower().strip()

    # ── 1) Search desktop database first ────────────────────────────────────
    matched = _match_desktop(app_name)
    if matched:
        print(f"[open_app] Found in desktop DB: '{matched['name']}' ({matched['desktop_file']}.desktop)")
        if _launch_desktop(matched):
            print(f"[open_app] ✅ Launched via desktop: {matched['name']}")
            return True
        else:
            print(f"[open_app] Desktop launch failed for '{matched['name']}', falling back...")

    # ── 2) Browser alias resolution ─────────────────────────────────────────
    if name_lower in ["chrome", "google-chrome", "google-chrome-stable", "browser", "chromium", "chromium-browser"]:
        for alt in ["chromium-browser", "google-chrome", "google-chrome-stable", "chromium", "firefox", "brave", "brave-browser"]:
            path = shutil.which(alt)
            if path:
                if path in ["/usr/bin/chromium-browser", "/usr/bin/chromium"] and not os.path.exists("/snap/bin/chromium"):
                    continue
                if path == "/usr/bin/firefox" and not os.path.exists("/snap/bin/firefox"):
                    continue
                app_name = alt
                break

    # ── 3) Binary lookup ────────────────────────────────────────────────────
    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        if binary in ["/usr/bin/chromium-browser", "/usr/bin/chromium"] and not os.path.exists("/snap/bin/chromium"):
            binary = None
        elif binary == "/usr/bin/firefox" and not os.path.exists("/snap/bin/firefox"):
            binary = None

    if binary:
        try:
            p = subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.5)
            if p.poll() is not None and p.returncode != 0:
                print(f"[open_app] ❌ Binary {binary} exited immediately with code {p.returncode}")
            else:
                return True
        except Exception as e:
            print(f"[open_app] ❌ Failed to execute {binary}: {e}")
            pass

    # ── 4) xdg-open fallback ───────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    # ── 5) gtk-launch with various name guesses ────────────────────────────
    if matched:
        guesses = [matched["desktop_file"]]
    else:
        guesses = [
            app_name.lower(),
            app_name.lower().replace(" ", "-"),
            app_name.lower().replace(" ", ""),
        ]
    for desktop_name in guesses:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                time.sleep(0.5)
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

    # Specialized handler for BrowserOS to prevent duplicate launches and handle health check sync
    app_name_lower = app_name.lower().strip()
    if app_name_lower == "browseros":
        try:
            from actions.browser_control import _is_browseros_running, focus_browseros, launch_browseros
            if _is_browseros_running():
                if focus_browseros():
                    return "BrowserOS is already running. Focused BrowserOS window."
                return "BrowserOS is already running."
            if launch_browseros():
                time.sleep(1.0)
                if focus_browseros():
                    return "Launched and focused BrowserOS."
                return "Launched BrowserOS."
            return "Failed to launch BrowserOS."
        except Exception as e:
            print(f"[open_app] BrowserOS specialized handler error: {e}")

    # Redirect browser app launches to BrowserOS (launch if needed)
    app_name_lower = app_name.lower().strip()

    if app_name_lower in ["firefox", "mozilla firefox"]:
        # Specialized handler for Firefox to write user.js and launch with --marionette
        try:
            # 1. Write user.js to Firefox profiles to ensure marionette port is 6000
            import os
            import platform
            from pathlib import Path
            
            if platform.system() == "Windows":
                appdata = os.environ.get("APPDATA", "")
                firefox_base = Path(appdata) / "Mozilla" / "Firefox"
                profiles_ini = firefox_base / "profiles.ini"
                if profiles_ini.exists():
                    import configparser
                    config = configparser.ConfigParser()
                    config.read(profiles_ini)
                    default_path = None
                    
                    for section in config.sections():
                        if section.startswith("Profile"):
                            is_default = config.get(section, "Default", fallback="0") == "1"
                            name = config.get(section, "Name", fallback="").lower()
                            path = config.get(section, "Path", fallback="")
                            is_relative = config.get(section, "IsRelative", fallback="1") == "1"
                            
                            if is_default or "release" in name:
                                full_path = firefox_base / path if is_relative else Path(path)
                                if full_path.exists():
                                    default_path = full_path
                                    if "release" in name:
                                        break
                                        
                    if default_path:
                        user_js = default_path / "user.js"
                        content = 'user_pref("marionette.port", 6000);\nuser_pref("marionette.enabled", true);\n'
                        user_js.write_text(content, encoding="utf-8")
                        print(f"[open_app] Wrote user.js to {user_js}")
            
            # 2. Launch Firefox with --marionette
            firefox_exe = None
            if platform.system() == "Windows":
                paths = [
                    Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Mozilla Firefox" / "firefox.exe",
                    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Mozilla Firefox" / "firefox.exe",
                ]
                for p in paths:
                    if p.exists():
                        firefox_exe = str(p)
                        break
                if not firefox_exe:
                    import winreg
                    try:
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe")
                        firefox_exe = winreg.QueryValue(k, None).strip().strip('"')
                        winreg.CloseKey(k)
                    except Exception:
                        pass
                        
            if not firefox_exe:
                firefox_exe = shutil.which("firefox")
                
            if firefox_exe and Path(firefox_exe).exists():
                print(f"[open_app] Launching Firefox with marionette: {firefox_exe}")
                import subprocess
                subprocess.Popen([firefox_exe, "--marionette"])
                time.sleep(1.5)
                return "Launched Firefox with Marionette enabled on port 6000."
                
        except Exception as e:
            print(f"[open_app] Failed to configure/launch Firefox with marionette: {e}")

    is_browser_app = app_name_lower in ["chrome", "google chrome", "browser", "browseros", "edge", "msedge", "brave", "opera", "operagx"]

    if is_browser_app:
        try:
            from actions.browser_control import _is_browseros_running, focus_browseros, launch_browseros
            if _is_browseros_running():
                if focus_browseros():
                    return "BrowserOS is already running. Focused BrowserOS window."
                return "BrowserOS is already running."
            if launch_browseros():
                time.sleep(1.0)
                if focus_browseros():
                    return "Launched and focused BrowserOS."
                return "Launched BrowserOS."
            print(f"[open_app] Failed to launch BrowserOS, falling through to normal launch for '{app_name}'.")
        except Exception as e:
            print(f"[open_app] BrowserOS redirect error: {e}")

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