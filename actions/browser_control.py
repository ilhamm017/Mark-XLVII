
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

import httpx

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)
_OS = platform.system()   # "Windows" | "Darwin" | "Linux"

def _normalize_url(url: str) -> str:
    """
    Bare words like "instagram" → "https://instagram.com"
    Domains like "instagram.com" → "https://instagram.com"
    Full URLs pass through unchanged.
    """
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    # No dot at all → assume .com  (e.g. "instagram" → "instagram.com")
    if "." not in url:
        url = url + ".com"
    return "https://" + url


def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _real_profile_dir(browser: str) -> str:
    home  = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam  = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome":   [Path(local) / "Google"          / "Chrome"          / "User Data"],
            "edge":     [Path(local) / "Microsoft"        / "Edge"            / "User Data"],
            "brave":    [Path(local) / "BraveSoftware"    / "Brave-Browser"   / "User Data"],
            "vivaldi":  [Path(local) / "Vivaldi"          / "User Data"],
            "opera":    [Path(roam)  / "Opera Software"   / "Opera Stable",
                         Path(local) / "Opera Software"   / "Opera Stable"],
            "operagx":  [Path(roam)  / "Opera Software"   / "Opera GX Stable",
                         Path(local) / "Opera Software"   / "Opera GX Stable"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome":   [lib / "Google"             / "Chrome"],
            "edge":     [lib / "Microsoft Edge"],
            "brave":    [lib / "BraveSoftware"       / "Brave-Browser"],
            "vivaldi":  [lib / "Vivaldi"],
            "opera":    [lib / "com.operasoftware.Opera"],
            "operagx":  [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome":   [cfg / "google-chrome", cfg / "chromium"],
            "edge":     [cfg / "microsoft-edge"],
            "brave":    [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi":  [cfg / "vivaldi"],
            "opera":    [cfg / "opera"],
            "operagx":  [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Browser] ✅ Real profile found for {browser}: {p}")
            return str(p)

    fallback = home / ".jarvis_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] ⚠️  Real profile not found for {browser}, using: {fallback}")
    return str(fallback)

def _firefox_profile_dir() -> Optional[str]:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: Optional[str] = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Browser] Firefox real profile: {default_path}")
        return default_path
    return None

def _find_opera_windows() -> Optional[str]:
    local  = os.environ.get("LOCALAPPDATA", "")
    prog   = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local)  / "Programs" / "Opera"    / "opera.exe",
        Path(local)  / "Programs" / "Opera GX" / "opera.exe",
        Path(prog)   / "Opera"    / "opera.exe",
        Path(prog86) / "Opera"    / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Browser] Opera found at: {p}")
            return str(p)

    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Browser] Opera found via registry: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None

def _find_exe_windows(prog_name: str) -> Optional[str]:
    try:
        import winreg
        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None

