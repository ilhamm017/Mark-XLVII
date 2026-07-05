import sys
import os

# Redirect stdout/stderr to run.log if running under pythonw.exe or if stdout is None (no console)
if sys.executable.lower().endswith("pythonw.exe") or sys.stdout is None:
    try:
        # Open in append mode, utf-8, buffering=1 (line buffered)
        log_file = open("run.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        pass

# Force stdout/stderr to utf-8 encoding to prevent CP1252/UnicodeEncodeError on Windows
if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr is not None and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import asyncio
# Define TaskGroup drop-in replacement for Python < 3.11
if sys.version_info >= (3, 11):
    from asyncio import TaskGroup
else:
    from taskgroup import TaskGroup
import os
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window.warning=false"
import re
import threading
import json
import traceback
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types

# --- Sub2API Monkeypatching ---
_OriginalClient = genai.Client

class Sub2APIClient(_OriginalClient):
    def __init__(self, *args, **kwargs):
        use_direct = kwargs.pop('use_direct_google', False)
        if not use_direct:
            try:
                from pathlib import Path
                import json
                base_dir = Path(__file__).resolve().parent
                config_path = base_dir / "config" / "api_keys.json"
                
                # Default fallback values
                api_key = "sk-4a76ada3ad42cccd8e85725cce8778ee42dd8010fd41249cf4dab250c7b62948"
                base_url = "https://sub2api.randompulse.my.id/antigravity"
                
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    api_key = cfg.get("sub2api_key", api_key)
                    base_url = cfg.get("sub2api_base_url", base_url)
                
                kwargs['api_key'] = api_key
                http_opts = kwargs.get('http_options', {})
                if isinstance(http_opts, dict):
                    http_opts = http_opts.copy()
                    http_opts['base_url'] = base_url
                    http_opts['api_version'] = 'v1beta'
                elif http_opts is None:
                    http_opts = {
                        'base_url': base_url,
                        'api_version': 'v1beta'
                    }
                kwargs['http_options'] = http_opts
            except Exception as e:
                print(f"[Sub2API] Failed to route client: {e}")
        super().__init__(*args, **kwargs)

genai.Client = Sub2APIClient
# ------------------------------
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.ytmusic_control   import ytmusic_control
from actions.system_control    import system_control
from actions.hermes_tools      import hermes_tools
from actions.taskbar_manager   import list_taskbar_apps, get_active_window


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

def _load_config_value(key: str, default):
    try:
        import json
        if API_CONFIG_PATH.exists():
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get(key, default)
    except Exception:
        pass
    return default
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-3.1-flash-live-preview"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def convert_schema_to_uppercase(schema: dict) -> dict:
    ALLOWED_KEYS = {"type", "description", "properties", "required", "items", "enum", "format", "nullable"}

    def helper(s, is_properties_dict=False):
        if not isinstance(s, dict):
            return s
        new_s = {}
        for k, v in s.items():
            if is_properties_dict:
                if isinstance(v, dict):
                    new_s[k] = helper(v, is_properties_dict=False)
                elif isinstance(v, list):
                    new_s[k] = [helper(item, is_properties_dict=False) if isinstance(item, dict) else item for item in v]
                else:
                    new_s[k] = v
                continue

            if k not in ALLOWED_KEYS:
                continue
            if k == "type":
                if isinstance(v, str):
                    new_s[k] = v.upper()
                elif isinstance(v, list):
                    items = [item.upper() for item in v if isinstance(item, str)]
                    if "STRING" in items:
                        new_s[k] = "STRING"
                    elif "NUMBER" in items:
                        new_s[k] = "NUMBER"
                    elif "INTEGER" in items:
                        new_s[k] = "INTEGER"
                    elif "BOOLEAN" in items:
                        new_s[k] = "BOOLEAN"
                    elif "ARRAY" in items:
                        new_s[k] = "ARRAY"
                    elif "OBJECT" in items:
                        new_s[k] = "OBJECT"
                    elif items:
                        new_s[k] = items[0]
                    else:
                        new_s[k] = "STRING"
                else:
                    new_s[k] = "STRING"
            elif k == "properties" and isinstance(v, dict):
                new_s[k] = helper(v, is_properties_dict=True)
            elif isinstance(v, dict):
                new_s[k] = helper(v, is_properties_dict=False)
            elif isinstance(v, list):
                new_s[k] = [helper(item, is_properties_dict=False) if isinstance(item, dict) else item for item in v]
            else:
                new_s[k] = v
        return new_s

    uppercased = helper(schema, is_properties_dict=False)
    cleaned = {}
    for key in ["type", "properties", "required"]:
        if key in uppercased:
            cleaned[key] = uppercased[key]
    return cleaned

async def fetch_browseros_mcp_tools() -> list:
    if not _load_config_value("mcp_enabled_browseros", True):
        print("[BrowserOS MCP] Disabled by configuration.")
        return []
    import httpx
    url = _load_config_value("browseros_mcp_url", "http://127.0.0.1:9200/mcp")
    try:
        async with httpx.AsyncClient() as client:
            list_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            resp = await client.post(url, json=list_payload, headers=headers, timeout=3.0)
            resp.raise_for_status()
            res_json = resp.json()
            mcp_tools = res_json.get("result", {}).get("tools", [])
            
            declarations = []
            for tool in mcp_tools:
                name = tool.get("name")
                desc = tool.get("description")
                input_schema = tool.get("inputSchema", {})
                parameters = convert_schema_to_uppercase(input_schema)
                
                declarations.append({
                    "name": name,
                    "description": desc,
                    "parameters": parameters
                })
            print(f"[BrowserOS MCP] Dynamic tool registration: Loaded {len(declarations)} tools.")
            return declarations
    except Exception as e:
        print(f"[BrowserOS MCP] Could not load MCP tools: {e}")
        return []

async def call_browseros_mcp_tool(name: str, arguments: dict) -> dict:
    import httpx
    url = _load_config_value("browseros_mcp_url", "http://127.0.0.1:9200/mcp")
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "alice-assistant",
                "version": "1.0.0"
            }
        }
    }
    call_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        },
        "id": 2
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=init_payload, headers=headers, timeout=5.0)
        except Exception:
            pass  # If initialization fails, try calling the tool anyway
        resp = await client.post(url, json=call_payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        res_json = resp.json()
        if "error" in res_json:
            raise Exception(f"MCP Tool Error: {res_json['error']}")
        return res_json.get("result", {})

def parse_mcp_response(text: str) -> dict:
    import json
    try:
        return json.loads(text)
    except Exception:
        pass
    data_lines = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        try:
            return json.loads("".join(data_lines))
        except Exception as e:
            raise Exception(f"Failed to parse SSE JSON: {e}. Raw content: {text}")
    raise Exception(f"Unable to parse MCP response. Raw content: {text}")

async def fetch_vscode_mcp_tools() -> list:
    if not _load_config_value("mcp_enabled_vscode", True):
        print("[VS Code MCP] Disabled by configuration.")
        return []
    import httpx
    url = _load_config_value("vscode_mcp_url", "http://127.0.0.1:3017/mcp")
    try:
        async with httpx.AsyncClient() as client:
            list_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            resp = await client.post(url, json=list_payload, headers=headers, timeout=3.0)
            resp.raise_for_status()
            parsed = parse_mcp_response(resp.text)
            mcp_tools = parsed.get("result", {}).get("tools", [])
            
            declarations = []
            for tool in mcp_tools:
                name = tool.get("name")
                desc = tool.get("description")
                input_schema = tool.get("inputSchema", {})
                parameters = convert_schema_to_uppercase(input_schema)
                
                declarations.append({
                    "name": name,
                    "description": desc,
                    "parameters": parameters
                })
            print(f"[VS Code MCP] Dynamic tool registration: Loaded {len(declarations)} tools.")
            return declarations
    except Exception as e:
        print(f"[VS Code MCP] Could not load MCP tools: {e}")
        return []

async def call_vscode_mcp_tool(name: str, arguments: dict) -> dict:
    import httpx
    url = _load_config_value("vscode_mcp_url", "http://127.0.0.1:3017/mcp")
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "alice-assistant",
                "version": "1.0.0"
            }
        }
    }
    call_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        },
        "id": 3
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=init_payload, headers=headers, timeout=5.0)
        except Exception:
            pass  # If initialization fails, try calling the tool anyway
        resp = await client.post(url, json=call_payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        parsed = parse_mcp_response(resp.text)
        if "error" in parsed:
            raise Exception(f"VS Code MCP Tool Error: {parsed['error']}")
        return parsed.get("result", {})

async def fetch_custom_mcp_tools() -> list:
    if not _load_config_value("mcp_custom_enabled", False):
        return []
    url = _load_config_value("mcp_custom_url", "").strip()
    if not url:
        return []
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            list_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            resp = await client.post(url, json=list_payload, headers=headers, timeout=3.0)
            resp.raise_for_status()
            parsed = parse_mcp_response(resp.text)
            mcp_tools = parsed.get("result", {}).get("tools", [])
            
            declarations = []
            for tool in mcp_tools:
                name = tool.get("name")
                desc = tool.get("description")
                input_schema = tool.get("inputSchema", {})
                parameters = convert_schema_to_uppercase(input_schema)
                
                declarations.append({
                    "name": name,
                    "description": desc,
                    "parameters": parameters
                })
            print(f"[Custom MCP] Dynamic tool registration: Loaded {len(declarations)} tools.")
            return declarations
    except Exception as e:
        print(f"[Custom MCP] Could not load MCP tools: {e}")
        return []

async def call_custom_mcp_tool(name: str, arguments: dict) -> dict:
    import httpx
    url = _load_config_value("mcp_custom_url", "").strip()
    if not url:
        raise Exception("Custom MCP URL is not configured.")
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "alice-assistant",
                "version": "1.0.0"
            }
        }
    }
    call_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        },
        "id": 4
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=init_payload, headers=headers, timeout=5.0)
        except Exception:
            pass
        resp = await client.post(url, json=call_payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        parsed = parse_mcp_response(resp.text)
        if "error" in parsed:
            raise Exception(f"Custom MCP Tool Error: {parsed['error']}")
        return parsed.get("result", {})

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are ALICE, an advanced AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "view_alice_skill",
        "description": "Loads the detailed instructions and steps for an available ALICE desktop/voice skill.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "skill_id": {"type": "STRING", "description": "The exact ID/filename of the skill (e.g. 'windows_control', 'music_playback')"}
            },
            "required": ["skill_id"]
        }
    },
    {
        "name": "ask_hermes",
        "description": (
            "Routes a complex programming, coding, server task, or ANY task you lack a built-in tool or capability to execute. "
            "If the user asks for a capability or action you don't have a direct tool for, route the query to Hermes "
            "so he can write the script, modify ALICE's files, or execute the required workflow autonomously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The request or task for Hermes"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "list_taskbar_apps",
        "description": (
            "Returns a list of all active application windows visible on the user's taskbar. "
            "Use this when the user asks what applications are currently open, running, "
            "or active on the taskbar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "get_active_window",
        "description": (
            "Returns the window title and executable process name of the active foreground window currently in focus on the user's desktop. "
            "Use this whenever the user asks an ambiguous question (like 'how to do this', 'explain this', 'how to cut video') "
            "to check what application they are actively working on before answering."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web. Use for ANY question about current facts, events, prices, "
            "or topics — always prefer this over guessing. "
            "Modes: 'search' (default), 'news' (latest headlines on a topic), "
            "'research' (deep comprehensive answer), 'price' (product cost lookup), "
            "'compare' (side-by-side comparison of items)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "ytmusic_control",
        "description": (
            "Controls YouTube Music Desktop App. "
            "Use for playing music, pausing, skipping tracks, setting volume, "
            "liking/disliking songs, checking current playing status, or managing queue. "
            "Actions: play | pause | toggle_play | next | previous | like | dislike | set_volume | status | queue | clear_queue | authenticate. "
            "For 'play' action, pass 'query' to search and play a song, or 'video_id' to play a specific video/track directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "play | pause | toggle_play | next | previous | like | dislike | set_volume | status | queue | clear_queue | authenticate"},
                "query":       {"type": "STRING", "description": "Search query for play/queue action"},
                "video_id":    {"type": "STRING", "description": "Specific YouTube video/track ID to play or queue"},
                "volume":      {"type": "INTEGER", "description": "Volume level 0-100 (for set_volume action)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "Returns a textual analysis of the captured display/camera. "
            "MUST be called when the user asks what is on screen, what you see, "
            "to look at the camera, analyze the display, etc. "
            "CRITICAL: Do NOT use this for inspecting web pages or browser contents if BrowserOS or another browser is running; "
            "use browser_control with action='get_text' or action='screenshot' instead to retrieve precise text or visual content."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level (absolute like 50, or relative like -10, +20), text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome', 'use BrowserOS'). Multiple browsers can run simultaneously. "
            "If BrowserOS is running, 'browseros' is the default and connects directly to the user's active "
            "BrowserOS window on port 9100, allowing real-time desktop browser control. "
            "CRITICAL: When the user asks about the active web page (what is on the website, read the text, "
            "what does it say, extract data, check the page), always prefer browser_control with action='get_text' "
            "or action='screenshot' over screen_process to get direct page data."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: browseros | chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_alice",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Alice. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "system_control",
        "description": (
            "Performs local system operations: running terminal/shell commands, managing processes (listing or killing), "
            "inspecting workspace/git status, triggering native OS desktop notifications, managing python/system packages, "
            "and running local network diagnostics (ping, listening ports, network interfaces)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool": {
                    "type": "STRING",
                    "description": "The specific operation to run: 'execute_command' | 'manage_process' | 'workspace_info' | 'show_notification' | 'manage_packages' | 'network_diagnostics'"
                },
                "command": {
                    "type": "STRING",
                    "description": "Required for 'execute_command': the terminal command to run"
                },
                "action": {
                    "type": "STRING",
                    "description": "Action for sub-tool. E.g. 'list' or 'kill' for manage_process; 'git_status' or 'list_files' for workspace_info; 'install' or 'uninstall' or 'list' for manage_packages; 'interfaces' or 'ping' or 'ports' for network_diagnostics"
                },
                "pid": {
                    "type": "INTEGER",
                    "description": "Process ID (PID) to terminate/kill"
                },
                "name": {
                    "type": "STRING",
                    "description": "Process name pattern to terminate/kill"
                },
                "path": {
                    "type": "STRING",
                    "description": "Workspace/project directory path to inspect"
                },
                "title": {
                    "type": "STRING",
                    "description": "Title of the notification to display"
                },
                "message": {
                    "type": "STRING",
                    "description": "Message body of the notification"
                },
                "manager": {
                    "type": "STRING",
                    "description": "Package manager to use: 'pip' | 'npm' | 'winget' | 'apt'"
                },
                "package_name": {
                    "type": "STRING",
                    "description": "Name of package/dependencies to install/uninstall"
                },
                "target": {
                    "type": "STRING",
                    "description": "Network target IP or hostname (for ping)"
                }
            },
            "required": ["tool"]
        }
    },
    {
        "name": "hermes_tools",
        "description": (
            "Hermes-emulated powerful development utilities: paginated file reading (read_file with offset/limit), "
            "precise code patching (patch_file with old_string/new_string), ripgrep-like file and content searching (search_file_content), "
            "and clean web/pdf text extraction (web_extract)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool": {
                    "type": "STRING",
                    "description": "The specific utility to run: 'read_file' | 'patch_file' | 'search_file_content' | 'web_extract'"
                },
                "path": {
                    "type": "STRING",
                    "description": "File or folder path to operate on"
                },
                "offset": {
                    "type": "INTEGER",
                    "description": "1-based line number to start reading from (for read_file)"
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum line count to read (for read_file) or max results to return (for search_file_content)"
                },
                "old_string": {
                    "type": "STRING",
                    "description": "Exact code or text snippet to find (for patch_file)"
                },
                "new_string": {
                    "type": "STRING",
                    "description": "Replacement text or code (for patch_file)"
                },
                "replace_all": {
                    "type": "BOOLEAN",
                    "description": "Whether to replace all occurrences of old_string (for patch_file). Default is false."
                },
                "pattern": {
                    "type": "STRING",
                    "description": "Regex or glob pattern to search for (for search_file_content)"
                },
                "target": {
                    "type": "STRING",
                    "description": "Search target: 'content' (default, searches inside files) or 'files' (finds file names) (for search_file_content)"
                },
                "file_glob": {
                    "type": "STRING",
                    "description": "Optional file name filter glob, e.g. '*.py' or '*config*' (for search_file_content)"
                },
                "url": {
                    "type": "STRING",
                    "description": "Webpage URL to extract markdown/text content from (for web_extract)"
                }
            },
            "required": ["tool"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

# --- Plugin system ---


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._phone_active  = False   # True while phone mic is streaming; pauses PC mic
        self.ui.on_text_command  = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui._win.on_escape_pressed = self.handle_interruption
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent = False          # morning briefing fires once per process
        self._sys_monitor   = SystemMonitor()  # persistent cooldown state
        self._last_voice_time = 0.0
        self._play_stream     = None
        self._turn_count      = 0
        self.mcp_tools        = []
        self.vscode_tool_names    = set()
        self.browseros_tool_names = set()
        self.custom_tool_names    = set()
        self._wake_event      = None
        self._session_resumption_handle = None
        import time
        self._last_activity_time = time.time()
        self.ui._win.on_wake_requested = self._wake_up

    def get_server_url(self, endpoint: str) -> str:
        import requests
        if not hasattr(self, '_resolved_server_host') or self._resolved_server_host is None:
            self._resolved_server_host = "192.168.0.102:8080"
            for host in ["192.168.0.102:8080", "100.69.16.104:8080"]:
                try:
                    res = requests.get(f"http://{host}/api/hermes/memory?user=ping_test", timeout=1.5)
                    if res.status_code in (200, 404, 401, 500):
                        self._resolved_server_host = host
                        print(f"[Server] Resolved server host to {host}")
                        break
                except Exception:
                    pass
        return f"http://{self._resolved_server_host}{endpoint}"

    def _load_all_api_keys(self) -> list[str]:
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                alt_keys = data.get("gemini_api_keys")
                if isinstance(alt_keys, list):
                    return [k.strip() for k in alt_keys if k.strip()]
                    
                keys = data.get("gemini_api_key")
                if isinstance(keys, list):
                    return [k.strip() for k in keys if k.strip()]
                elif isinstance(keys, str) and keys.strip():
                    if "," in keys:
                        return [k.strip() for k in keys.split(",") if k.strip()]
                    return [keys.strip()]
        except Exception as e:
            print(f"[ALICE] Error loading API keys: {e}")
        return []

    def _load_alice_skills_manifest(self) -> str:
        skills_dir = BASE_DIR / "skills"
        if not skills_dir.exists():
            try:
                skills_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                return ""
        
        manifest_lines = []
        md_files = list(skills_dir.glob("*.md"))
        if not md_files:
            return ""
            
        manifest_lines.append("[AVAILABLE ALICE DESKTOP/VOICE SKILLS]")
        manifest_lines.append("You have access to specialized skills. If you need details on how to execute one, call `view_alice_skill` with its name.")
        
        for f in md_files:
            try:
                content = f.read_text(encoding="utf-8")
                name = f.stem
                description = "No description provided."
                
                if content.startswith("---"):
                    end_idx = content.find("\n---\n", 3)
                    if end_idx != -1:
                        frontmatter_str = content[3:end_idx]
                        for line in frontmatter_str.split("\n"):
                            if ":" in line:
                                k, v = line.split(":", 1)
                                if k.strip().lower() == "name":
                                    name = v.strip()
                                elif k.strip().lower() == "description":
                                    description = v.strip()
                
                manifest_lines.append(f"- {f.stem}: {description} (Name: {name})")
            except Exception as e:
                print(f"[ALICE SKILLS] Error parsing {f.name}: {e}")
                
        return "\n" + "\n".join(manifest_lines) + "\n\n"

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _wake_up(self):
        import time
        self._last_activity_time = time.time()
        if self._wake_event and not self._wake_event.is_set():
            print("[ALICE] Waking up session...")
            if self._loop:
                self._loop.call_soon_threadsafe(self._wake_event.set)

    def _on_text_command(self, text: str):
        import time
        self._last_activity_time = time.time()
        self._wake_up()

        cmd = text.strip().lower()
        if cmd in ["stop", "/stop", "quiet", "diam", "cancel", "shutup", "batal"]:
            self.handle_interruption()
            self.ui.write_log("SYS: Interrupted speech by user command.")
            return

        if cmd in ["reset", "/reset", "restart", "refresh"]:
            self.handle_interruption()
            self.ui.write_log("SYS: Rotating session manually...")
            if self.session and self._loop:
                asyncio.run_coroutine_threadsafe(self.session.close(), self._loop)
            return

        if text.strip().lower().startswith("hermes ") or text.strip().startswith("/hermes "):
            query = text.strip()
            if query.startswith("/hermes "):
                query = query[8:]
            else:
                query = query[7:]
            
            import uuid
            task_id = f"local_{uuid.uuid4().hex[:6]}"
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._run_local_hermes_task(task_id, query),
                    self._loop
                )
            else:
                self.ui.write_log("SYS: Async loop not running. Cannot execute Hermes task.")
            return

        if not self._loop:
            return

        async def send_when_ready():
            for _ in range(100):
                if self.session:
                    break
                await asyncio.sleep(0.1)
            if self.session:
                await self.session.send_realtime_input(text=text)
            else:
                self.ui.write_log("SYS: Failed to send command — session not ready.")

        asyncio.run_coroutine_threadsafe(send_when_ready(), self._loop)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        else:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            self.ui.set_speaking_volume(0.0)

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_realtime_input(text=text),
            self._loop
        )

    async def speak_when_ready(self, text: str):
        while True:
            with self._speaking_lock:
                alice_speaking = self._is_speaking
            queue_empty = self.audio_in_queue.empty() if self.audio_in_queue else True
            if not alice_speaking and queue_empty:
                break
            await asyncio.sleep(0.5)
            
        # Give a small pause (1.0 second) for natural conversation transition
        await asyncio.sleep(1.0)
        
        while True:
            with self._speaking_lock:
                alice_speaking = self._is_speaking
            queue_empty = self.audio_in_queue.empty() if self.audio_in_queue else True
            if not alice_speaking and queue_empty:
                break
            await asyncio.sleep(0.5)
            
        self.speak(text)

    def _sync_memory_to_hermes(self):
        try:
            from memory.memory_manager import load_memory
            import json
            import os
            
            user_name = "ilham"
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    user_name = cfg.get("user_name", "ilham").lower().strip()
            except Exception:
                pass
                
            memory = load_memory()
            facts = []
            for cat, items in memory.items():
                if not isinstance(items, dict):
                    continue
                for key, entry in items.items():
                    if isinstance(entry, dict) and "value" in entry:
                        val = entry.get("value")
                        if val:
                            facts.append(f"Category [{cat}] {key}: {val}")
                    elif isinstance(entry, str) and entry:
                        facts.append(f"Category [{cat}] {key}: {entry}")
                        
            content = "\n§\n".join(facts)
            
            home_dir = os.path.expanduser("~")
            mem_dir = os.path.join(home_dir, ".hermes", "memories")
            os.makedirs(mem_dir, exist_ok=True)
            
            user_suffix = f"_{user_name}" if user_name != "ilham" else ""
            user_md_path = os.path.join(mem_dir, f"USER{user_suffix}.md")
            
            with open(user_md_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[Memory] 🔄 Synced {len(facts)} ALICE memory entries to {user_md_path}")
        except Exception as e:
            print(f"[Memory] ❌ Failed to sync ALICE memory to Hermes: {e}")

    def _sync_memory_from_hermes(self):
        try:
            from memory.memory_manager import update_memory
            import os
            import re
            
            user_name = "ilham"
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    user_name = cfg.get("user_name", "ilham").lower().strip()
            except Exception:
                pass
                
            home_dir = os.path.expanduser("~")
            mem_dir = os.path.join(home_dir, ".hermes", "memories")
            user_suffix = f"_{user_name}" if user_name != "ilham" else ""
            user_md_path = os.path.join(mem_dir, f"USER{user_suffix}.md")
            
            if not os.path.exists(user_md_path):
                return
                
            with open(user_md_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            facts = [f.strip() for f in content.split("§") if f.strip()]
            updates = {}
            for fact in facts:
                match = re.match(r"^Category\s+\[([^\]]+)\]\s+([^:]+):\s*(.*)$", fact, re.IGNORECASE)
                if match:
                    cat = match.group(1).strip()
                    key = match.group(2).strip()
                    val = match.group(3).strip()
                    
                    if cat not in updates:
                        updates[cat] = {}
                    updates[cat][key] = {"value": val}
                else:
                    words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', '', fact).split() if w]
                    if words:
                        key = "_".join(words[:3]).lower()
                        if "notes" not in updates:
                            updates["notes"] = {}
                        updates["notes"][key] = {"value": fact}
                        
            if updates:
                update_memory(updates)
                print(f"[Memory] 🔄 Synced memory back from Hermes to ALICE (updated {len(updates)} categories)")
        except Exception as e:
            print(f"[Memory] ❌ Failed to sync memory from Hermes to ALICE: {e}")

    async def _run_local_hermes_task(self, task_id: str, query: str):
        import os
        import sys
        import httpx
        import json
        import re
        import platform
        import subprocess
        
        print(f"[ALICE] 🔄 SYS: Starting local Hermes task {task_id} for query: {query}")
        self.ui.write_log(f"SYS: Starting local Hermes task {task_id}")
        
        # Sync ALICE memory to Hermes memories before execution
        self._sync_memory_to_hermes()
        
        project_dir = os.path.dirname(os.path.abspath(__file__))
        
        try:
            # Try to send query to daemon server first
            daemon_url = "http://127.0.0.1:8085/query"
            print(f"[ALICE] Attempting to route query to Hermes Daemon: {daemon_url}")
            
            use_daemon = False
            response_text = ""
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(daemon_url, json={"query": query, "task_id": task_id})
                    if resp.status_code == 200 and resp.json().get("status") == "started":
                        use_daemon = True
            except Exception as daemon_err:
                print(f"[ALICE] Hermes Daemon not reachable or failed to start: {daemon_err}. Falling back to hermes.exe subprocess.")
                
            if use_daemon:
                # Poll and tail log file in real-time, checking for the done file
                log_path = os.path.join(project_dir, ".hermes", "logs", f"{task_id}.log")
                done_path = os.path.join(project_dir, ".hermes", "logs", f"{task_id}.done")
                
                last_pos = 0
                while True:
                    if os.path.exists(log_path):
                        try:
                            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                                f.seek(last_pos)
                                lines = f.readlines()
                                last_pos = f.tell()
                                
                            for line in lines:
                                line_str = line.strip()
                                if line_str:
                                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                                    clean_str = ansi_escape.sub('', line_str)
                                    if clean_str:
                                        print(f"[ALICE] [Local Hermes] {clean_str}")
                                        # Do not write to general activity log since we have a dedicated Hermes logs view
                                        # self.ui.write_log(f"HERMES: {clean_str}")
                        except Exception as read_err:
                            print(f"[ALICE] Error reading local Hermes log: {read_err}")
                            
                    if os.path.exists(done_path):
                        try:
                            with open(done_path, "r", encoding="utf-8") as f:
                                done_data = json.load(f)
                            if done_data.get("status") == "success":
                                response_text = done_data.get("response", "")
                            else:
                                raise RuntimeError(done_data.get("error", "Unknown error in Hermes task."))
                            break
                        except json.JSONDecodeError:
                            # Done file might be partially written, sleep and retry
                            pass
                            
                    await asyncio.sleep(0.5)
                    
                print(f"[ALICE] 🔄 HERMES (Daemon): Local task {task_id} completed.")
                self.ui.write_log(f"HERMES: Local task {task_id} completed (Daemon).")
                
                if hasattr(self.ui, "show_content"):
                    self.ui.show_content(f"LOCAL HERMES RESPONSE ({task_id})", response_text)
                    
                # Sync memory back from Hermes to ALICE
                self._sync_memory_from_hermes()
                
                await self.speak_when_ready(
                    f"Sir, local task {task_id} has completed successfully. "
                    f"Please explain the full findings, statuses, versions, paths, and details from the output below to the user in casual Indonesian/Javanese (Ragam Santai). "
                    f"Do NOT be concise, do NOT give a lazy summary, and do NOT ask the user to read it themselves. Explain it step-by-step in detail. "
                    f"Output:\n{response_text}"
                )
                return

            # FALLBACK to standard subprocess run
            scripts_dir = os.path.dirname(sys.executable)
            hermes_path = os.path.join(scripts_dir, 'hermes.exe')
            if not os.path.exists(hermes_path):
                hermes_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'hermes.exe'))
            
            print(f"[ALICE] Using local Hermes path: {hermes_path}")
            project_dir = os.path.dirname(os.path.abspath(__file__))
            hermes_home = os.path.join(project_dir, '.hermes')
            custom_env = {**os.environ, "HERMES_HOME": hermes_home}
            
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = await asyncio.create_subprocess_exec(
                hermes_path, '-z', query,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=custom_env,
                **kwargs
            )
            
            stdout_lines = []
            stderr_lines = []
            
            async def read_stdout():
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                        clean_str = ansi_escape.sub('', line_str)
                        if clean_str:
                            print(f"[ALICE] [Local Hermes] {clean_str}")
                            # Do not write to general activity log since we have a dedicated Hermes logs view
                            # self.ui.write_log(f"HERMES: {clean_str}")
                            stdout_lines.append(clean_str)
                        
            async def read_stderr():
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        import re
                        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                        clean_str = ansi_escape.sub('', line_str)
                        if clean_str:
                            print(f"[ALICE] [Local Hermes ERR] {clean_str}")
                            stderr_lines.append(clean_str)

            await asyncio.gather(read_stdout(), read_stderr())
            return_code = await proc.wait()
            
            if return_code == 0:
                full_output = "\n".join(stdout_lines)
                print(f"[ALICE] 🔄 HERMES: Local task {task_id} completed.")
                self.ui.write_log(f"HERMES: Local task {task_id} completed.")
                if hasattr(self.ui, "show_content"):
                    self.ui.show_content(f"LOCAL HERMES RESPONSE ({task_id})", full_output)
                
                # Sync memory back from Hermes to ALICE
                self._sync_memory_from_hermes()
                
                await self.speak_when_ready(
                    f"Sir, local task {task_id} has completed successfully. "
                    f"Please explain the full findings, statuses, versions, paths, and details from the output below to the user in casual Indonesian/Javanese (Ragam Santai). "
                    f"Do NOT be concise, do NOT give a lazy summary, and do NOT ask the user to read it themselves. Explain it step-by-step in detail. "
                    f"Output:\n{full_output}"
                )
            else:
                full_err = "\n".join(stderr_lines)
                print(f"[ALICE] ❌ HERMES: Local task {task_id} failed with exit code {return_code}.")
                self.ui.write_log(f"HERMES: Local task {task_id} failed.")
                await self.speak_when_ready(f"Sir, the local task {task_id} has failed: {full_err or 'Exit code ' + str(return_code)}")
                
        except Exception as e:
            print(f"[ALICE] ❌ Exception in local Hermes execution: {e}")
            self.ui.write_log(f"SYS: Local Hermes task {task_id} exception: {e}")
            await self.speak_when_ready(f"Sir, I encountered an error running local Hermes task {task_id}: {str(e)}")

    async def _start_hermes_daemon(self):
        print("[ALICE] 🔄 Starting Hermes Daemon...")
        import os
        import sys
        import httpx
        import platform
        import subprocess
        
        project_dir = os.path.dirname(os.path.abspath(__file__))
        daemon_path = os.path.join(project_dir, 'hermes_daemon.py')
        
        # Kill any existing daemon on port 8085 first
        try:
            async with httpx.AsyncClient() as client:
                await client.post("http://127.0.0.1:8085/shutdown", timeout=1.0)
                await asyncio.sleep(0.5)
        except Exception:
            pass
            
        try:
            logs_dir = os.path.join(project_dir, ".hermes", "logs")
            os.makedirs(logs_dir, exist_ok=True)
            daemon_log_path = os.path.join(logs_dir, "daemon.log")
            
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            daemon_log_file = open(daemon_log_path, "a", encoding="utf-8")

            self._hermes_daemon_proc = await asyncio.create_subprocess_exec(
                sys.executable, daemon_path,
                stdout=daemon_log_file,
                stderr=daemon_log_file,
                **kwargs
            )
            
            # Wait up to 5 seconds for the daemon to become responsive
            for _ in range(10):
                try:
                    async with httpx.AsyncClient() as client:
                        r = await client.get("http://127.0.0.1:8085/docs", timeout=0.5)
                        if r.status_code == 200:
                            print("[ALICE] 🔄 Hermes Daemon is online and healthy.")
                            break
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            else:
                print("[ALICE] ⚠️ Warning: Hermes Daemon took too long to respond.")
        except Exception as e:
            print(f"[ALICE] ❌ Failed to start Hermes Daemon: {e}")

    async def _poll_hermes_task(self, task_id: str, query: str):
        print(f"[ALICE] 🔄 SYS: Started polling task {task_id} for query: {query}")
        self.ui.write_log(f"SYS: Started polling task {task_id}")
        url = self.get_server_url(f"/api/hermes/task/{task_id}")
        
        await asyncio.sleep(2)
        
        import requests
        
        def _get_status():
            try:
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    return res.json()
                return {"status": "error", "message": f"Server status code {res.status_code}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
                
        loop = asyncio.get_event_loop()
        
        while True:
            data = await loop.run_in_executor(None, _get_status)
            status = data.get("status")
            print(f"[ALICE] 🔄 Polling task {task_id}: status={status}")
            
            if status == "completed":
                response = data.get("response", "No response from Hermes.")
                print(f"[ALICE] 🔄 HERMES: Task {task_id} completed.")
                self.ui.write_log(f"HERMES: Task {task_id} completed.")
                if hasattr(self.ui, "show_content"):
                    self.ui.show_content(f"HERMES RESPONSE ({task_id})", response)
                await self.speak_when_ready(
                    f"Sir, local task {task_id} has completed successfully. "
                    f"Please explain the full findings, statuses, versions, paths, and details from the output below to the user in casual Indonesian/Javanese (Ragam Santai). "
                    f"Do NOT be concise, do NOT give a lazy summary, and do NOT ask the user to read it themselves. Explain it step-by-step in detail. "
                    f"Output:\n{response}"
                )
                break
            elif status == "failed":
                response = data.get("response", "Unknown failure.")
                print(f"[ALICE] ❌ HERMES: Task {task_id} failed: {response}")
                self.ui.write_log(f"HERMES: Task {task_id} failed.")
                await self.speak_when_ready(f"Sir, the task {task_id} on Hermes server has failed: {response}")
                break
            elif status == "error":
                message = data.get("message", "")
                print(f"[ALICE] ⚠️ SYS: Task poll connection error: {message}")
                self.ui.write_log(f"SYS: Task poll connection error: {message}")
                
            await asyncio.sleep(3)

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def handle_interruption(self):
        self.ui.write_log("SYS: Interruption detected.")
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        if self._play_stream is not None:
            try:
                self._play_stream.stop()
                self._play_stream.close()
            except Exception as e:
                print(f"[ALICE] Error stopping stream: {e}")
            self._play_stream = None
        
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.set_speaking(False)

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime
        import requests

        # Pull memory directly from Honcho server
        mem_str = ""
        try:
            memory = load_memory()
            mem_str = format_memory_for_prompt(memory)
            if mem_str:
                print("[Memory] Dynamically loaded memory directly from Honcho server.")
        except Exception as e:
            print(f"[Memory] Failed to load memory directly from Honcho server: {e}")

        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        import platform
        import socket as py_socket
        import getpass

        os_name = platform.system()
        try:
            hostname = py_socket.gethostname()
        except Exception:
            hostname = "unknown"

        try:
            username = getpass.getuser()
        except Exception:
            username = "unknown"

        env_ctx = (
            f"[HOST ENVIRONMENT]\n"
            f"You are currently running directly on the following machine:\n"
            f"- Operating System: {os_name}\n"
            f"- Computer Hostname: {hostname}\n"
            f"- Current OS User: {username}\n"
            f"Always align all tool parameters, system commands, paths, and interactions with this active environment ({os_name} on {hostname}).\n\n"
        )

        parts = [time_ctx, env_ctx]
        if mem_str:
            parts.append(mem_str)

        skills_manifest = self._load_alice_skills_manifest()
        if skills_manifest:
            parts.append(skills_manifest)

        parts.append(sys_prompt)

        combined_tools = TOOL_DECLARATIONS.copy()
        if hasattr(self, 'mcp_tools') and self.mcp_tools:
            combined_tools.extend(self.mcp_tools)

        system_instruction_content = types.Content(
            parts=[types.Part.from_text(text="\n".join(parts))]
        )

        handle = getattr(self, "_session_resumption_handle", None)
        if handle:
            print(f"[ALICE] Resuming session with handle: {handle[:15]}...")

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=system_instruction_content,
            tools=[{"function_declarations": combined_tools}],
            session_resumption=types.SessionResumptionConfig(handle=handle),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_load_config_value("voice_name", "Aoede")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[ALICE] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                try:
                    update_memory({category: {key: {"value": value}}})
                    print(f"[Memory] 💾 save_memory directly to Honcho: {category}/{key} = {value}")
                except Exception as e:
                    print(f"[Memory] Failed to save memory to Honcho: {e}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "view_alice_skill":
                skill_id = args.get("skill_id") or ""
                skill_id = os.path.basename(skill_id)
                skills_dir = BASE_DIR / "skills"
                skill_path = skills_dir / f"{skill_id}.md"
                if skill_path.exists():
                    try:
                        result = skill_path.read_text(encoding="utf-8")
                    except Exception as e:
                        result = f"Error reading skill {skill_id}: {e}"
                else:
                    skills_list = [f.stem for f in skills_dir.glob("*.md")]
                    result = f"Skill '{skill_id}' not found. Available skills are: " + ", ".join(skills_list)

            elif name == "ask_hermes":
                query = args.get("query")
                import uuid
                task_id = f"local_{uuid.uuid4().hex[:6]}"
                result = f"Task successfully started locally in WSL. Task ID: {task_id}. I will speak the response once it is complete."
                asyncio.create_task(self._run_local_hermes_task(task_id, query))

            elif name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "list_taskbar_apps":
                r = await loop.run_in_executor(None, lambda: list_taskbar_apps(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "get_active_window":
                r = await loop.run_in_executor(None, lambda: get_active_window(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "ytmusic_control":
                r = await loop.run_in_executor(None, lambda: ytmusic_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                r = await loop.run_in_executor(None, lambda: screen_process(parameters=args, player=self.ui))
                result = r or "Vision module failed to analyze screen."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
                # Mirror substantial results to the on-screen content panel
                if r and len(r) > 120:
                    mode  = args.get("mode", "search").upper()
                    query = args.get("query") or ", ".join(args.get("items", []))
                    label = f"{mode} — {query[:38]}" if query else mode
                    self.ui.show_content(label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_control":
                r = await loop.run_in_executor(None, lambda: system_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "hermes_tools":
                r = await loop.run_in_executor(None, lambda: hermes_tools(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "shutdown_alice":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                if hasattr(self, "_hermes_daemon_proc") and self._hermes_daemon_proc:
                    try:
                        self._hermes_daemon_proc.terminate()
                    except Exception:
                        pass
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                builtins = {
                    "ask_hermes", "open_app", "weather_report", "browser_control", 
                    "file_controller", "send_message", "ytmusic_control", "reminder", 
                    "youtube_video", "screen_process", "computer_settings", 
                    "desktop_control", "code_helper", "dev_agent", "web_search",
                    "file_processor", "computer_control", "game_updater", "flight_finder",
                    "system_status", "shutdown_alice", "save_memory", "system_control", "hermes_tools"
                }
                if name not in builtins:
                    # If tool is not in any registered list, try refreshing lists dynamically
                    if (name not in self.vscode_tool_names and 
                        name not in self.browseros_tool_names and 
                        name not in self.custom_tool_names):
                        print(f"[ALICE] Tool '{name}' not found in registered lists. Refreshing MCP tools...")
                        try:
                            vscode_tools = await fetch_vscode_mcp_tools()
                            self.vscode_tool_names = {t["name"] for t in vscode_tools}
                        except Exception as e:
                            print(f"[ALICE] Failed to refresh VS Code tools: {e}")
                        try:
                            browser_tools = await fetch_browseros_mcp_tools()
                            self.browseros_tool_names = {t["name"] for t in browser_tools}
                        except Exception as e:
                            print(f"[ALICE] Failed to refresh BrowserOS tools: {e}")
                        try:
                            custom_tools = await fetch_custom_mcp_tools()
                            self.custom_tool_names = {t["name"] for t in custom_tools}
                        except Exception as e:
                            print(f"[ALICE] Failed to refresh Custom tools: {e}")

                    if name in self.vscode_tool_names:
                        print(f"[ALICE] Forwarding {name} call to VS Code MCP server...")
                        mcp_res = await call_vscode_mcp_tool(name, args)
                    elif name in self.custom_tool_names:
                        print(f"[ALICE] Forwarding {name} call to Custom MCP server...")
                        mcp_res = await call_custom_mcp_tool(name, args)
                    elif name in self.browseros_tool_names:
                        print(f"[ALICE] Forwarding {name} call to BrowserOS MCP server...")
                        mcp_res = await call_browseros_mcp_tool(name, args)
                    else:
                        # Smarter heuristic fallbacks based on name keywords
                        vscode_keywords = {"editor", "vscode", "terminal", "file", "directory", "grep", "insert", "replace", "execute_command"}
                        browseros_keywords = {"tab", "navigate", "screenshot", "pdf", "click", "type", "hover", "scroll", "download", "upload"}
                        
                        is_vscode = name.endswith("_code") or any(kw in name.lower() for kw in vscode_keywords)
                        is_browser = any(kw in name.lower() for kw in browseros_keywords)
                        
                        if is_vscode and not is_browser:
                            print(f"[ALICE] Heuristic: Forwarding {name} call to VS Code MCP server...")
                            mcp_res = await call_vscode_mcp_tool(name, args)
                        elif is_browser and not is_vscode:
                            print(f"[ALICE] Heuristic: Forwarding {name} call to BrowserOS MCP server...")
                            mcp_res = await call_browseros_mcp_tool(name, args)
                        else:
                            # Default fallback
                            if name.endswith("_code"):
                                print(f"[ALICE] Heuristic: Forwarding {name} call to VS Code MCP server...")
                                mcp_res = await call_vscode_mcp_tool(name, args)
                            else:
                                print(f"[ALICE] Heuristic: Forwarding {name} call to BrowserOS MCP server...")
                                mcp_res = await call_browseros_mcp_tool(name, args)
                    result = mcp_res
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[ALICE] 📤 {name} → {str(result)[:80]}")
        resp_data = result if isinstance(result, dict) else {"result": result}
        return types.FunctionResponse(
            id=fc.id, name=name,
            response=resp_data
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(audio=msg)

    async def _listen_audio(self):
        print("[ALICE] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[ALICE] 🎤 Mic status warning: {status}")
            
            import time
            now = time.time()
            try:
                import numpy as np
                mean_val = np.nanmean(indata**2) if len(indata) > 0 else 0
                rms = np.sqrt(max(0.0, mean_val)) if not np.isnan(mean_val) else 0.0
                
                with self._speaking_lock:
                    alice_speaking = self._is_speaking
                
                threshold = 800 if alice_speaking else 200
                
                if rms > threshold:
                    self._last_voice_time = now
                    self._last_activity_time = now
                    loop.call_soon_threadsafe(self.ui.set_user_speaking, True)
                elif now - self._last_voice_time > 0.8:
                    loop.call_soon_threadsafe(self.ui.set_user_speaking, False)
            except Exception:
                alice_speaking = False

            should_block_mic = alice_speaking and not self.ui.voice_interrupt_enabled
            
            if alice_speaking and self.ui.voice_interrupt_enabled:
                if now - self._last_voice_time > 0.3:
                    should_block_mic = True

            if not should_block_mic and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                try:
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm;rate=16000"}
                    )
                except Exception:
                    pass

        try:
            while True:
                if not self.session:
                    await asyncio.sleep(0.5)
                    continue

                print("[ALICE] 🎤 Opening mic stream...")
                loop.call_soon_threadsafe(self.ui.set_mic_active, True)
                try:
                    mic_device_name = _load_config_value("mic_device_name", None)
                    mic_device_idx = None
                    if mic_device_name:
                        try:
                            devices = sd.query_devices()
                            for idx, dev in enumerate(devices):
                                if dev['max_input_channels'] > 0 and dev['name'] == mic_device_name:
                                    mic_device_idx = idx
                                    break
                        except Exception as e:
                            print(f"[ALICE] Error resolving input device: {e}")

                    with sd.InputStream(
                        device=mic_device_idx,
                        samplerate=SEND_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                        callback=callback,
                    ) as stream:
                        print("[ALICE] 🎤 Mic stream open and active")
                        while stream.active and self.session:
                            await asyncio.sleep(0.5)
                        print("[ALICE] ⚠️ Mic stream inactive or session closed. Releasing...")
                finally:
                    loop.call_soon_threadsafe(self.ui.set_mic_active, False)
                    loop.call_soon_threadsafe(self.ui.set_user_speaking, False)
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[ALICE] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[ALICE] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():
                    import time
                    self._last_activity_time = time.time()

                    if response.session_resumption_update:
                        sru = response.session_resumption_update
                        if sru.resumable and sru.new_handle:
                            self._session_resumption_handle = sru.new_handle
                            print(f"[ALICE] Saved session resumption handle: {sru.new_handle[:15]}...")

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.interrupted:
                            self.handle_interruption()

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            self._turn_count += 1

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Alice: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "alice",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[ALICE] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            import websockets
            from google.genai import errors as gerrors
            is_normal = (
                isinstance(e, websockets.exceptions.ConnectionClosedOK) or
                (isinstance(e, gerrors.APIError) and e.code == 1000)
            )
            if not is_normal:
                print(f"[ALICE] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[ALICE] 🔊 Play started")
        stream = None
        idle_ticks = 0
        self._play_stream = None

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                    idle_ticks = 0
                except asyncio.TimeoutError:
                    self.ui.set_speaking_volume(0.0)
                    if stream is not None:
                        idle_ticks += 1
                        if idle_ticks >= 5: # 0.5s of silence
                            try:
                                stream.stop()
                                stream.close()
                            except Exception:
                                pass
                            stream = None
                            self._play_stream = None
                            idle_ticks = 0

                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        if self._turn_count >= 12 and self.session:
                            self.ui.write_log("SYS: Session rotated to maintain low latency.")
                            asyncio.create_task(self.session.close())
                    continue

                self.set_speaking(True)
                if stream is None:
                    try:
                        spk_device_name = _load_config_value("spk_device_name", None)
                        spk_device_idx = None
                        if spk_device_name:
                            try:
                                devices = sd.query_devices()
                                for idx, dev in enumerate(devices):
                                    if dev['max_output_channels'] > 0 and dev['name'] == spk_device_name:
                                        spk_device_idx = idx
                                        break
                            except Exception as e:
                                print(f"[ALICE] Error resolving output device: {e}")

                        stream = sd.RawOutputStream(
                            device=spk_device_idx,
                            samplerate=RECEIVE_SAMPLE_RATE,
                            channels=CHANNELS,
                            dtype="int16",
                        )
                        stream.start()
                        self._play_stream = stream
                    except Exception as se:
                        print(f"[ALICE] ❌ Failed to open audio output stream: {se}")
                        continue

                try:
                    # hitung RMS volume dan pitch frekuensi dominan dari chunk audio (dtype int16)
                    import numpy as np
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    if len(samples) > 0:
                        # hitung RMS
                        mean_val = np.mean(samples.astype(np.float32) ** 2)
                        rms = np.sqrt(mean_val) if mean_val > 0 else 0.0
                        vol = min(1.0, rms / 3000.0)
                        
                        # hitung Pitch Dominan via FFT
                        freq_norm = 0.5
                        try:
                            fft_data = np.abs(np.fft.rfft(samples))
                            freqs = np.fft.rfftfreq(len(samples), d=1.0/RECEIVE_SAMPLE_RATE)
                            if len(fft_data) > 1:
                                dom_idx = np.argmax(fft_data[1:]) + 1
                                dom_freq = freqs[dom_idx]
                                # Normalisasi range frekuensi suara manusia vocal range (80 Hz s.d 800 Hz)
                                freq_norm = max(0.0, min(1.0, (dom_freq - 80.0) / 720.0))
                        except Exception:
                            pass
                        
                        self.ui.set_speaking_volume(vol, freq_norm)

                    await asyncio.to_thread(stream.write, chunk)
                except Exception as we:
                    print(f"[ALICE] Play chunk error (possibly stream closed): {we}")
                    if stream is not None:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        stream = None
                        self._play_stream = None
        except Exception as e:
            print(f"[ALICE] ❌ Play error: {e}")
        finally:
            self.set_speaking(False)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                self._play_stream = None

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing for instant perceived response:
          Phase 1 — immediate greeting (no tools, no fetch) → Alice speaks in <2s
          Phase 2 — news fetched in background (turned off for now)
        """
        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── memory ───────────────────────────────────────────────────────────
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")

        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")

        # ── Phase 1: instant greeting — zero data needed ──────────────────────
        import random
        greetings_pool = [
            "Cheerful / Friendly Peer style: Speak in a very warm, casual, and smiley tone. Use casual terms like 'nih', 'deh', 'yuk', 'ya'. Choose pronouns 'aku' and 'kamu'. Example: 'Halo Ham! Selamat pagi/siang. Udah jam {time_str} nih, hari ini ada project seru apa yang mau kita garap bareng?'",
            "Casual Developer Buddy style: Speak like an active coder buddy. Keep it relaxed, using tech slang. Choose pronouns 'aku' and 'kamu'. Example: 'Oy Ham! Sistem ALICE udah up nih pukul {time_str}. Mau lanjut ngoding atau debug apa kita hari ini? Gas lah!'",
            "Warm / Caring Helper style: Speak gently and politely but fully casual. Choose pronouns 'aku' and 'kamu'. Example: 'Halo Ham, selamat pagi/siang/sore. Semoga hari kamu lancar ya. Aku udah online di jam {time_str} nih, siap nemenin kamu ngoding hari ini.'",
            "Sleek Tech Companion style: Clean, quick, modern but casual. Choose pronouns 'aku' and 'kamu'. Example: 'Sistem online, Ham. Pukul {time_str}, all modules are running. Mau lanjutin codingan yang mana nih?'",
            "Playful / High Energy style: Express excitement and positive vibes. Choose pronouns 'aku' and 'kamu'. Example: 'Halo Ham! Ketemu lagi kita. Pas banget udah jam {time_str}, yuk kita bikin sesuatu yang keren hari ini! Ada code yang mau dieksekusi?'",
        ]
        chosen_style = random.choice(greetings_pool).format(time_str=time_str)

        p1_lines = [
            "[STARTUP_GREETING] Greet the user immediately and naturally.",
            "Identity: You are A.L.I.C.E, a friendly female AI assistant companion.",
            f"Current time: {time_str}.",
            "Strict Guideline: Use pronouns 'aku' (for yourself) and 'kamu' (for the user) ONLY. Never use formal terms like 'saya', 'Anda', or formal templates. Speak in extremely casual, natural, and friendly Indonesian Ragam Santai (casual Indonesian mixed with English tech terms), just like a real human coworker/friend.",
            f"Style constraint to adopt: {chosen_style}",
            "- Mention the time/hour naturally as shown in the style.",
            "- Keep it natural and simple, do NOT add generic questions like 'Ada yang bisa kubantu lagi?' or 'Ada yang mau dibantu?' at the end.",
            "- Keep it brief (1-2 sentences max).",
            "- Do NOT call any tools. Do NOT say [STARTUP_GREETING].",
            "- Respond in "
            + (f"language: {lang}." if lang else "Indonesian Ragam Santai (casual Indonesian mixed with tech terms)."),
        ]
        if name:
            p1_lines.append(f"- Address the user as {name} (or 'Ham').")

        await self.session.send_realtime_input(
            text='\n'.join(p1_lines)
        )
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fetch news in background (turned off as requested) ───────
        # async def _guarded_news():
        #     try:
        #         await self._briefing_news_phase(lang)
        #     except Exception as e:
        #         print(f"[Briefing] Phase 2 error: {e}")
        #         self.ui.write_log(f"SYS: Briefing news phase failed: {e}")
        # asyncio.create_task(_guarded_news())

    async def _briefing_news_phase(self, lang: str) -> None:
        """
        Fetches headlines (DDG → Gemini fallback), shows them on screen,
        then injects a short 2-headline summary into the Live session.
        Waits enough time for the phase-1 greeting to finish playing first.
        """
        from actions.web_search import _ddg_search, _gemini_headlines

        fetch_start           = asyncio.get_event_loop().time()
        headlines: list[str]  = []
        full_news             = ""

        # 1) DDG — ~0.6 s when available
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(_ddg_search, "world news today", 6),
                timeout=4.0,
            )
            if results:
                headlines = [r["title"] for r in results if r.get("title")][:6]
                full_news = "\n\n".join(
                    f"• {r.get('title','')}\n  {r.get('snippet','')}\n  {r.get('url','')}"
                    for r in results
                )
        except Exception as e:
            print(f"[Briefing] DDG: {e}")

        # 2) Gemini grounded search — reliable fallback
        if not headlines:
            try:
                headlines, full_news = await asyncio.wait_for(
                    asyncio.to_thread(_gemini_headlines, 5),
                    timeout=8.0,
                )
            except Exception as e:
                print(f"[Briefing] Gemini headlines: {e}")

        # Show full list on screen immediately when data arrives
        if full_news:
            self.ui.show_content("NEWS — latest headlines", full_news)

        if not headlines or not self.session:
            return

        # Ensure the phase-1 greeting (≈ 3 s of speech) has finished before we speak again
        elapsed       = asyncio.get_event_loop().time() - fetch_start
        wait_more     = max(0.0, 3.5 - elapsed)
        if wait_more > 0:
            await asyncio.sleep(wait_more)

        if not self.session:
            return

        headlines_text = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        p2_lines = [
            "[BRIEFING_NEWS] Today's headlines are already displayed on screen.",
            "Data:",
            headlines_text,
            "",
            "Voice rules:",
            "- Mention ONLY 2 headlines — one short sentence each.",
            "- Tell the user the full list is visible on screen.",
            "- Do NOT ask if they need anything, do NOT use any generic/repetitive questions at the end.",
            "- Do NOT say [BRIEFING_NEWS].",
            "- Respond in "
            + (f"language: {lang}." if lang else "the user's language."),
        ]

        await self.session.send_realtime_input(
            text='\n'.join(p2_lines)
        )
        self.ui.write_log("SYS: Briefing phase 2 (news) sent.")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if alert and self.session:
                try:
                    await self.session.send_realtime_input(
                        text=alert
                    )
                except Exception as e:
                    print(f"[Monitor] ⚠️ Could not send alert: {e}")

    async def _idle_watchdog(self) -> None:
        """Watchdog to sleep the live session after 5 minutes of inactivity."""
        import time
        while True:
            await asyncio.sleep(10)
            if self.session:
                now = time.time()
                with self._speaking_lock:
                    speaking = self._is_speaking
                elapsed = now - max(self._last_voice_time, self._last_activity_time)
                # If idle for 5 mins (300s) and not speaking, put session to sleep
                if elapsed > 300.0 and not speaking:
                    print(f"[ALICE] Idle for {int(elapsed)}s. Disconnecting session to conserve API quota.")
                    self.ui.write_log("SYS: Standby mode (idle). Alt+Space or unmute/text to wake up.")
                    if self._wake_event:
                        self._wake_event.clear()
                    try:
                        await self.session.close()
                    except Exception:
                        pass

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                self._wake_up()
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_realtime_input(
                        text=text
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._wake_event = asyncio.Event()
        self._wake_event.set()

        # Start Hermes Daemon first so Custom MCP can fetch tools from it
        await self._start_hermes_daemon()

        # Fetch BrowserOS, VS Code, and Custom MCP tools on startup
        self.mcp_tools = []
        try:
            browser_tools = await fetch_browseros_mcp_tools()
            self.mcp_tools.extend(browser_tools)
            self.browseros_tool_names = {t["name"] for t in browser_tools}
        except Exception as e:
            print(f"[ALICE] Failed fetching BrowserOS MCP tools: {e}")
            self.browseros_tool_names = set()

        try:
            vscode_tools = await fetch_vscode_mcp_tools()
            self.mcp_tools.extend(vscode_tools)
            self.vscode_tool_names = {t["name"] for t in vscode_tools}
        except Exception as e:
            print(f"[ALICE] Failed fetching VS Code MCP tools: {e}")
            self.vscode_tool_names = set()

        try:
            custom_tools = await fetch_custom_mcp_tools()
            self.mcp_tools.extend(custom_tools)
            self.custom_tool_names = {t["name"] for t in custom_tools}
        except Exception as e:
            print(f"[ALICE] Failed fetching Custom MCP tools: {e}")
            self.custom_tool_names = set()

        self._api_keys = self._load_all_api_keys()
        if not self._api_keys:
            try:
                self._api_keys = [_get_api_key()]
            except Exception:
                self._api_keys = []
        self._current_key_idx = 0

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        while True:
            try:
                await self._wake_event.wait()

                if not self._api_keys:
                    self._api_keys = self._load_all_api_keys()
                    if not self._api_keys:
                        try:
                            self._api_keys = [_get_api_key()]
                        except Exception:
                            self._api_keys = []
                    if not self._api_keys:
                        print("[ALICE] No API keys available. Sleeping 5s...")
                        await asyncio.sleep(5)
                        continue

                self._current_key_idx = self._current_key_idx % len(self._api_keys)
                active_key = self._api_keys[self._current_key_idx]

                print(f"[ALICE] Using API Key index {self._current_key_idx} (Ends with ...{active_key[-6:] if len(active_key) > 6 else ''})")

                client = genai.Client(
                    api_key=active_key,
                    http_options={"api_version": "v1beta"},
                    use_direct_google=True
                )

                # Try to load live_model override from config
                live_model = LIVE_MODEL
                try:
                    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        live_model = cfg.get("live_model", live_model)
                except Exception:
                    pass

                print(f"[ALICE] Connecting to {live_model}...")
                self.ui.set_state("THINKING")

                # Dynamic parallel fetch of MCP tools upon each connection attempt
                try:
                    results = await asyncio.gather(
                        fetch_browseros_mcp_tools(),
                        fetch_vscode_mcp_tools(),
                        fetch_custom_mcp_tools(),
                        return_exceptions=True
                    )
                    
                    self.mcp_tools = []
                    
                    browser_tools = results[0] if not isinstance(results[0], Exception) else []
                    self.mcp_tools.extend(browser_tools)
                    self.browseros_tool_names = {t["name"] for t in browser_tools}
                    if isinstance(results[0], Exception):
                        print(f"[ALICE] Failed fetching BrowserOS MCP tools: {results[0]}")
                        
                    vscode_tools = results[1] if not isinstance(results[1], Exception) else []
                    self.mcp_tools.extend(vscode_tools)
                    self.vscode_tool_names = {t["name"] for t in vscode_tools}
                    if isinstance(results[1], Exception):
                        print(f"[ALICE] Failed fetching VS Code MCP tools: {results[1]}")
                        
                    custom_tools = results[2] if not isinstance(results[2], Exception) else []
                    self.mcp_tools.extend(custom_tools)
                    self.custom_tool_names = {t["name"] for t in custom_tools}
                    if isinstance(results[2], Exception):
                        print(f"[ALICE] Failed fetching Custom MCP tools: {results[2]}")
                except Exception as mcp_err:
                    print(f"[ALICE] Error in dynamic MCP gather on connection: {mcp_err}")

                config = self._build_config()

                connection_established = False
                async with (
                    client.aio.live.connect(model=live_model, config=config) as session,
                    TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()
                    self._turn_count      = 0

                    import time
                    self._last_activity_time = time.time()
                    self._last_voice_time = 0.0

                    print("[ALICE] Connected.")
                    connection_established = True
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: ALICE online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._idle_watchdog())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

                    # Morning briefing — fires once per process launch
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except Exception as e:
                if not connection_established and getattr(self, "_session_resumption_handle", None):
                    print(f"[ALICE] Resumption handshake failed. Clearing handle: {e}")
                    self._session_resumption_handle = None

                is_normal = False
                is_api_error = False
                try:
                    from google.genai import errors as gerrors
                    if isinstance(e, gerrors.APIError) or "RESOURCE_EXHAUSTED" in str(e) or "API_KEY_INVALID" in str(e):
                        is_api_error = True
                except Exception:
                    pass
                
                if is_api_error or "quota" in str(e).lower() or "limit" in str(e).lower() or "key" in str(e).lower() or "unauthorized" in str(e).lower() or "forbidden" in str(e).lower():
                    if self._api_keys:
                        self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
                        print(f"[ALICE] API error or rate limit hit. Rotating to key index {self._current_key_idx}...")

                try:
                    import websockets
                    from google.genai import errors as gerrors
                    
                    def check_normal(exc):
                        if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                            return True
                        if isinstance(exc, websockets.exceptions.ConnectionClosedOK):
                            return True
                        if isinstance(exc, gerrors.APIError) and exc.code == 1000:
                            return True
                        if exc.__class__.__name__ in ("BaseExceptionGroup", "ExceptionGroup"):
                            return all(check_normal(sub) for sub in exc.exceptions)
                        return False
                    
                    if check_normal(e):
                        is_normal = True
                except Exception:
                    pass

                if is_normal:
                    print("[ALICE] Session closed normally.")
                else:
                    print(f"[ALICE] Error: {e}")
                    traceback.print_exc()
            finally:
                self.session = None

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            print("[ALICE] Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()