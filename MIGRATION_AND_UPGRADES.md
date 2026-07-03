# 🚀 ALICE (Mark-XLVII) Migration & Feature Upgrades Documentation

This document records the major changes, architectural migrations, and feature upgrades applied to the **ALICE (Mark-XLVII)** codebase in this session.

---

## 1. Gemini 3.1 Live API Migration
* **API Upgrades**: Migrated connection targets to `models/gemini-3.1-flash-live-preview`.
* **Method Updates**: 
  - Updated all client content-sending calls from the deprecated `send_client_content` to the new `send_realtime_input` API.
  - Wrapped microphone audio chunks directly in `audio=msg` and text inputs in `text=text`.
* **System Instruction Fix**: Resolved a critical SDK serialization bug where passing a string as the `system_instruction` parameter would incorrectly default the role to `"user"` (causing the model to ignore rules and talk like a standard assistant). The prompt is now passed as a `types.Content` object containing `parts` but omitting the `role` parameter entirely, forcing the API to process it as a clean system prompt.

---

## 2. Dynamic UI & Window Architecture
* **Split-Window Layout**:
  - **`HudWindow`**: Placed in the center of the screen as a frameless, translucent, click-through hologram orb. Fades dynamically from `0.04` opacity (idle/standby) up to `0.4` opacity (listening/speaking). Corner brackets and visualizer bars have been removed for a clean visual look.
  - **`MainWindow`**: Placed at the bottom-right corner of the desktop, handling text inputs, logs, and settings. It expands horizontally (slide-in from right-to-left, slide-out from left-to-right) via a global `Alt + Space` hotkey hook or System Tray clicks.
* **Interactive Mic Status**: Placed an interactive microphone icon status directly on the input bar (glowing Cyan when active, Red when muted) which toggles mute/unmute state instantly.

---

## 3. Sound-Responsive Visualizer (Hologram Pulser)
* **Real-time FFT & RMS Analysis**:
  - Implemented real-time Root Mean Square (RMS) calculation on the audio playback buffer (`_play_audio` in `main.py`) to measure speaker amplitude.
  - Implemented Fast Fourier Transform (FFT) on the playback stream to extract active frequency pitch (mapping typical speech range between 80Hz - 800Hz).
* **Smooth Canvas Modulations**: Mapped amplitude and frequency to modulate the HUD scale and tick marks. Applied Linear Interpolation (LERP) on the UI update loops to make the visual orb pulse smoothly in sync with Alice's voice.

---

## 4. Taskbar & Focus Window Overhaul
* **Taskbar App Listing**: Added the `list_taskbar_apps` tool using Windows `EnumWindows` to filter and return only visible, active GUI application windows currently on the taskbar, excluding system process noises.
* **Bypassing LockSetForegroundWindow**: To prevent Windows from blocking foreground transitions (which makes taskbar icons flash yellow without raising the window), we implemented a multi-layered force-focus bypass in `open_app.py` and `browser_control.py`:
  1. **UWP Window Checks**: Added class name verification (`ApplicationFrameWindow` check) for Windows modern apps (like Settings, Calculator) to always trigger `SW_RESTORE` since UWP apps hide their iconic minimized state from standard checks.
  2. **Alt-Tab Simulation**: Calls the undocumented `SwitchToThisWindow` API (incredibly robust for cross-process Z-order transitions).
  3. **Multi-layer Retries**: Falls back to direct `SetForegroundWindow`, keyboard virtual `Alt` key down/up presses, and `AttachThreadInput` hooks.
* **Process Fallback Matching**: Matches input queries (e.g. "buka chrome") against the window title OR the active process executable name (e.g. `chrome.exe`).

---

## 5. Active Window Context-Aware Assistance
* **`get_active_window` Tool**: Added a tool that retrieves the title and process of the foreground window currently in focus on the user's desktop.
* **Ambiguous Query Resolver**: Configured ALICE's system instructions (`core/prompt.txt`) to automatically run `get_active_window` if the user asks ambiguous questions (e.g. *"cara cut video gimana"*). This allows the model to know if they are using a video editor (like CapCut), code editor (VS Code), or browser, and formulate responses contextually. It can trigger `screen_process` (Vision) automatically if visual inspection of the app is required.

---

## 6. Local Network & File-System Safety Routing
* **Subnet Direct Route**: Rerouted memory synchronization and sub2api requests directly through the local Armbian VM IP `192.168.0.102:8080` instead of Tailscale, reducing latency.
* **Dynamic Safe Paths**: Whitelisted all active non-C partition drives (e.g. drive `X:\`, `E:\`) dynamically inside `_SAFE_ROOTS` by querying partitions using `psutil`. This allows ALICE to manage files in secondary project directories without triggering false-positive access denied restrictions.
* **IPv4 Localhost Enforcements**: Modified all local loopbacks from `localhost` to `127.0.0.1` to prevent DNS resolving timeouts under IPv6 stacks.

---

## 7. Idle Standby Mode
* Automatically disconnects the WebSocket Gemini Live session and suspends PyAudio microphone streams after 5 minutes of silence, saving token usage and CPU/RAM resources.
