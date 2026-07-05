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

## 🤖 Hermes Agent & BrowserOS Integration

This modified fork of MARK XLVII is integrated with **Hermes Agent** and **BrowserOS** to enable advanced autonomous operations and robust web automation:

- **Hermes Task Delegation**: Includes `hermes_daemon.py` on port `8085` to run autonomous coding and system tasks. Features a file-based async bridge (`.clarify` / `.clarify_response`) allowing ALICE to capture Hermes clarification requests and prompt the user interactively.
- **BrowserOS Management**: Migrated browser automation entirely to **BrowserOS** Chrome MCP. All standard navigation, clicks, and snapshots run through the BrowserOS server.
- **Firefox MCP Deprecation**: The legacy Firefox Marionette MCP debugger has been removed. Any browser commands or heuristic fallback calls previously targeting Firefox are automatically routed to BrowserOS Chrome for optimal stability and resource efficiency.

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