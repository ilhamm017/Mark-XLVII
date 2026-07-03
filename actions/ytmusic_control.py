# ytmusic_control.py
import json
import os
import sys
from pathlib import Path

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
TOKEN_PATH = BASE_DIR / "config" / "ytmusic_token.txt"

class YTMusicAPI:
    """
    Interface for interacting with the YouTube Music Desktop App API Server (port 26538).
    Supports authentication, searching, playback control, volume, and queue management.
    """
    def __init__(self, host="localhost", port=26538, client_id="alice-assistant"):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.base_url = f"http://{host}:{port}"
        self.token = None
        self._load_token_from_file()

    def _load_token_from_file(self):
        if TOKEN_PATH.exists():
            try:
                self.token = TOKEN_PATH.read_text(encoding="utf-8").strip()
            except Exception as e:
                print(f"[YTMusic] ⚠️ Failed to load local token: {e}")

    def _save_token_to_file(self, token):
        try:
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(token, encoding="utf-8")
            self.token = token
        except Exception as e:
            print(f"[YTMusic] ⚠️ Failed to save token to file: {e}")

    def authenticate(self, force=False, timeout=45) -> bool:
        """
        Request authorization from the YouTube Music Desktop App.
        If a popup appears on the host screen, the user must click 'Allow'.
        """
        if not _REQUESTS_OK:
            print("[YTMusic] ❌ requests library is not available.")
            return False

        if self.token and not force:
            # Quick check if token is valid by making a simple request
            if self.get_current_song() is not None or self.get_volume() is not None:
                return True

        auth_url = f"{self.base_url}/auth/{self.client_id}"
        print(f"[YTMusic] Sending authorization request to {auth_url}...")
        print("[YTMusic] Prompting desktop app authorization dialog. Please click 'Allow' on the host screen.")

        try:
            r = requests.post(auth_url, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                token = data.get("accessToken")
                if token:
                    self._save_token_to_file(token)
                    print("[YTMusic] ✅ Authorization successful and token saved.")
                    return True
            elif r.status_code == 403:
                print("[YTMusic] ❌ Authorization request was denied.")
            else:
                print(f"[YTMusic] ❌ Authorization returned status: {r.status_code}")
        except requests.exceptions.Timeout:
            print("[YTMusic] ❌ Authorization request timed out (user did not respond).")
        except Exception as e:
            print(f"[YTMusic] ❌ Connection error during auth: {e}")

        return False

    def _get_headers(self):
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method, endpoint, json_data=None, timeout=10):
        if not _REQUESTS_OK:
            return None

        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=json_data,
                timeout=timeout
            )
            if r.status_code == 204:
                return True
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return r.text
            if r.status_code == 401:
                print("[YTMusic] ❌ Unauthorized (401). Trying re-authentication...")
                # Re-auth (non-blocking) or mark token invalid
                self.token = None
                if TOKEN_PATH.exists():
                    try:
                        TOKEN_PATH.unlink()
                    except Exception:
                        pass
            return None
        except Exception as e:
            print(f"[YTMusic] ⚠️ Request to {endpoint} failed: {e}")
            return None

    # --- Playback Controls ---
    def set_queue_index(self, index: int) -> bool:
        return bool(self._request("PATCH", "/api/v1/queue", json_data={"index": index}))

    def play(self, video_id: str | None = None, playlist_id: str | None = None) -> bool:
        if video_id:
            # 1. Get current queue to find selected index
            queue_data = self.get_queue()
            current_idx = -1
            if queue_data and isinstance(queue_data, dict) and "items" in queue_data:
                for idx, item in enumerate(queue_data["items"]):
                    renderer = item.get("playlistPanelVideoRenderer", {})
                    if renderer.get("selected"):
                        current_idx = idx
                        break
            
            # 2. Add to queue right after current video
            insert_after = (current_idx != -1)
            if not self.add_to_queue(video_id, insert_after_current=insert_after):
                return False
                
            # 3. Switch queue index to play the new song
            target_idx = current_idx + 1 if insert_after else 0
            if not self.set_queue_index(target_idx):
                return False
                
            # 4. Ensure playback is active
            self._request("POST", "/api/v1/play")
            return True
        elif playlist_id:
            print("[YTMusic] playPlaylist is not supported in this version of the API.")
            return False
        else:
            return bool(self._request("POST", "/api/v1/play"))

    def pause(self) -> bool:
        return bool(self._request("POST", "/api/v1/pause"))

    def toggle_play(self) -> bool:
        return bool(self._request("POST", "/api/v1/toggle-play"))

    def next(self) -> bool:
        return bool(self._request("POST", "/api/v1/next"))

    def previous(self) -> bool:
        return bool(self._request("POST", "/api/v1/previous"))

    def like(self) -> bool:
        return bool(self._request("POST", "/api/v1/like"))

    def dislike(self) -> bool:
        return bool(self._request("POST", "/api/v1/dislike"))

    def get_volume(self) -> dict | None:
        return self._request("GET", "/api/v1/volume")

    def set_volume(self, volume: int) -> bool:
        return bool(self._request("POST", "/api/v1/volume", json_data={"volume": volume}))

    def get_current_song(self) -> dict | None:
        """
        Returns info for the currently loaded song or None.
        """
        return self._request("GET", "/api/v1/song")

    # --- Queue management ---
    def get_queue(self) -> dict | None:
        return self._request("GET", "/api/v1/queue")

    def add_to_queue(self, video_id: str, insert_after_current=False) -> bool:
        position = "INSERT_AFTER_CURRENT_VIDEO" if insert_after_current else "INSERT_AT_END"
        return bool(self._request("POST", "/api/v1/queue", json_data={"videoId": video_id, "insertPosition": position}))

    def clear_queue(self) -> bool:
        return bool(self._request("DELETE", "/api/v1/queue"))

    # --- Search and Parser ---
    def search(self, query: str) -> list:
        """
        Searches YouTube Music for songs, videos, albums, etc.
        Returns a parsed list of results.
        """
        raw_res = self._request("POST", "/api/v1/search", json_data={"query": query})
        if not raw_res:
            return []

        return self._parse_search_results(raw_res)

    def _parse_search_results(self, res) -> list:
        contents = res.get("contents", {}).get("tabbedSearchResultsRenderer", {}).get("tabs", [{}])[0].get("tabRenderer", {}).get("content", {}).get("sectionListRenderer", {}).get("contents", [])
        
        parsed_items = []
        
        def get_text(run_list):
            if not run_list:
                return ""
            if isinstance(run_list, dict) and "runs" in run_list:
                return "".join(run.get("text", "") for run in run_list["runs"])
            return ""
            
        for shelf in contents:
            # 1. Top Result (Card)
            if "musicCardShelfRenderer" in shelf:
                card = shelf["musicCardShelfRenderer"]
                title = get_text(card.get("title"))
                subtitle = get_text(card.get("subtitle"))
                
                # Determine type
                item_type = "unknown"
                sub_lower = subtitle.lower()
                if any(x in sub_lower for x in ["artis", "artist"]):
                    item_type = "artist"
                elif any(x in sub_lower for x in ["lagu", "song"]):
                    item_type = "song"
                elif "album" in sub_lower:
                    item_type = "album"
                elif "video" in sub_lower:
                    item_type = "video"
                    
                # Extract ID
                item_id = None
                buttons = card.get("buttons", [])
                for btn in buttons:
                    cmd = btn.get("buttonRenderer", {}).get("command", {})
                    if "watchEndpoint" in cmd:
                        item_id = cmd["watchEndpoint"].get("videoId")
                        break
                
                if not item_id:
                    title_runs = card.get("title", {}).get("runs", [])
                    if title_runs and "navigationEndpoint" in title_runs[0]:
                        nav = title_runs[0]["navigationEndpoint"]
                        if "browseEndpoint" in nav:
                            item_id = nav["browseEndpoint"].get("browseId")
                
                thumb = None
                thumbs = card.get("thumbnail", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])
                if thumbs:
                    thumb = thumbs[-1].get("url")
                    
                parsed_items.append({
                    "type": item_type,
                    "title": title,
                    "artist": title if item_type == "artist" else subtitle.split(" • ")[-1] if " • " in subtitle else subtitle,
                    "id": item_id,
                    "extra": subtitle,
                    "thumbnail": thumb,
                    "is_top_result": True
                })
                
            # 2. Other results (Item Sections)
            elif "itemSectionRenderer" in shelf:
                isr = shelf["itemSectionRenderer"]
                for item in isr.get("contents", []):
                    mrlir = item.get("musicResponsiveListItemRenderer", {})
                    if not mrlir:
                        continue
                        
                    flex_columns = mrlir.get("flexColumns", [])
                    if not flex_columns:
                        continue
                    
                    # Column 0: Title
                    title = get_text(flex_columns[0].get("musicResponsiveListItemFlexColumnRenderer", {}).get("text", {}))
                    
                    # Column 1: Details
                    details_runs = flex_columns[1].get("musicResponsiveListItemFlexColumnRenderer", {}).get("text", {}).get("runs", [])
                    
                    item_type = "unknown"
                    artist = ""
                    extra_parts = []
                    
                    if details_runs:
                        raw_type = details_runs[0].get("text", "").strip().lower()
                        if raw_type in ["lagu", "song"]:
                            item_type = "song"
                        elif raw_type in ["artis", "artist"]:
                            item_type = "artist"
                        elif raw_type in ["album", "single", "singel", "ep"]:
                            item_type = "album"
                        elif raw_type == "video":
                            item_type = "video"
                        
                        # Split by bullet point
                        parts = []
                        current_part = []
                        for run in details_runs:
                            text = run.get("text", "")
                            if text.strip() == "•":
                                if current_part:
                                    parts.append("".join(current_part).strip())
                                    current_part = []
                            else:
                                current_part.append(text)
                        if current_part:
                            parts.append("".join(current_part).strip())
                        
                        if len(parts) > 1:
                            if parts[0].lower() in ["lagu", "song", "album", "video", "artis", "artist", "single", "singel", "ep"]:
                                artist = parts[1]
                                if len(parts) > 2:
                                    extra_parts.extend(parts[2:])
                            else:
                                artist = parts[0]
                                extra_parts.extend(parts[1:])
                        else:
                            artist = parts[0] if parts else ""
                    
                    # Additional Columns (Plays, Duration, etc.)
                    for col in flex_columns[2:]:
                        col_text = get_text(col.get("musicResponsiveListItemFlexColumnRenderer", {}).get("text", {}))
                        if col_text:
                            extra_parts.append(col_text)
                    
                    extra_info = " • ".join(extra_parts)
                    
                    # Extract ID
                    item_id = None
                    playlist_item_data = mrlir.get("playlistItemData", {})
                    if "videoId" in playlist_item_data:
                        item_id = playlist_item_data["videoId"]
                    
                    if not item_id:
                        overlay = mrlir.get("overlay", {}).get("musicItemThumbnailOverlayRenderer", {})
                        play_nav = overlay.get("content", {}).get("musicPlayButtonRenderer", {}).get("playNavigationEndpoint", {})
                        if "watchEndpoint" in play_nav:
                            item_id = play_nav["watchEndpoint"].get("videoId")
                            
                    if not item_id:
                        overlay = mrlir.get("overlay", {}).get("musicItemThumbnailOverlayRenderer", {})
                        play_nav = overlay.get("content", {}).get("musicPlayButtonRenderer", {}).get("playNavigationEndpoint", {})
                        if "watchPlaylistEndpoint" in play_nav:
                            item_id = play_nav["watchPlaylistEndpoint"].get("playlistId")
                    
                    if not item_id:
                        nav = mrlir.get("navigationEndpoint", {})
                        if "browseEndpoint" in nav:
                            item_id = nav["browseEndpoint"].get("browseId")
                            
                    thumb = None
                    thumbs = mrlir.get("thumbnail", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])
                    if thumbs:
                        thumb = thumbs[-1].get("url")
                        
                    parsed_items.append({
                        "type": item_type,
                        "title": title,
                        "artist": artist,
                        "id": item_id,
                        "extra": extra_info,
                        "thumbnail": thumb,
                        "is_top_result": False
                    })
                    
        return parsed_items

