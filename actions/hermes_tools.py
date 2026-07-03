#hermes_tools.py
import os
import sys
import re
import fnmatch
import platform
import urllib.request
from pathlib import Path

# Safe path check similar to file_controller
_OS = platform.system()
_SAFE_ROOTS: list[Path] = [Path.home()]

if _OS == "Windows":
    try:
        import psutil
        for part in psutil.disk_partitions():
            mount = part.mountpoint
            if mount and mount.upper() != "C:\\":
                _SAFE_ROOTS.append(Path(mount))
    except Exception:
        for drive in ["D:\\", "E:\\", "R:\\", "X:\\", "Y:\\", "Z:\\"]:
            if Path(drive).exists():
                _SAFE_ROOTS.append(Path(drive))

def _is_safe_path(target: Path) -> bool:
    try:
        resolved = target.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False

def _resolve_path(raw: str) -> Path:
    shortcuts = {
        "desktop": Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "home": Path.home(),
    }
    lower = raw.strip().lower()
    if lower in shortcuts:
        return shortcuts[lower]
    return Path(raw).expanduser()

def read_file(path: str, offset: int = 1, limit: int = 500) -> str:
    """Reads a file with line numbers and pagination (offset & limit)."""
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target}"
        if not target.is_file():
            return f"Not a file: {target}"
            
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        start_idx = max(0, offset - 1)
        end_idx = min(total_lines, start_idx + limit)
        
        output = []
        for idx in range(start_idx, end_idx):
            output.append(f"{idx + 1}|{lines[idx]}")
            
        if not output:
            return f"No lines to read within offset={offset} and limit={limit}. Total lines: {total_lines}."
            
        header = f"--- File: {target.name} (Lines {start_idx+1}-{end_idx} of {total_lines}) ---\n"
        footer = f"\n--- End of Page (Total lines: {total_lines}) ---"
        return header + "".join(output) + footer
    except Exception as e:
        return f"Error reading file: {e}"

def patch_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replaces old_string with new_string in the file."""
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target}"
            
        content = target.read_text(encoding="utf-8", errors="ignore")
        
        occ = content.count(old_string)
        if occ == 0:
            return "Error: old_string not found in file. Make sure of exact whitespace/indentation."
        if occ > 1 and not replace_all:
            return f"Error: old_string found {occ} times. Set replace_all=True or add context lines."
            
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            
        target.write_text(new_content, encoding="utf-8")
        return f"Successfully patched {target.name}. Replaced {occ if replace_all else 1} occurrence(s)."
    except Exception as e:
        return f"Error patching file: {e}"

def search_file_content(pattern: str, target: str = "content", path: str = ".", file_glob: str = None, limit: int = 50) -> str:
    """Searches file names or file contents in a directory."""
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"
            
        results = []
        target = target.lower().strip()
        
        if target == "files":
            search_terms = re.split(r'[-_\s]+', pattern.lower().strip())
            for p in search_path.rglob("*"):
                if p.is_file():
                    p_name_lower = p.name.lower()
                    if all(term in p_name_lower for term in search_terms if term):
                        if file_glob and not fnmatch.fnmatch(p.name, file_glob):
                            continue
                        size = p.stat().st_size
                        results.append(f"📄 {p.relative_to(search_path)} ({size} bytes)")
                        if len(results) >= limit:
                            break
        else:
            glob_pat = file_glob or "*"
            regex = re.compile(pattern, re.IGNORECASE)
            
            for p in search_path.rglob(glob_pat):
                if not p.is_file():
                    continue
                if p.suffix.lower() in ['.png', '.jpg', '.exe', '.zip', '.pdf', '.pyc']:
                    continue
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f):
                            if regex.search(line):
                                results.append(f"{p.relative_to(search_path)}:{idx+1}: {line.strip()}")
                                if len(results) >= limit:
                                    break
                except Exception:
                    continue
                if len(results) >= limit:
                    break
                    
        if not results:
            return "No matches found."
        return "\n".join(results)
    except Exception as e:
        return f"Error searching files: {e}"

def web_extract(url: str) -> str:
    """Extracts text content from a web page and returns it in a readable format."""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            for script in soup(["script", "style", "meta", "noscript", "header", "footer"]):
                script.decompose()
                
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            title = soup.title.string if soup.title else "No Title"
            return f"--- URL: {url} ---\nTitle: {title}\n\n{text[:6000]}"
        except ImportError:
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            title = title_match.group(1) if title_match else "No Title"
            
            text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return f"--- URL: {url} (Regex Parse Fallback) ---\nTitle: {title}\n\n{text[:6000]}"
            
    except Exception as e:
        return f"Error extracting webpage: {e}"

def hermes_tools(parameters: dict = None, player=None) -> str:
    """Dispatcher function for Hermes-emulated tools."""
    params = parameters or {}
    tool = params.get("tool", "").lower().strip()
    
    if player:
        player.write_log(f"[hermes_tools] Running tool: {tool}")
        
    try:
        if tool == "read_file":
            return read_file(
                path=params.get("path", ""),
                offset=int(params.get("offset", 1)),
                limit=int(params.get("limit", 500))
            )
        elif tool == "patch_file":
            return patch_file(
                path=params.get("path", ""),
                old_string=params.get("old_string", ""),
                new_string=params.get("new_string", ""),
                replace_all=bool(params.get("replace_all", False))
            )
        elif tool == "search_file_content":
            return search_file_content(
                pattern=params.get("pattern", ""),
                target=params.get("target", "content"),
                path=params.get("path", "."),
                file_glob=params.get("file_glob"),
                limit=int(params.get("limit", 50))
            )
        elif tool == "web_extract":
            return web_extract(url=params.get("url", ""))
        else:
            return f"Unknown hermes tool: '{tool}'"
    except Exception as e:
        return f"Hermes tool error ({tool}): {e}"