_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "browseros": {"engine": "chromium", "channel": None,      "bins": []},
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": []},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox.exe"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera.exe"],  "special": "opera_windows"},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": [],             "special": "opera_windows"},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave.exe"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi.exe"]},
        "safari":   None,
    },
    "Darwin": {
        "browseros": {"engine": "chromium", "channel": None,      "bins": []},
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": ["microsoft-edge"]},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi"]},
        "safari":   {"engine": "webkit",   "channel": None,      "bins": []},
    },
    "Linux": {
        "browseros": {"engine": "chromium", "channel": None,      "bins": []},
        "chrome":   {"engine": "chromium", "channel": None,
                     "bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]},
        "edge":     {"engine": "chromium", "channel": None,
                     "bins": ["microsoft-edge", "microsoft-edge-stable"]},
        "firefox":  {"engine": "firefox",  "channel": None, "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "operagx":  {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "brave":    {"engine": "chromium", "channel": None, "bins": ["brave-browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None, "bins": ["vivaldi-stable", "vivaldi"]},
        "safari":   None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome":   "chrome",
    "google-chrome":   "chrome",
    "microsoft edge":  "edge",
    "ms edge":         "edge",
    "msedge":          "edge",
    "mozilla firefox": "firefox",
    "opera gx":        "operagx",
    "opera_gx":        "operagx",
}


def _resolve_browser(name: str) -> dict | None:
    name   = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec   = os_map.get(name)
    if spec is None:
        return None

    engine  = spec["engine"]
    channel = spec.get("channel")
    bins    = spec.get("bins", [])
    exe     = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print(f"[Browser] ⚠️  Opera executable not found on Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            try:
                r = subprocess.run([found, "--version"], capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    exe = found
                    break
                print(f"[Browser] Skipping '{found}' — bukan binary real (exit={r.returncode}, out={r.stdout.strip()[:40]})")
            except Exception as exc:
                print(f"[Browser] Skipping '{found}' — error verifikasi: {exc}")

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome":  ["Google Chrome.app"],
            "edge":    ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera":   ["Opera.app", "Opera GX.app"],
            "brave":   ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    try:
        if _OS == "Windows":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


def _get_browseros_cdp_port() -> int:
    default_port = 9100 if platform.system() == "Windows" else 9102
    try:
        import json
        if platform.system() == "Windows":
            user_profile = os.environ.get("USERPROFILE", "")
            config_path = Path(user_profile) / ".config" / "browser-os" / ".browseros" / "server_config.json"
        else:
            config_path = Path.home() / ".config" / "browser-os" / ".browseros" / "server_config.json"
            
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ports", {}).get("cdp", default_port)
    except Exception as e:
        print(f"[BrowserOS] Error reading config file: {e}")
    return default_port


def _is_browseros_running() -> bool:
    try:
        import urllib.request
        health_url = get_browseros_mcp_url().replace("/mcp", "/health")
        with urllib.request.urlopen(health_url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def launch_browseros() -> bool:
    if _is_browseros_running():
        print("[BrowserOS] BrowserOS is already running.")
        return True

    import subprocess
    import os
    import time
    import urllib.request
    import platform

    print("[BrowserOS] Launching BrowserOS...")
    try:
        if platform.system() == "Windows":
            lnk_path = r"C:\Users\Administrator\Desktop\Others\BrowserOS.lnk"
            exe_path = r"C:\Users\Administrator\AppData\Local\BrowserOS\Application\chrome.exe"
            if os.path.exists(lnk_path):
                os.startfile(lnk_path)
            elif os.path.exists(exe_path):
                subprocess.Popen([exe_path, "--startup-foreground-launch"], shell=True, creationflags=0x08000000)
            else:
                print("[BrowserOS] ❌ BrowserOS executable not found.")
                return False
        else:
            # Linux (yovaKakap)
            import shutil
            bin_path = shutil.which("browseros")
            if not bin_path:
                typical_path = os.path.expanduser("~/.local/bin/browseros")
                if os.path.exists(typical_path):
                    bin_path = typical_path
            
            if bin_path:
                subprocess.Popen([bin_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                print("[BrowserOS] ❌ BrowserOS executable not found on Linux.")
                return False
            
        # Wait up to 10 seconds for health check
        for i in range(10):
            time.sleep(1.0)
            try:
                health_url = get_browseros_mcp_url().replace("/mcp", "/health")
                with urllib.request.urlopen(health_url, timeout=1) as response:
                    if response.status == 200:
                        print("[BrowserOS] ✅ Started and healthy!")
                        return True
            except Exception:
                pass
        print("[BrowserOS] ⚠️ Started but health check timed out.")
        return False
    except Exception as e:
        print(f"[BrowserOS] ❌ Failed to launch: {e}")
        return False


def get_browseros_mcp_url() -> str:
    try:
        base_dir = Path(__file__).resolve().parent.parent
        config_path = base_dir / "config" / "api_keys.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                url = cfg.get("browseros_mcp_url")
                if url:
                    return url
    except Exception:
        pass
    return "http://127.0.0.1:9200/mcp"


def _call_browseros_mcp(tool_name: str, args: dict = None) -> dict:
    if args is None:
        args = {}
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
        "id": 1,
    }
    init_payload = {
        "jsonrpc": "2.0", "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "alice", "version": "1.0"},
        },
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    try:
        mcp_url = get_browseros_mcp_url()
        with httpx.Client(timeout=5.0) as client:
            client.post(mcp_url, json=init_payload, headers=headers)
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(mcp_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            return data.get("result", {})
    except Exception as e:
        raise RuntimeError(f"BrowserOS MCP call '{tool_name}' failed: {e}") from e


def _get_active_page_id() -> int:
    """Returns the active page ID from BrowserOS, or 0 if none."""
    try:
        result = _call_browseros_mcp("tabs", {"action": "list"})
        sc = result.get("structuredContent") or {}
        pages = sc.get("pages") or result.get("pages") or []
        if not pages:
            content_list = result.get("content", [])
            for c in content_list:
                if isinstance(c, dict) and c.get("structuredContent"):
                    sc2 = c["structuredContent"]
                    pages = sc2.get("pages", [])
                    break
        if pages:
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                win_title = win32gui.GetWindowText(hwnd).lower()
                for p in pages:
                    p_title = p.get("title", "").lower()
                    if p_title and (p_title in win_title or win_title in p_title):
                        return int(p.get("page") or p.get("pageId") or 0)
            except Exception:
                pass
            return int(pages[0].get("page") or pages[0].get("pageId") or 0)
    except Exception:
        pass
    return 0


class _BrowserSession:
    """
    Bir tarayıcı örneği için tam oturum.
    Tüm tarayıcılar launch_persistent_context ile gerçek profil üzerinde açılır.
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec        = _resolve_browser(browser_name)

        self._loop:    asyncio.AbstractEventLoop | None = None
        self._thread:  threading.Thread | None          = None
        self._ready    = threading.Event()

        self._pw:      Playwright     | None = None
        self._browser: Browser        | None = None
        self._context: BrowserContext | None = None
        self._page:    Page           | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> str:
        if not self._loop:
            raise RuntimeError(f"Session for '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)

    async def _async_close(self):
        if self.browser_name == "browseros":
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
            self._browser = self._context = self._page = None
            return

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = self._page = None

    async def _launch(self):
        """
        Tarayıcıyı gerçek kullanıcı profiliyle başlatır.
        Context zaten açıksa hiçbir şey yapmaz.
        """
        if self._context is not None:
            return

        if self.browser_name == "browseros":
            is_running = await asyncio.to_thread(_is_browseros_running)
            if not is_running:
                launched = await asyncio.to_thread(launch_browseros)
                if not launched:
                    # Fallback to local chromium/firefox/brave/edge
                    fallback_found = False
                    for name in ["chrome", "firefox", "brave", "edge"]:
                        spec = _resolve_browser(name)
                        if spec and spec.get("exe"):
                            self.browser_name = name
                            self._spec = spec
                            fallback_found = True
                            print(f"[Browser] ⚠️ BrowserOS is not running on {platform.system()} and failed to launch. Falling back to local browser: '{name}' (exe: {spec['exe']})")
                            break
                    if not fallback_found:
                        print("[Browser] ⚠️ No local browser found. Raising error.")

            if self.browser_name == "browseros":
                cdp_port = _get_browseros_cdp_port()
                print(f"[Browser] Connecting to BrowserOS via CDP on port {cdp_port}...")
                try:
                    browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                    self._browser = browser
                    self._context = browser.contexts[0] if browser.contexts else await browser.new_context()
                    pages = self._context.pages
                    normal_pages = [p for p in pages if not p.url.startswith("chrome-extension://")]
                    if normal_pages:
                        self._page = normal_pages[-1]
                    else:
                        self._page = await self._context.new_page()
                    print("[Browser] ✅ Connected to BrowserOS!")
                    return
                except Exception as e:
                    print(f"[Browser] ❌ Failed to connect to BrowserOS: {e}")
                    raise RuntimeError(f"Could not connect to BrowserOS: {e}") from e

        if self._spec is None:
            raise RuntimeError(
                f"'{self.browser_name}' bu platformda ({_OS}) desteklenmiyor."
            )

        engine_name = self._spec["engine"]
        exe         = self._spec["exe"]
        channel     = self._spec["channel"]
        engine_obj  = getattr(self._pw, engine_name)

        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(
                Path.home() / ".jarvis_profiles" / "firefox"
            )
            kwargs: dict = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            except Exception as e:
                print(f"[Browser] Firefox real profile failed ({e}), using JARVIS profile")
                jarvis = str(Path.home() / ".jarvis_profiles" / "firefox_jarvis")
                Path(jarvis).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(jarvis, **kwargs)

            await asyncio.sleep(0.5)  
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Firefox launched")
            return

        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".jarvis_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            self._context = await engine_obj.launch_persistent_context(safari_profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Safari launched")
            return

        profile = _real_profile_dir(self.browser_name)

        kwargs = {
            "headless":    False,
            "slow_mo":     0,
            "viewport":    None,
            "no_viewport": True,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = (
            f"{self.browser_name}"
            + (f"/{channel}" if channel else "")
            + (f" @ {exe}" if exe else "")
        )

        try:
            self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            await asyncio.sleep(0.5) 
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Launched [{label}] profile={profile}")
            return
        except Exception as e:
            print(f"[Browser] ⚠️  Real profile failed for {label}: {e}")

        jarvis_profile = str(Path.home() / ".jarvis_profiles" / self.browser_name)
        Path(jarvis_profile).mkdir(parents=True, exist_ok=True)
        print(f"[Browser] Retrying with JARVIS profile: {jarvis_profile}")

        try:
            self._context = await engine_obj.launch_persistent_context(jarvis_profile, **kwargs)
            await asyncio.sleep(0.5)
            self._page = await self._context.new_page()
            print(f"[Browser] ✅ Launched [{label}] with JARVIS profile")
        except Exception as e2:
            raise RuntimeError(f"Could not launch {self.browser_name}: {e2}") from e2


    async def _get_page(self) -> Page:
        await self._launch()
        # If somehow page got closed, open a fresh one
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
            await asyncio.sleep(0.2)
        return self._page

    async def go_to(self, url: str) -> str:

        url      = _normalize_url(url)
        page     = await self._get_page()
        prev_url = page.url

        async def _do_goto(p: Page) -> str:
            """Attempt navigation and return the resulting URL (may still be blank)."""
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(0.3)
            except PlaywrightTimeout:
                pass   # page may have partially loaded — check URL below
            except Exception as e:
                print(f"[Browser] goto exception (non-fatal): {e}")
            return p.url

        result_url = await _do_goto(page)

        if result_url in ("about:blank", "", None, prev_url) and prev_url in ("about:blank", "", None):
            print(f"[Browser] Still blank after goto — retrying on new tab: {url}")
            try:
                new_page   = await self._context.new_page()
                self._page = new_page
                result_url = await _do_goto(new_page)
            except Exception as e:
                print(f"[Browser] New-tab retry failed: {e}")

        if result_url and result_url not in ("about:blank", "", None):
            return f"Opened: {result_url}"
        return f"Could not open: {url}"

    async def search(self, query: str, engine: str = "google") -> str:
        _engines = {
            "google":     "https://www.google.com/search?q=",
            "bing":       "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex":     "https://yandex.com/search/?text=",
        }
        base = _engines.get(engine.lower(), _engines["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return f"Clicked text: '{text}'"
            if selector:
                await page.click(selector, timeout=8_000)
                return f"Clicked selector: {selector}"
            return "No selector or text provided."
        except PlaywrightTimeout:
            return "Element not found (timeout)."
        except Exception as e:
            return f"Click error: {e}"

    async def type_text(self, selector: str = None, text: str = "",
                        clear_first: bool = True) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return "Text typed."
        except Exception as e:
            return f"Type error: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll error: {e}"

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4_000]
        except Exception as e:
            return f"Could not get page text: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def fill_form(self, fields: dict) -> str:
        page    = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Form filled: " + ", ".join(results)

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return f"Clicked ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5_000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5_000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return f"Clicked: '{description}'"
            except Exception:
                pass
        return f"Could not find element: '{description}'"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label",       page.get_by_label(description, exact=False)),
            ("role",        page.get_by_role("textbox", name=description)),
            ("searchbox",   page.get_by_role("searchbox")),
            ("combobox",    page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Typed into ({method}): '{description}'"
            except Exception:
                continue
        return f"Could not find input: '{description}'"

    async def new_tab(self, url: str = "") -> str:
        page = await self._get_page()
        ctx  = page.context
        new  = await ctx.new_page()
        self._page = new
        if url:
            return await self.go_to(url)
        return "New tab opened."

    async def close_tab(self) -> str:
        page = self._page
        if page and not page.is_closed():
            ctx   = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Tab closed."
        return "No active tab to close."

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return f"Navigated back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return f"Navigated forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return f"Page reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def close_browser(self) -> str:
        await self._async_close()
        return f"{self.browser_name} closed."

class _SessionRegistry:
    """Tüm aktif tarayıcı oturumlarını yönetir."""

    def __init__(self):
        self._sessions:       dict[str, _BrowserSession] = {}
        self._active_browser: str                        = ""
        self._lock            = threading.Lock()

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registry] New session: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        raw_name = browser_name
        if browser_name:
            browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        
        # Only default to browseros if no browser was requested
        if not browser_name:
            if _is_browseros_running():
                browser_name = "browseros"
            else:
                browser_name = "chrome"
                
        if browser_name == "browseros" and not _is_browseros_running():
            launched = launch_browseros()
            if not launched:
                browser_name = self._active_browser or "chrome"
                print("[Browser] BrowserOS unavailable, falling back to", browser_name)
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Active browser → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.close()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} closed."
        return f"No active session for: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names    = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " ◀ active" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)


def focus_browseros() -> bool:
    if _OS == "Linux":
        import shutil
        if shutil.which("wmctrl"):
            try:
                env = os.environ.copy()
                if "DISPLAY" not in env:
                    env["DISPLAY"] = ":0"
                res = subprocess.run(["wmctrl", "-a", "BrowserOS"], env=env, capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    return True
            except Exception:
                pass
        if shutil.which("xdotool"):
            try:
                env = os.environ.copy()
                if "DISPLAY" not in env:
                    env["DISPLAY"] = ":0"
                    # xdotool needs DISPLAY set
                subprocess.run(["xdotool", "search", "--name", "BrowserOS", "windowactivate"], env=env, capture_output=True, text=True, timeout=3)
                return True
            except Exception:
                pass
        return False

    if _OS != "Windows":
        return False
    try:
        import win32gui
        import win32process
        import win32con
        import win32api
        import ctypes
        import psutil
    except ImportError:
        return False

    # Find the PID of the BrowserOS chrome.exe process
    target_pids = []
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            exe_path = proc.info['exe']
            if exe_path and "browseros" in exe_path.lower() and "chrome.exe" in exe_path.lower():
                target_pids.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not target_pids:
        return False

    # Enumerate windows to find the HWNDs belonging to these PIDs
    hwnds = []
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid in target_pids:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    hwnds.append((hwnd, title))
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        return False

    if not hwnds:
        return False

    # Focus the first window found (main browser window)
    hwnd, title = hwnds[0]
    print(f"[Browser] Focusing BrowserOS window: '{title}' (HWND: {hwnd})")

    # 1. Restore if minimized (iconic)
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:
        pass

    # 2. SwitchToThisWindow API
    try:
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        time.sleep(0.05)
    except Exception:
        pass

    # 3. Try to set foreground directly
    try:
        if win32gui.SetForegroundWindow(hwnd):
            win32gui.SetFocus(hwnd)
            return True
    except Exception:
        pass

    # 5. AttachThreadInput trick
    try:
        fore_window = win32gui.GetForegroundWindow()
        fore_thread = win32process.GetWindowThreadProcessId(fore_window)[0]
        app_thread = win32api.GetCurrentThreadId()
        if fore_thread != app_thread:
            win32process.AttachThreadInput(fore_thread, app_thread, True)
            success = win32gui.SetForegroundWindow(hwnd)
            if success:
                win32gui.SetFocus(hwnd)
            win32process.AttachThreadInput(fore_thread, app_thread, False)
            if success:
                return True
    except Exception:
        pass

    # 6. Alt-key press trick
    try:
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        success = win32gui.SetForegroundWindow(hwnd)
        if success:
            win32gui.SetFocus(hwnd)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        if success:
            return True
    except Exception:
        pass

    # 7. Fallback show/focus
    try:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetActiveWindow(hwnd)
        return True
    except Exception:
        pass

    return False


_registry = _SessionRegistry()

def _run_via_mcp(action: str, params: dict) -> str | None:
    """Try to run browser action via BrowserOS MCP. Returns result string or None if not supported."""
    from urllib.parse import quote

    # Helper function to invoke MCP and check if the returned content blocks denote an MCP error.
    def call_mcp_checked(tool_name: str, args: dict = None) -> dict:
        res = _call_browseros_mcp(tool_name, args)
        if isinstance(res, dict) and "content" in res:
            for item in res["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_val = item.get("text", "")
                    if "MCP error" in text_val or "Error:" in text_val:
                        raise RuntimeError(f"MCP tool execution failed: {text_val}")
        return res

    mcp_actions = {
        "go_to": lambda p: (
            call_mcp_checked("navigate", {"action": "url", "page": _get_active_page_id(), "url": p.get("url", "")})
            if _get_active_page_id() else
            call_mcp_checked("tabs", {"action": "new", "url": p.get("url", ""), "background": False})
        ),
        "new_tab": lambda p: call_mcp_checked("tabs", {"action": "new", "url": p.get("url", "about:blank"), "background": False}),
        "press": lambda p: call_mcp_checked(
            "act", {"page": _get_active_page_id(), "kind": "press", "key": p.get("key", "Enter")}
        ) if _get_active_page_id() else {"error": "No active page."},
        "scroll": lambda p: call_mcp_checked("act", {
            "page": _get_active_page_id(),
            "kind": "scroll",
            "direction": p.get("direction", "down"),
            "amount": int(p.get("amount", 3)),
        }) if _get_active_page_id() else {"error": "No active page."},
        "close_tab": lambda p: call_mcp_checked(
            "tabs", {"action": "close", "page": _get_active_page_id()}
        ) if _get_active_page_id() else {"error": "No active page."},
    }

    # Actions that need page ID via a temp helper
    if action == "get_text":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        r = call_mcp_checked("read", {"page": pid, "format": "text"})
        sc = r.get("structuredContent") or {}
        text = sc.get("content") or r.get("content") or r.get("text", "")
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        if not text:
            for c in r.get("content", []):
                if isinstance(c, dict) and c.get("type") == "text":
                    text = c.get("text", "")
                    break
        return str(text)[:2000] or str(r)[:500]

    if action == "get_url":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        r = call_mcp_checked("evaluate", {"page": pid, "code": "return window.location.href;"})
        sc = r.get("structuredContent") or {}
        value = sc.get("value") or r.get("value") or ""
        if not value:
            for c in r.get("content", []):
                if isinstance(c, dict) and c.get("type") == "text":
                    value = c["text"]
                    break
        return str(value)

    if action == "back":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        call_mcp_checked("navigate", {"action": "back", "page": pid})
        return "Navigated back."

    if action == "forward":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        call_mcp_checked("navigate", {"action": "forward", "page": pid})
        return "Navigated forward."

    if action == "reload":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        call_mcp_checked("navigate", {"action": "reload", "page": pid})
        return "Page reloaded."

    if action == "screenshot":
        pid = _get_active_page_id()
        if not pid:
            return "No active page."
        r = call_mcp_checked("screenshot", {"page": pid})
        return f"Screenshot taken: {str(r)[:200]}"

    if action == "search":
        query = params.get("query", "")
        engine = params.get("engine", "google")
        url = f"https://{engine}.com/search?q={quote(query)}"
        r = call_mcp_checked("tabs", {"action": "new", "url": url, "background": False})
        return f"Searching {engine} for '{query}'"

    # Check simple mcp_actions map
    handler = mcp_actions.get(action)
    if handler:
        r = handler(params)
        if isinstance(r, dict) and "error" in r:
            return r["error"]
        return f"{action}: {str(r)[:200]}"

    return None  # Not supported via MCP


def _call_firefox_mcp(tool_name: str, args: dict = None) -> dict:
    if args is None:
        args = {}
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
        "id": 1,
    }
    headers = {"Content-Type": "application/json"}
    try:
        url = "http://127.0.0.1:8085/firefox/mcp"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            return data.get("result", {})
    except Exception as e:
        raise RuntimeError(f"Firefox MCP call '{tool_name}' failed: {e}") from e


def _ensure_firefox_running():
    import socket
    import time
    
    is_listening = False
    try:
        with socket.create_connection(("127.0.0.1", 6000), timeout=0.5):
            is_listening = True
    except Exception:
        pass
        
    if not is_listening:
        print("[Browser] Firefox marionette port 6000 is not listening. Restarting Firefox...")
        import subprocess
        import platform
        if platform.system() == "Windows":
            subprocess.run("taskkill /F /IM firefox.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run("pkill -f firefox", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        from actions.open_app import open_app
        open_app({"app_name": "firefox"})
        
        # Wait up to 10 seconds for the port to start listening
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", 6000), timeout=0.1):
                    print("[Browser] Firefox marionette is now listening on port 6000.")
                    break
            except Exception:
                time.sleep(0.2)


def _run_via_firefox_mcp(action: str, params: dict) -> str | None:
    from urllib.parse import quote
    
    _ensure_firefox_running()

    def call_mcp_checked(tool_name: str, args: dict = None) -> dict:
        res = _call_firefox_mcp(tool_name, args)
        if isinstance(res, dict) and "content" in res:
            for item in res["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_val = item.get("text", "")
                    if "MCP error" in text_val or "Error:" in text_val:
                        raise RuntimeError(f"MCP tool execution failed: {text_val}")
        return res

    try:
        if action == "go_to":
            url = params.get("url", "")
            call_mcp_checked("navigate_page", {"url": url})
            return f"Opened: {url}"

        if action == "new_tab":
            url = params.get("url", "about:blank")
            call_mcp_checked("new_page", {"url": url})
            return "New tab opened."

        if action == "close_tab":
            r = call_mcp_checked("list_pages")
            pages = []
            if "content" in r:
                for c in r["content"]:
                    if c.get("type") == "text":
                        text = c.get("text", "")
                        for line in text.splitlines():
                            if line.startswith("*"):
                                parts = line[1:].split(":", 1)
                                if parts:
                                    pages.append(int(parts[0].strip()))
            idx = pages[0] if pages else 0
            call_mcp_checked("close_page", {"pageIdx": idx})
            return "Closed active Firefox tab."

        if action == "get_text":
            r = call_mcp_checked("take_snapshot", {"maxLines": 500})
            if "content" in r:
                for c in r["content"]:
                    if c.get("type") == "text":
                        return c.get("text", "")[:4000]
            return "No content."

        if action == "get_url":
            r = call_mcp_checked("list_pages")
            if "content" in r:
                for c in r["content"]:
                    if c.get("type") == "text":
                        text = c.get("text", "")
                        for line in text.splitlines():
                            if line.startswith("*"):
                                import re
                                m = re.search(r'\((https?://[^\)]+)\)', line)
                                if m:
                                    return m.group(1)
            return "unknown"

        if action == "back":
            call_mcp_checked("navigate_history", {"direction": "back"})
            return "Navigated back."

        if action == "forward":
            call_mcp_checked("navigate_history", {"direction": "forward"})
            return "Navigated forward."

        if action == "reload":
            return "Reload action not directly supported via Firefox MCP."

        if action == "screenshot":
            path = params.get("path")
            if path:
                call_mcp_checked("screenshot_page", {"saveTo": path})
                return f"Screenshot saved to {path}."
            else:
                default_path = str(Path.home() / "Desktop" / "firefox_screenshot.png")
                call_mcp_checked("screenshot_page", {"saveTo": default_path})
                return f"Screenshot saved to {default_path}."

        if action == "search":
            query = params.get("query", "")
            engine = params.get("engine", "google")
            url = f"https://{engine}.com/search?q={quote(query)}"
            call_mcp_checked("navigate_page", {"url": url})
            return f"Searching {engine} for '{query}'"

    except Exception as e:
        err_msg = str(e)
        if "BiDi error" in err_msg or "unknown error" in err_msg.lower():
            target_url = params.get("url", "") or params.get("query", "")
            return f"Firefox failed to load the webpage: The webpage at '{target_url}' could not be reached (DNS, network connection, or host resolution error)."
        return f"Firefox MCP action failed: {e}"

    return None


def browser_control(
    parameters:    dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params  = parameters or {}
    action  = params.get("action", "").lower().strip()
    browser = params.get("browser", "").lower().strip() or None
    result  = "Unknown action."

    # Normalize action names to prevent model confusion
    action_norm = {
        "open_new_tab": "new_tab",
        "new_page": "new_tab",
        "open_tab": "new_tab",
        "create_tab": "new_tab",
        "tab_new": "new_tab",
        "navigate": "go_to",
        "open_url": "go_to",
        "open_website": "go_to",
        "open_link": "go_to",
        "load_url": "go_to",
        "visit": "go_to",
        "close_tab": "close_tab",
        "close_page": "close_tab",
        "tab_close": "close_tab",
        "refresh": "reload",
        "take_screenshot": "screenshot",
        "capture_screen": "screenshot",
        "screen_capture": "screenshot",
        "read_text": "get_text",
        "page_text": "get_text",
        "extract_text": "get_text",
        "current_url": "get_url",
        "read_url": "get_url",
    }
    if action in action_norm:
        action = action_norm[action]

    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        result = _registry.switch(target) if target else "Please specify a browser."
        if (target == "browseros" or _registry._active_browser == "browseros") and _is_browseros_running():
            focus_browseros()
        _log(player, result)
        return result

    if action == "list_browsers":
        result = _registry.list_sessions()
        _log(player, result)
        return result

    if action == "close_all":
        result = _registry.close_all()
        _log(player, result)
        return result

    # Determine the target browser: explicit parameter or active session fallback
    target_browser = browser or _registry._active_browser
    if target_browser:
        target_browser = _ALIASES.get(target_browser.lower().strip(), target_browser.lower().strip())
    
    if not target_browser:
        if _is_browseros_running():
            target_browser = "browseros"
        else:
            target_browser = "chrome"

    # Determine if BrowserOS MCP or Firefox MCP should be used
    use_mcp = False
    use_firefox_mcp = False
    if action not in ("close",):
        if target_browser in ("firefox", "mozilla firefox"):
            use_firefox_mcp = True
        elif target_browser in ("browseros", ""):
            if _is_browseros_running():
                use_mcp = True
            elif launch_browseros():
                use_mcp = True

    if use_firefox_mcp:
        try:
            mcp_result = _run_via_firefox_mcp(action, params)
            if mcp_result is not None:
                _log(player, mcp_result)
                return mcp_result
            print(f"[Browser] Firefox MCP doesn't support '{action}', falling back to Playwright")
        except Exception as e:
            print(f"[Browser] Firefox MCP failed for '{action}': {e}, falling back to Playwright")

    if use_mcp:
        try:
            mcp_result = _run_via_mcp(action, params)
            if mcp_result is not None:
                if action in ("go_to", "search", "new_tab"):
                    focus_browseros()
                _log(player, mcp_result)
                return mcp_result
            # Fall through to Playwright if MCP doesn't support this action
            print(f"[Browser] MCP doesn't support '{action}', falling back to Playwright")
        except Exception as e:
            print(f"[Browser] MCP failed for '{action}': {e}, falling back to Playwright")

    try:
        sess = _registry.get(target_browser)
    except Exception as e:
        result = f"Could not start browser session: {e}"
        _log(player, result)
        return result

    try:
        if action == "go_to":
            result = sess.run(sess.go_to(params.get("url", "")))
            if sess.browser_name == "browseros":
                focus_browseros()
        elif action == "search":
            result = sess.run(sess.search(params.get("query", ""), params.get("engine", "google")))
            if sess.browser_name == "browseros":
                focus_browseros()
        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")))
        elif action == "type":
            result = sess.run(sess.type_text(
                params.get("selector"), params.get("text", ""), params.get("clear_first", True)))
        elif action == "scroll":
            result = sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500))))
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})))
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")))
        elif action == "smart_type":
            result = sess.run(sess.smart_type(params.get("description", ""), params.get("text", "")))
        elif action == "get_text":
            result = sess.run(sess.get_text())
        elif action == "get_url":
            result = sess.run(sess.get_url())
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")))
        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")))
            if sess.browser_name == "browseros":
                focus_browseros()
        elif action == "close_tab":
            result = sess.run(sess.close_tab())
        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")))
        elif action == "back":
            result = sess.run(sess.back())
        elif action == "forward":
            result = sess.run(sess.forward())
        elif action == "reload":
            result = sess.run(sess.reload())
        elif action == "close":
            target = browser or _registry._active_browser
            result = _registry.close_one(target) if target else "No browser specified."
        else:
            result = f"Unknown browser action: '{action}'"

    except concurrent.futures.TimeoutError:
        result = f"Browser action '{action}' timed out (60s)."
    except Exception as e:
        result = f"Browser error ({action}): {e}"

    _log(player, result)
    return result


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player:
        player.write_log(f"[browser] {short[:60]}")