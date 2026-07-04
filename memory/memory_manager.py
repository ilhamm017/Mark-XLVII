import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys
import os
import re
import requests

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR         = get_base_dir()
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

def get_user_name() -> str:
    user_name = "ilham"
    try:
        base_dir = get_base_dir()
        config_path = base_dir / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                user_name = cfg.get("user_name", "ilham").lower().strip()
    except Exception:
        pass
    return user_name

def get_honcho_peer_id() -> str:
    try:
        base_dir = get_base_dir()
        config_path = base_dir / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                val = cfg.get("honcho_peer_name")
                if val:
                    return str(val).strip()
    except Exception:
        pass

    # Try HERMES_HOME env var
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        p = Path(hermes_home) / "honcho.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get("peer_name", "760143518")
            except Exception:
                pass

    # Try local project .hermes directory
    p = Path(BASE_DIR) / ".hermes" / "honcho.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f).get("peer_name", "760143518")
        except Exception:
            pass

    # Try AppData/Local/hermes/honcho.json
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "hermes" / "honcho.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get("peer_name", "760143518")
            except Exception:
                pass
    
    # Try ~/.hermes/honcho.json
    home = os.path.expanduser("~")
    p = Path(home) / ".hermes" / "honcho.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f).get("peer_name", "760143518")
        except Exception:
            pass

    return "760143518"

def get_honcho_url() -> str:
    try:
        base_dir = get_base_dir()
        config_path = base_dir / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                val = cfg.get("honcho_base_url")
                if val:
                    return str(val).strip().rstrip("/")
    except Exception:
        pass

    base_url = "http://192.168.0.102:8000"
    
    paths_to_check = []
    
    # Try HERMES_HOME env var or local project .hermes directory first
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        paths_to_check.append(Path(hermes_home) / "honcho.json")
        paths_to_check.append(Path(hermes_home) / "config.yaml")
        
    paths_to_check.append(Path(BASE_DIR) / ".hermes" / "honcho.json")
    paths_to_check.append(Path(BASE_DIR) / ".hermes" / "config.yaml")
    
    # Try AppData/Local/hermes/honcho.json or config.yaml fallback
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths_to_check.append(Path(appdata) / "hermes" / "honcho.json")
        paths_to_check.append(Path(appdata) / "hermes" / "config.yaml")
    
    home = os.path.expanduser("~")
    paths_to_check.append(Path(home) / ".hermes" / "honcho.json")
    paths_to_check.append(Path(home) / ".hermes" / "config.yaml")
    
    for p in paths_to_check:
        if p.exists():
            try:
                if p.suffix == ".json":
                    with open(p, "r", encoding="utf-8") as f:
                        val = json.load(f).get("baseUrl") or json.load(f).get("base_url")
                        if val:
                            base_url = val
                            break
                elif p.suffix in (".yaml", ".yml"):
                    import yaml
                    with open(p, "r", encoding="utf-8") as f:
                        val = yaml.safe_load(f).get("honcho", {}).get("base_url")
                        if val:
                            base_url = val
                            break
            except Exception:
                pass
                
    base_url = base_url.rstrip("/")
    # Ping-test the resolved base_url, fallback to Tailscale IP if unreachable
    try:
        res = requests.get(f"{base_url}/health", timeout=1.5)
        if res.status_code == 200:
            return base_url
    except Exception:
        pass
        
    ts_url = "http://100.69.16.104:8000"
    try:
        res = requests.get(f"{ts_url}/health", timeout=1.5)
        if res.status_code == 200:
            return ts_url
    except Exception:
        pass
        
    return base_url

def get_honcho_workspace() -> str:
    try:
        base_dir = get_base_dir()
        config_path = base_dir / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                val = cfg.get("honcho_workspace")
                if val:
                    return str(val).strip()
    except Exception:
        pass
    return "hermes"

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    base_url = get_honcho_url()
    peer_id = get_honcho_peer_id()
    workspace = get_honcho_workspace()
    
    data = _empty_memory()
    
    with _lock:
        try:
            url = f"{base_url}/v3/workspaces/{workspace}/peers/{peer_id}/card"
            res = requests.get(url, timeout=3.0)
            if res.status_code == 200:
                card_data = res.json()
                peer_card = card_data.get("peer_card") or []
                
                for chunk in peer_card:
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    match = re.match(r"^Category\s+\[([^\]]+)\]\s+([^:]+):\s*(.*)$", chunk, re.IGNORECASE)
                    if match:
                        cat = match.group(1).strip()
                        key = match.group(2).strip()
                        val = match.group(3).strip()
                        
                        if cat not in data:
                            data[cat] = {}
                        data[cat][key] = {"value": val}
                    else:
                        words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', '', chunk).split() if w]
                        if words:
                            key = "_".join(words[:3]).lower()
                            data["notes"][key] = {"value": chunk}
                return data
        except Exception as e:
            print(f"[Memory] ⚠️ Load error from Honcho ({base_url}): {e}")
            
    return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries

def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    
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
                
    base_url = get_honcho_url()
    peer_id = get_honcho_peer_id()
    workspace = get_honcho_workspace()
    
    with _lock:
        try:
            url = f"{base_url}/v3/workspaces/{workspace}/peers/{peer_id}/card"
            res = requests.put(url, json={"peer_card": facts}, timeout=3.0)
            if res.status_code != 200:
                print(f"[Memory] ⚠️ Save to Honcho returned status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[Memory] ⚠️ Save error to Honcho ({base_url}): {e}")

def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val

def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed

def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved to Honcho: {list(memory_update.keys())}")
    return memory

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"

def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"

forget_memory = forget