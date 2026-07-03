#!/usr/bin/env python3
import subprocess
import sys
import os

def run_args(args):
    try:
        res = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Don't print stack trace for benign remove errors
        if "-r" not in args:
            print(f"Error running command: {' '.join(args)}\nStdout: {e.stdout}\nStderr: {e.stderr}", file=sys.stderr)
        return None

def main():
    print("🤖 Configuring global hotkeys for ALICE on Linux...")
    
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if not desktop:
        ps_out = run_args(["ps", "aux"]) or ""
        if "xfce" in ps_out or "xfwm" in ps_out:
            desktop = "xfce"
        elif "gnome" in ps_out:
            desktop = "gnome"
        else:
            desktop = "unknown"
            
    print(f"-> Detected Desktop Environment: {desktop.upper()}")
    
    toggle_cmd = 'python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b\'toggle\', (\'127.0.0.1\', 9107))"'
    mute_cmd = 'python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b\'mute\', (\'127.0.0.1\', 9107))"'

    if "xfce" in desktop:
        print("-> Configuring XFCE shortcuts via xfconf-query...")
        
        # 1. Remove default Alt+Space popup menu binding in xfwm4
        print("   - Removing default Alt+Space window menu shortcut in XFWM4...")
        run_args(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/xfwm4/custom/<Alt>space", "-r"])
        
        # 2. Add Toggle shortcut to custom commands
        print("   - Binding Alt+Space to ALICE Toggle command...")
        run_args(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Alt>space", "-r"])
        run_args(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Alt>space", "-n", "-t", "string", "-s", toggle_cmd])
        
        # 3. Add Mute shortcut
        print("   - Binding Alt+Scroll Lock to ALICE Mute command...")
        run_args(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Alt>Scroll_Lock", "-r"])
        run_args(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", "/commands/custom/<Alt>Scroll_Lock", "-n", "-t", "string", "-s", mute_cmd])
        
        print("✅ XFCE Keyboard Shortcuts successfully configured!")
        
    elif "gnome" in desktop or "ubuntu" in desktop:
        print("-> Configuring GNOME shortcuts via gsettings...")
        
        # 1. Disable the default Alt+Space window menu binding in GNOME
        print("   - Unbinding default Alt+Space window menu shortcut in GNOME...")
        run_args(["gsettings", "set", "org.gnome.desktop.wm.keybindings", "activate-window-menu", "[]"])
        
        # 2. Read existing custom keybindings list
        bindings_str = run_args(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"])
        bindings = []
        if bindings_str:
            import re
            matches = re.findall(r"'(.*?)'", bindings_str)
            if matches:
                bindings = list(matches)
                
        toggle_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/alice_toggle/'
        mute_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/alice_mute/'
        
        changed = False
        if toggle_path not in bindings:
            bindings.append(toggle_path)
            changed = True
        if mute_path not in bindings:
            bindings.append(mute_path)
            changed = True
            
        if changed:
            list_val = "[" + ", ".join(f"'{p}'" for p in bindings) + "]"
            run_args(["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", list_val])
            
        # 3. Configure toggle shortcut
        print("   - Setting up 'Alt+Space' to toggle ALICE show/hide...")
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path}", "name", "ALICE Toggle Show/Hide"])
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path}", "command", toggle_cmd])
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{toggle_path}", "binding", "<Alt>space"])
        
        # 4. Configure mute shortcut
        print("   - Setting up 'Alt+Scroll_Lock' to toggle ALICE mic mute...")
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path}", "name", "ALICE Toggle Mic Mute"])
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path}", "command", mute_cmd])
        run_args(["gsettings", "set", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{mute_path}", "binding", "<Alt>Scroll_Lock"])
        
        print("✅ GNOME Keyboard Shortcuts successfully configured!")
    else:
        print("⚠️ Could not detect GNOME or XFCE. Setting up fallback local test trigger...")
        print("You can manually map Alt+Space to run:")
        print(f"  {toggle_cmd}")
        
    print("\nCommands will send UDP signals to localhost:9107 which ALICE will process instantly.")

if __name__ == "__main__":
    main()