def ytmusic_control(parameters: dict, player=None) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    query = params.get("query", "").strip()
    video_id = params.get("video_id", "").strip()
    volume = params.get("volume")

    # Local host by default for running on Windows PC
    api = YTMusicAPI(host="localhost")

    if action == "authenticate":
        if api.authenticate(force=True, timeout=15):
            return "YouTube Music authorization successful."
        else:
            return "Failed to authorize YouTube Music. Please click 'Allow' on the desktop app popup."

    # For other actions, ensure auth
    if not api.token:
        print("[YTMusic] Token missing. Attempting quick auth...")
        if not api.authenticate(timeout=5):
            return "YouTube Music is not authorized. Please ask me to authenticate first."

    if action == "play":
        if video_id:
            if api.play(video_id=video_id):
                return f"Playing track with ID {video_id}."
            return "Failed to play track."
        elif query:
            results = api.search(query)
            if not results:
                return f"No results found for '{query}' on YouTube Music."
            # Find first item that has an ID and is a song or video
            target = None
            for item in results:
                if item.get("id") and item.get("type") in ("song", "video"):
                    target = item
                    break
            if not target:
                target = results[0]  # Fallback to top result
            
            tid = target.get("id")
            title = target.get("title")
            artist = target.get("artist")
            if tid:
                if api.play(video_id=tid):
                    return f"Playing {title} by {artist} on YouTube Music."
                return f"Failed to play {title}."
            return "Found search results but could not extract track ID."
        else:
            if api.play():
                return "Resumed playback on YouTube Music."
            return "Failed to resume playback."

    elif action == "pause":
        if api.pause():
            return "Paused music."
        return "Failed to pause music."

    elif action == "toggle_play":
        if api.toggle_play():
            return "Toggled playback."
        return "Failed to toggle playback."

    elif action == "next":
        if api.next():
            return "Skipped to next song."
        return "Failed to skip."

    elif action == "previous":
        if api.previous():
            return "Went back to previous song."
        return "Failed to go back."

    elif action == "like":
        if api.like():
            return "Liked the current song."
        return "Failed to like song."

    elif action == "dislike":
        if api.dislike():
            return "Disliked the current song."
        return "Failed to dislike song."

    elif action == "set_volume":
        if volume is None:
            return "Volume value is required for set_volume."
        try:
            vol_int = int(volume)
            if api.set_volume(vol_int):
                return f"Set YouTube Music volume to {vol_int}%."
        except ValueError:
            pass
        return "Failed to set volume."

    elif action == "status":
        song = api.get_current_song()
        if not song or not song.get("title"):
            return "No song is currently playing on YouTube Music."
        title = song.get("title")
        artist = song.get("artist", "Unknown Artist")
        album = song.get("album", "")
        duration = song.get("duration", "")
        paused = song.get("isPaused", False)
        status = "Paused" if paused else "Playing"
        msg = f"Currently {status}: {title} by {artist}"
        if album:
            msg += f" (Album: {album})"
        if duration:
            msg += f" [{duration}]"
        return msg

    elif action == "queue":
        if video_id or query:
            # Add to queue
            target_id = video_id
            track_name = ""
            if not target_id and query:
                results = api.search(query)
                for item in results:
                    if item.get("id") and item.get("type") in ("song", "video"):
                        target_id = item["id"]
                        track_name = item["title"]
                        break
            if target_id:
                if api.add_to_queue(target_id):
                    return f"Added {track_name or target_id} to queue."
                return "Failed to add to queue."
            return "Could not find a track to add to queue."
        else:
            # Get queue
            q = api.get_queue()
            if not q or not q.get("items"):
                return "The queue is empty."
            items = q["items"]
            lines = ["YouTube Music Queue:"]
            for idx, item in enumerate(items[:10]):
                renderer = item.get("playlistPanelVideoRenderer", {})
                title_runs = renderer.get("title", {}).get("runs", [])
                title = title_runs[0].get("text", "Unknown") if title_runs else "Unknown"
                
                author_runs = renderer.get("shortBylineText", {}).get("runs", [])
                author = author_runs[0].get("text", "Unknown") if author_runs else "Unknown"
                
                selected = renderer.get("selected", False)
                prefix = "▶ " if selected else f"{idx+1}. "
                lines.append(f"{prefix}{title} - {author}")
            if len(items) > 10:
                lines.append(f"... and {len(items) - 10} more tracks.")
            return "\n".join(lines)

    elif action == "clear_queue":
        if api.clear_queue():
            return "Cleared the queue."
        return "Failed to clear queue."

    return f"Unknown action: {action}"

if __name__ == "__main__":
    # Test execution
    api = YTMusicAPI(host="100.108.138.26") # Local Tailscale IP of Windows PC
    if api.authenticate(timeout=10):
        print("Authenticated successfully!")
        song = api.get_current_song()
        if song:
            print(f"Current song: {song.get('title')} by {song.get('artist')}")
        results = api.search("READY STEADY GO")
        print(f"Search results for 'READY STEADY GO' ({len(results)} found):")
        for r in results[:5]:
            print(f"- [{r['type'].upper()}] {r['title']} by {r['artist']} (ID: {r['id']}, Extra: {r['extra']})")
    else:
        print("Authentication failed.")
