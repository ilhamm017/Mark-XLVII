# 🤖 MARK XLVII (47)
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://www.youtube.com/watch?v=BhOsnGC_sAA)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Built with Gemini integration for maximum stability and performance, delivering zero subscriptions and total digital autonomy.

---

## ✨ Overview

MARK XLVII represents the pinnacle of the Jarvis series, evolving into a proactive, deeply integrated system. It bridges the gap between the operating system, real-time web intelligence, and hardware metrics. Through natural dialogue, Mark 47 monitors your hardware, prepares your day, and visualizes complex web data through an adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New in XLVII

- 🌅 **Morning Briefing Mode** — Automatically triggers once on first boot to read the time, pull local/global news, and check memory for your city to deliver a personalized weather update.
- 🎛️ **Audio-Visual System Monitor** — Background telemetry checks CPU, RAM, GPU, and temps every 10 seconds, delivering localized voice warnings with a 5-minute cooldown when thresholds are breached.
- 🔍 **Advanced Multi-Modal Search** — Overhauled web search featuring specific modes (`news`, `research`, `price`, `compare`, `search`) that prioritize Gemini Grounded Search with an automatic DuckDuckGo fallback.
- 🖼️ **Dynamic Content Panel** — A new scrollable display layer beneath the HUD that automatically expands to render high-density web results (over 120 characters) with active timestamps.
- 🗣️ **Silent Language Memory** — Instantly and silently captures your spoken language to save it under `identity/language`, ensuring all subsequent boots and briefings adapt to your dialect automatically.

---

## 🔱 Custom Fork Features: Honcho, Hermes & UI Enhancements

This repository is a heavily modified custom fork of MARK XLVII, evolving the original vocal assistant into a production-grade, multi-agent hybrid system. The architecture has been substantially refactored to support deep automation, persistent memory backends, and decoupled browser infrastructure.

### 🧠 Honcho Unified Memory Manager
- **Self-Hosted Backend**: Replaced local file-based JSON memory (`long_term.json`) with a self-hosted **Honcho server** running on a Linux (Armbian) server.
- **Persistent Peer Cards**: Implements live synchronization of user facts, project directories, and assistant conventions directly into Honcho's database, enabling seamless long-term context recall across restarts.

### 🤖 Hermes Agent Integration
- **Asynchronous Task Delegation**: Integrated a native `hermes_daemon.py` service (on port `8085`) acting as a background master-agent runner.
- **Interactive Clarification Bridge**: Implemented a file-based asynchronous feedback loop (`.clarify` / `.clarify_response`) under `.hermes/logs`. When Hermes needs user input during background tasks, ALICE dynamically prompts the user via the Gemini Live voice/chat stream and routes the response back to Hermes to continue the run.

### 🌐 BrowserOS Unified Web Automation
- **Unified Engine**: Completely phased out resource-heavy local browser processes and the buggy Firefox Marionette MCP debugger.
- **BrowserOS Integration**: All browser commands, scraping actions, and screenshots are routed to **BrowserOS** (Chrome MCP) running locally on port `9000`.
- **Heuristic Redirection**: Heuristic mappings automatically rewrite any legacy or implicit Firefox/Chromium calls into BrowserOS-compatible tool commands.

### 🎨 HUD UI & System Enhancements
- **UI Modifications**: Custom transparency overlay, tray context controls, and minimized HUD states (color status indicators without bulky bars).
- **Graceful Sound Stream Management**: The real-time sound stream has been optimized with strict error isolation. Microphone failures (e.g. Nakamichi N2 headset connections) are handled gracefully inside `_listen_audio` with a 15-second retry cooldown, preventing the Gemini Live session from crashing or entering infinite reconnect loops.
- **Session Latency Management**: Auto-rotation of Gemini sessions after 12 completed interaction turns to prevent token buildup and maintain sub-second voice responsiveness.

---

## ⚡ Quick Start

```bash
git clone [https://github.com/FatihMakes/Mark-XLVII.git](https://github.com/FatihMakes/Mark-XLVII.git)
cd Mark-XLVII
pip install -r requirements.txt
playwright install
python main.py
```

> ⚠️ **Installation Note:** To keep the repository lightweight, some OS-specific dependencies are not bundled in `requirements.txt`. If you run into a `ModuleNotFoundError`, simply install the missing package via `pip install <module_name>` for your specific system.

---

## 📋 Requirements

| Requirement | Details |
| --- | --- |
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world JARVIS-style assistant.
⭐ **Star the repository to support the journey to Mark 100.**

| Platform | Link |
| --- | --- |
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |

```

```