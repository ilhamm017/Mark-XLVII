# CLAUDE.md - ALICE Mark-XLVII & Hermes Agent Developer Guide

Dokumen ini mendefinisikan rancangan arsitektur, aturan routing browser, pengelolaan subprocess Windows, serta protokol integrasi/restart untuk memastikan AI coding assistant (Hermes/Cursor/IDE Agent) tetap berada di jalur rancangan desain sistem yang benar.

---

## 1. Arsitektur Utama (System Blueprint)

Sistem ini terintegrasi sebagai kesatuan asisten otonom ALICE (frontend GUI & Live API) dengan Hermes (backend mastermind & coding agent).
- **ALICE (Live Client)**: Berjalan sebagai proses Python/PyQt (`pythonw.exe`) di Windows (`X:\Mark-XLVII`). Menangani input/output audio (mic/speaker dinamis) dan status panel monitor real-time.
- **Hermes Daemon**: Berjalan asinkron di background port `8085`. Menangani eksekusi tugas otonom, tailing log task otonom (`local_XXXXXX.log` ke panel UI), dan menyediakan **Stdio-to-HTTP Bridge** untuk Firefox MCP.
- **Unified Memory (Honcho)**: Menghubungkan modul memori ALICE (`memory_manager.py`) secara native ke Honcho Server (`http://192.168.0.102:8000` / port 8000 di Linux Armbian). Tidak menggunakan memori JSON lokal (`long_term.json`) maupun port dashboard `8080` (deprecated). Memori dibaca dan ditulis langsung dari/ke file markdown `USER.md` di `.hermes` AppData.

---

## 2. Aturan Rute & Kontrol Browser (Browser Routing)

Terdapat pemisahan tegas antara dua browser yang dikontrol secara programmatic:

### A. BrowserOS / Chrome (System Browser)
- **Tujuan**: Untuk kontrol umum, web search, visual debugging, scraping umum, atau tugas headless/headed cepat.
- **Tools**: Menggunakan set tool BrowserOS MCP (`tabs`, `navigate`, `act`, `read`, `snapshot`, dll.) yang terdaftar dengan deskripsi bertanda `[BrowserOS Chrome ONLY]`.
- **Rute URL**: Port default `9200` atau sesuai config `browseros_mcp_url`.

### B. Firefox (Developer Browser)
- **Tujuan**: Untuk pengujian langsung di local/development environment (seperti web Migunani Motor).
- **Tools**: Menggunakan Firefox DevTools MCP tools (`list_pages`, `new_page`, `navigate_page`, `select_page`, `close_page`, `take_snapshot`, `click_by_uid`, `fill_by_uid`, `hover_by_uid`) bertanda `[Firefox ONLY]`.
- **Port Debugging**: Marionette port `6000`, remote debugging port `9222`.
- **Aturan Eksekusi Firefox**:
  1. **Dilarang Keras** melakukan fallback secara diam-diam ke Chrome/BrowserOS jika Firefox mengalami kegagalan loading halaman. Laporkan error koneksi/DNS apa adanya ke user.
  2. Gunakan `_ensure_firefox_running()` untuk memeriksa port 6000 sebelum memanggil API Firefox.
  3. Gunakan pencocokan Process ID (PID) via `psutil` dan Win32 ctypes mapping (`GetWindowThreadProcessId`) untuk memfokuskan jendela Firefox secara presisi.
  4. Untuk aksi interaktif di Firefox, gunakan tool BiDi:
     - `click` -> rute ke `click_by_uid`
     - `type` / `fill` -> rute ke `fill_by_uid`
     - `hover` -> rute ke `hover_by_uid`

---

## 3. Aturan Subprocess Windows (No-Window Guard)

Semua pemanggilan CLI eksternal, task otonom Hermes, script Python, git, npm, maupun CLI tool lainnya langsung di sistem Windows:
- **Wajib** menyertakan parameter `creationflags=0x08000000` (atau flag dari pembantu `windows_hide_flags()`) di dalam parameter `subprocess.Popen` atau `subprocess.run`.
- **Tujuan**: Mencegah munculnya pop-up command prompt kosong yang mengganggu visual layar utama Windows user.

---

## 4. Pengembangan & Penambahan Tool Aksi Baru (Adding Actions)

Jika diminta menambahkan fitur atau kemampuan baru di ALICE:
1. Buat file script aksi baru di folder `actions/` (misal `actions/my_tool.py`). Gunakan parameter standar:
   ```python
   def my_tool(parameters=None, response=None, player=None, session_memory=None) -> str:
       # Logika program...
       return "Deskripsi hasil untuk ALICE"
   ```
2. Daftarkan deklarasi skema JSON tool baru di dalam array `TOOL_DECLARATIONS` pada berkas `main.py`.
3. Tambahkan rute penanganan tool baru di bagian `elif name == "my_tool":` di dalam dispatcher `main.py`.
4. Selalu jalankan uji kompilasi sintaks sebelum deploy: `python -m py_compile main.py`.

---

## 5. Protokol Relaunch & Restart Sistem

Setelah Hermes selesai memodifikasi kode program, sistem **wajib di-restart** agar Python memuat modul baru dari disk ke memori. 
Restart dilakukan secara non-interactive dengan mematikan proses `pythonw.exe` aktif dan memicu ulang Task Scheduler Windows:

```powershell
taskkill /F /IM pythonw.exe ; schtasks /end /tn "RunAlice" ; schtasks /run /tn "RunAlice"
```
Jangan biarkan ALICE tetap berjalan dengan kode lama setelah perubahan krusial dilakukan.
