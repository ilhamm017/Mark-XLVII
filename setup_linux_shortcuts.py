#!/usr/bin/env python3
import subprocess
import sys
import re

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}", file=sys.stderr)
        return None

def main():
    print("🤖 Configuring global hotkeys for ALICE on Linux (GNOME Desktop)...")
    
    # 1. Disable the default Alt+Space window menu binding in GNOME to prevent conflicts
    print("-> Unbinding default Alt+Space window menu shortcut in GNOME...")
    run_cmd('gsettings set org.gnome.desktop.wm.keybindings activate-window-menu "[]"')
    
    # 2. Read existing custom keybindings list
    bindings_str = run_cmd('gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings')
    if bindings_str is None:
        print("❌ Could not read custom keybindings. Are you running inside a GNOME desktop session?", file=sys.stderr)
        sys.exit(1)
        
    # Parse list: e.g. "['/org/gnome/.../custom0/', '/org/gnome/.../custom1/']"
    bindings = []
    # Simple regex to extract paths inside single quotes
    matches = re.findall(r"'(.*?)'", bindings_str)
    if matches:
        bindings = list(matches)
        
    toggle_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/alice_toggle/'
    mute_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/alice_mute/'
    
    # Add paths if not already there
    changed = False
    if toggle_path not in bindings:
        bindings.append(toggle_path)
        changed = True
    if mute_path not in bindings:
        bindings.append(mute_path)
        changed = True
        
    if changed:
        # Format list back to string: "['path1', 'path2']"
        list_val = "[" + ", ".join(f"'{p}'" for p in bindings) + "]"
        run_cmd(f"gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \"{list_val}\"")
        
    # 3. Configure toggle shortcut
    print("-> Setting up 'Alt+Space' to toggle ALICE show/hide...")
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path} name "ALICE Toggle Show/Hide"')
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path} command "python3 -c \\\"import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b\'toggle\', (\'127.0.0.1\', 9107))\\\""')
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path} binding "<Alt>space"')
    
    # 4. Configure mute shortcut
    print("-> Setting up 'Alt+Scroll_Lock' to toggle ALICE mic mute...")
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path} name "ALICE Toggle Mic Mute"')
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path} command "python3 -c \\\"import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b\'mute\', (\'127.0.0.1\', 9107))\\\""')
    run_cmd(f'gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path} binding "<Alt>Scroll_Lock"')
    
    print("✅ Successfully configured global shortcuts!")
    print("Commands will send UDP signals to localhost:9107 which ALICE will process instantly.")

if __name__ == "__main__":
    main()
