import webbrowser
from urllib.parse import quote_plus


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city     = parameters.get("city")
    when     = parameters.get("time", "today")  

    if not city or not isinstance(city, str) or not city.strip():
        msg = "Sir, the city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip()

    search_query  = f"weather in {city} {when}"
    url           = f"https://www.google.com/search?q={quote_plus(search_query)}"

    try:
        import urllib.request
        browseros_running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:9200/health", timeout=1) as response:
                browseros_running = (response.status == 200)
        except Exception:
            pass

        if browseros_running:
            try:
                from actions.browser_control import browser_control
                print(f"[Weather] Opening search in BrowserOS: {url}")
                browser_control({"action": "go_to", "url": url}, player)
                msg = f"Showing the weather for {city}, {when} in BrowserOS, sir."
                _log(msg, player)
                if session_memory:
                    try:
                        session_memory.set_last_search(query=search_query, response=msg)
                    except Exception:
                        pass
                return msg
            except Exception as e:
                print(f"[Weather] ⚠️ Failed to open in BrowserOS: {e}")
    except Exception as e:
        print(f"[Weather] ⚠️ BrowserOS check failed: {e}")

    try:
        opened = webbrowser.open(url)
        if not opened:
            raise RuntimeError("webbrowser.open returned False")
    except Exception as e:
        msg = f"Sir, I couldn't open the browser for the weather report: {e}"
        _log(msg, player)
        return msg

    msg = f"Showing the weather for {city}, {when}, sir."
    _log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(query=search_query, response=msg)
        except Exception:
            pass

    return msg


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"Alice: {message}")
        except Exception:
            pass