# taskbar_manager.py
import platform
import subprocess

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
    # Fallback using wmctrl
    try:
        res = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            windows = []
            for line in res.stdout.splitlines():
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    title = parts[4].strip()
                    windows.append({"title": title, "process_name": "Unknown"})
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
    """Returns the title and process name of the active (foreground) window on the screen.
    If the active window is ALICE/Jarvis itself, it finds the window directly behind/underneath it.
    """
    import os
    current_pid = os.getpid()

    def is_alice_window(title: str, pid: int | None) -> bool:
        if pid == current_pid:
            return True
        if title:
            title_lower = title.lower()
            if "a.l.i.c.e" in title_lower or "jarvis" in title_lower or "mark-xlvii" in title_lower:
                return True
        return False

    if _OS == "Windows":
        try:
            import win32gui
            import win32process
            import psutil
            
            hwnd = win32gui.GetForegroundWindow()
            while hwnd:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).strip()
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    except Exception:
                        pid = None
                    
                    if not is_alice_window(title, pid) and title:
                        try:
                            proc = psutil.Process(pid)
                            proc_name = proc.name()
                        except Exception:
                            proc_name = "Unknown"
                        return f"Active Window: '{title}' (Process: '{proc_name}')"
                
                # Move to next window in Z-order (GW_HWNDNEXT = 2)
                hwnd = win32gui.GetWindow(hwnd, 2)
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
            env = os.environ.copy()
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
                
            # Get stacking order (bottom to top)
            res = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST_STACKING"], capture_output=True, text=True, env=env, timeout=3)
            if res.returncode == 0:
                line = res.stdout.strip()
                if "#" in line:
                    window_ids = [w.strip() for w in line.split("#")[1].split(",") if w.strip()]
                    window_ids.reverse() # Go from top (foreground) to bottom
                    
                    for wid_str in window_ids:
                        wid = int(wid_str, 16)
                        
                        # Get window title
                        name_res = subprocess.run(["xdotool", "getwindowname", str(wid)], capture_output=True, text=True, env=env, timeout=2)
                        title = name_res.stdout.strip() if name_res.returncode == 0 else ""
                        
                        # Get window PID
                        pid_res = subprocess.run(["xdotool", "getwindowpid", str(wid)], capture_output=True, text=True, env=env, timeout=2)
                        pid = int(pid_res.stdout.strip()) if pid_res.returncode == 0 and pid_res.stdout.strip().isdigit() else None
                        
                        if not title:
                            continue
                        title_lower = title.lower()
                        # Ignore system desktop components
                        if title_lower in ["desktop", "xfce4-panel", "panel", "polybar", "tint2", "gnome-shell"]:
                            continue
                            
                        if not is_alice_window(title, pid):
                            return f"Active Window: '{title}'"
            
            # Fallback if xprop failed
            res = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, env=env, timeout=3)
            if res.returncode == 0:
                return f"Active Window: '{res.stdout.strip()}'"
        except Exception:
            pass
            
    return "Could not determine active window."

