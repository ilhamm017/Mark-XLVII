#system_control.py
import os
import sys
import subprocess
import platform
import json
import re
from pathlib import Path

_OS = platform.system() # "Windows", "Darwin", "Linux"

def execute_command(command: str) -> str:
    """Runs a terminal/shell command locally with a 30s timeout."""
    try:
        if _OS == "Windows":
            # Use PowerShell for more powerful capabilities on Windows
            shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]
            
        res = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="ignore"
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        
        result = []
        if out:
            result.append(out)
        if err:
            result.append(f"[Error Output]\n{err}")
            
        if not result:
            return "Command executed successfully (no output)."
            
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return "Command execution timed out after 30 seconds."
    except Exception as e:
        return f"Failed to execute command: {e}"

def manage_process(action: str, pid: int = None, name: str = None) -> str:
    """Lists or terminates system processes."""
    action = action.lower().strip()
    try:
        import psutil
        _PSUTIL = True
    except ImportError:
        _PSUTIL = False

    if action == "list":
        if _PSUTIL:
            try:
                processes = []
                for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        info = p.info
                        processes.append(info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                # Sort by memory usage descending and get top 30
                processes.sort(key=lambda x: x.get('memory_percent') or 0, reverse=True)
                lines = [f"{'PID':>8}  {'Process Name':<30}  {'CPU %':>8}  {'MEM %':>8}"]
                for p in processes[:30]:
                    cpu = f"{p['cpu_percent'] or 0.0:.1f}"
                    mem = f"{p['memory_percent'] or 0.0:.1f}"
                    lines.append(f"{p['pid']:>8}  {p['name']:<30}  {cpu:>8}  {mem:>8}")
                return "\n".join(lines)
            except Exception as e:
                return f"Failed listing processes using psutil: {e}"
        else:
            # Fallback to tasklist (Windows) or ps (Linux/Mac)
            if _OS == "Windows":
                return execute_command("tasklist | Select-Object -First 35")
            else:
                return execute_command("ps aux | head -n 35")
                
    elif action == "kill":
        if not pid and not name:
            return "Error: Either 'pid' or 'name' must be specified to kill a process."
        if _PSUTIL:
            try:
                killed_count = 0
                if pid:
                    p = psutil.Process(pid)
                    p.terminate()
                    return f"Process with PID {pid} ({p.name()}) terminated."
                elif name:
                    for p in psutil.process_iter(['pid', 'name']):
                        if name.lower() in p.info['name'].lower():
                            p.terminate()
                            killed_count += 1
                    if killed_count > 0:
                        return f"Terminated {killed_count} processes matching '{name}'."
                    else:
                        return f"No process found matching name '{name}'."
            except Exception as e:
                return f"Failed to kill process using psutil: {e}"
        else:
            # Fallback
            if _OS == "Windows":
                if pid:
                    return execute_command(f"taskkill /F /PID {pid}")
                else:
                    return execute_command(f"taskkill /F /IM {name}*")
            else:
                if pid:
                    return execute_command(f"kill -9 {pid}")
                else:
                    return execute_command(f"pkill -f {name}")
    else:
        return f"Unknown action: '{action}'"

def workspace_info(action: str, path: str = None) -> str:
    """Inspects the current project workspace or repository status."""
    action = action.lower().strip()
    target_path = Path(path).expanduser().resolve() if path else Path.cwd()
    
    if action == "git_status":
        # Find git root
        curr = target_path
        git_root = None
        for _ in range(10): # Max 10 directories up
            if (curr / ".git").exists():
                git_root = curr
                break
            if curr.parent == curr:
                break
            curr = curr.parent
            
        if not git_root:
            return f"Not a git repository: {target_path}"
            
        # Run git status & git log
        status = execute_command(f"cd '{git_root}' && git status")
        log = execute_command(f"cd '{git_root}' && git log -n 3 --oneline")
        return f"Git Repository Root: {git_root}\n\n[Status]\n{status}\n\n[Recent Commits]\n{log}"
    elif action == "list_files":
        # Simply list top files in the workspace
        if _OS == "Windows":
            return execute_command(f"Get-ChildItem '{target_path}' | Select-Object Name, Length, LastWriteTime | Format-Table")
        else:
            return execute_command(f"ls -lh '{target_path}'")
    else:
        return f"Unknown action: '{action}'"

def show_notification(title: str, message: str) -> str:
    """Triggers a native desktop notification."""
    title_escaped = title.replace('"', '\\"')
    msg_escaped = message.replace('"', '\\"')
    
    if _OS == "Windows":
        # Use PowerShell NotifyIcon balloon tip
        ps_script = f"""
        [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");
        $objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon;
        $objNotifyIcon.Icon = [System.Drawing.SystemIcons]::Information;
        $objNotifyIcon.BalloonTipIcon = "Info";
        $objNotifyIcon.BalloonTipText = "{msg_escaped}";
        $objNotifyIcon.BalloonTipTitle = "{title_escaped}";
        $objNotifyIcon.Visible = $True;
        $objNotifyIcon.ShowBalloonTip(10000);
        """
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return "Notification sent to Windows System Tray."
    elif _OS == "Linux":
        try:
            subprocess.run(["notify-send", title, message], capture_output=True, check=True)
            return "Notification sent using notify-send."
        except Exception as e:
            return f"Failed to send notification via notify-send: {e}"
    elif _OS == "Darwin":
        try:
            applescript = f'display notification "{msg_escaped}" with title "{title_escaped}"'
            subprocess.run(["osascript", "-e", applescript], capture_output=True, check=True)
            return "Notification sent using AppleScript."
        except Exception as e:
            return f"Failed to send AppleScript notification: {e}"
    return "Unsupported OS for notifications."

def manage_packages(action: str, manager: str, package_name: str) -> str:
    """Installs, uninstalls, or lists packages using standard package managers."""
    action = action.lower().strip()
    manager = manager.lower().strip()
    pkg = package_name.strip()
    
    if manager == "pip":
        if action == "install":
            cmd = f"pip install --upgrade {pkg}"
        elif action == "uninstall":
            cmd = f"pip uninstall -y {pkg}"
        elif action == "list":
            cmd = "pip list"
        else:
            return f"Unknown package action: '{action}'"
            
    elif manager == "npm":
        if action == "install":
            cmd = f"npm install -g {pkg}"
        elif action == "uninstall":
            cmd = f"npm uninstall -g {pkg}"
        elif action == "list":
            cmd = "npm list -g --depth=0"
        else:
            return f"Unknown package action: '{action}'"
            
    elif manager == "winget":
        if _OS != "Windows":
            return "winget is only supported on Windows."
        if action == "install":
            cmd = f"winget install --quiet --accept-package-agreements --accept-source-agreements {pkg}"
        elif action == "uninstall":
            cmd = f"winget uninstall --quiet {pkg}"
        elif action == "list":
            cmd = "winget list"
        else:
            return f"Unknown package action: '{action}'"
            
    elif manager == "apt":
        if _OS != "Linux":
            return "apt-get is only supported on Linux."
        if action == "install":
            cmd = f"sudo apt-get install -y {pkg}"
        elif action == "uninstall":
            cmd = f"sudo apt-get remove -y {pkg}"
        elif action == "list":
            cmd = f"dpkg -l | grep {pkg}"
        else:
            return f"Unknown package action: '{action}'"
            
    else:
        return f"Unknown package manager: '{manager}'"
        
    return execute_command(cmd)

def network_diagnostics(action: str, target: str = None) -> str:
    """Runs network connectivity tests, port scanning, or lists interfaces."""
    action = action.lower().strip()
    
    if action == "interfaces":
        if _OS == "Windows":
            return execute_command("Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress, AddressFamily | Format-Table")
        else:
            return execute_command("ip addr || ifconfig")
            
    elif action == "ping":
        if not target:
            return "Error: A target hostname/IP must be provided to ping."
        if _OS == "Windows":
            return execute_command(f"ping -n 4 {target}")
        else:
            return execute_command(f"ping -c 4 {target}")
            
    elif action == "ports":
        if _OS == "Windows":
            return execute_command("Get-NetTCPConnection | Where-Object State -eq 'Listen' | Select-Object LocalAddress, LocalPort | Format-Table")
        else:
            return execute_command("ss -tulpn || netstat -tulpn || netstat -an")
            
    else:
        return f"Unknown network action: '{action}'"

def system_control(parameters: dict = None, player=None) -> str:
    """Dispatcher function for system control actions."""
    params = parameters or {}
    tool = params.get("tool", "").lower().strip()
    
    if player:
        player.write_log(f"[system_control] Running tool: {tool}")
        
    try:
        if tool == "execute_command":
            return execute_command(params.get("command", ""))
            
        elif tool == "manage_process":
            pid_val = params.get("pid")
            pid = int(pid_val) if pid_val is not None else None
            return manage_process(
                action=params.get("action", "list"),
                pid=pid,
                name=params.get("name")
            )
            
        elif tool == "workspace_info":
            return workspace_info(
                action=params.get("action", "git_status"),
                path=params.get("path")
            )
            
        elif tool == "show_notification":
            return show_notification(
                title=params.get("title", "Alice Alert"),
                message=params.get("message", "")
            )
            
        elif tool == "manage_packages":
            return manage_packages(
                action=params.get("action", "list"),
                manager=params.get("manager", "pip"),
                package_name=params.get("package_name", "")
            )
            
        elif tool == "network_diagnostics":
            return network_diagnostics(
                action=params.get("action", "interfaces"),
                target=params.get("target")
            )
            
        else:
            return f"Unknown system control tool: '{tool}'"
    except Exception as e:
        return f"System control error ({tool}): {e}"
