# taskbar_manager.py
import platform
import subprocess
from pathlib import Path

_OS = platform.system()

def get_visible_windows_windows() -> list[dict]:
    try:
        import win32gui
        import win32process
        import win32con
        import psutil
    except ImportError:
        return []

    windows = []
    
    # Keep track of seen titles/processes to avoid duplicate entries for the same app
    seen = set()

    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True

            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

            # Filter out tool windows
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return True

            # Filter out children windows
            if style & win32con.WS_CHILD:
                return True

            # Check for owner window
            owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
            if owner and win32gui.IsWindowVisible(owner):
                return True

            # Blacklist common background/system titles
            title_lower = title.lower()
            system_titles = [
                "program manager", "start", "settings", 
                "microsoft text input application", 
                "windows push notifications", 
                "nvidia share", "steam helper", "cortana"
            ]
            if any(sys_t in title_lower for sys_t in system_titles):
                return True

            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                proc_name = proc.name()
            except Exception:
                proc_name = "Unknown"

            # Skip listing ALICE itself to keep the focus clean
            if "mark-xlvii" in title_lower or "alice" in title_lower:
                return True

            # Filter out background server/helper processes
            if proc_name.lower() in ["explorer.exe", "rtkaudioservice.exe", "shellexperiencehost.exe"]:
                # Keep explorer only if it has a real folder path (e.g. not the main shell)
                if proc_name.lower() == "explorer.exe" and title in ["Start", "Program Manager"]:
                    return True

            windows.append({
                "hwnd": hwnd,
                "title": title,
                "process_name": proc_name
            })
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        print(f"[Taskbar] EnumWindows error: {e}")

    return windows

def get_visible_windows_macos() -> list[dict]:
    # Simple fallback using AppleScript to get open apps
    try:
        cmd = "osascript -e 'tell application \"System Events\" to get name of every process whose background only is false'"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            apps = [a.strip() for a in res.stdout.split(",") if a.strip()]
            return [{"title": app, "process_name": app} for app in apps]
    except Exception:
        pass
    return []

def get_visible_windows_linux() -> list[dict]:
    try:
        res = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            windows = []
            for line in res.stdout.splitlines():
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    win_id = parts[0]
                    pid = parts[2]
                    title = parts[4].strip()
                    proc_name = "Unknown"
                    if pid != "-1":
                        try:
                            comm_path = Path(f"/proc/{pid}/comm")
                            if comm_path.exists():
                                proc_name = comm_path.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass
                    windows.append({"title": title, "process_name": proc_name, "id": win_id, "pid": pid})
            return windows
    except Exception:
        pass
    return []

def list_taskbar_apps(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Lists visible active application windows on the taskbar."""
    if _OS == "Windows":
        windows = get_visible_windows_windows()
    elif _OS == "Darwin":
        windows = get_visible_windows_macos()
    else:
        windows = get_visible_windows_linux()

    if not windows:
        return "No active application windows found on the taskbar."

    lines = []
    for i, w in enumerate(windows, 1):
        proc_str = f" ({w['process_name']})" if w.get("process_name") else ""
        lines.append(f"{i}. {w['title']}{proc_str}")

    return "Aplikasi aktif di taskbar:\n" + "\n".join(lines)


def get_active_window(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Returns the title and process name of the active (foreground) window on the screen."""
    if _OS == "Windows":
        try:
            import win32gui
            import win32process
            import psutil
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd).strip()
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                except Exception:
                    proc_name = "Unknown"
                return f"Active Window: '{title}' (Process: '{proc_name}')"
            return "No foreground window detected."
        except Exception as e:
            return f"Error: {e}"
    elif _OS == "Darwin":
        try:
            cmd = "osascript -e 'tell application \"System Events\" to name of first application process whose frontmost is true'"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                return f"Active Application: '{res.stdout.strip()}'"
        except Exception as e:
            return f"Error: {e}"
    else:
        try:
            title_res = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=3)
            if title_res.returncode == 0:
                title = title_res.stdout.strip()
                pid_res = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"], capture_output=True, text=True, timeout=3)
                pid = pid_res.stdout.strip() if pid_res.returncode == 0 else "?"
                proc_name = "Unknown"
                if pid != "?":
                    try:
                        comm_path = Path(f"/proc/{pid}/comm")
                        if comm_path.exists():
                            proc_name = comm_path.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass
                return f"Active Window: '{title}' (Process: '{proc_name}', PID: {pid})"
        except Exception:
            pass
    return "Could not determine active window."

