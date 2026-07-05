# CLAUDE.md - ALICE Mark-XLVII & Hermes Agent Developer Guide

Dokumen ini mendefinisikan secara lengkap arsitektur sistem, struktur repositori, aliran data, aturan routing, manajemen proses Windows, konfigurasi, serta panduan pengembang untuk memastikan setiap agen AI (terutama Hermes Agent) maupun pengembang manusia tetap berada di dalam koridor rancangan desain sistem yang benar.

---

## 1. PENGENALAN SISTEM

ALICE (Advanced Live Integrated Computer Environment) Mark-XLVII adalah asisten virtual otonom berbasis kecerdasan buatan (AI) yang berjalan secara native di lingkungan Windows. Sistem ini mengkombinasikan antarmuka grafis (GUI PyQt6) berlatar belakang HUD futuristik, penanganan audio streaming real-time berlatar belakang Gemini Live API, kontrol sistem operasi Windows tingkat rendah (Win32 API/ctypes), serta integrasi erat dengan **Hermes Agent** untuk pendelegasian tugas pemrograman, administrasi server, dan pemrosesan otonom.

---

## 2. STRUKTUR DIREKTORI & PERAN BERKAS

```
X:\Mark-XLVII\
├── actions/                   # Modul aksi/tool yang dieksekusi secara lokal oleh ALICE
│   ├── browser_control.py     # Kontrol terpadu Chrome/BrowserOS dan Firefox (Marionette/BiDi)
│   ├── computer_control.py    # Kontrol jendela ctypes, penanganan fokus, volume, shortcut
│   ├── computer_settings.py   # Pengaturan volume suara, kecerahan layar, Wi-Fi, daya
│   ├── file_controller.py     # Penelusuran file cerdas dengan os.walk (pruning node_modules/venv)
│   ├── open_app.py            # Peluncuran aplikasi, penulisan user.js Firefox, Marionette port 6000
│   ├── system_monitor.py      # Pembacaan performa CPU, Memori, Suhu, dan Fallback GPU AMD/WMI
│   ├── system_control.py      # Dispatcher command line (CMD/PowerShell) & package manager
│   ├── ytmusic_control.py     # Pengontrol pemutar musik YouTube Music Desktop
│   ├── hermes_tools.py        # Wrapper untuk file_reader, search, dan web_extract
│   └── weather_report.py, send_message.py, dll.
├── config/
│   └── api_keys.json          # Berkas konfigurasi sensitif (API Keys, model, audio devices, port)
├── core/
│   └── prompt.txt             # Panduan instruksi perilaku utama (System Prompt) untuk Gemini Live API
├── memory/
│   └── memory_manager.py      # Pengelola memori markdown sinkron langsung dengan Honcho API
├── skills/                    # Dokumen manifest instruksi spesifik task (Markdown)
│   ├── windows_control.md
│   ├── adel_protocol.md
│   ├── adding_new_tools.md    # Panduan bagi Hermes untuk membuat & memasang tool baru secara dinamis
│   └── music_playback.md
├── hermes-agent/              # Subdirectory repositori Hermes Agent (embedded editable package)
├── main.py                    # Berkas bootstrapping utama, penanganan websocket Live API, & tool dispatcher
├── ui.py                      # Definisi visual GUI PyQt6 (Overlay HUD, System Monitor, Hermes Logs)
├── hermes_daemon.py           # Daemon pendukung port 8085 (asynchronous task runner & Firefox MCP bridge)
├── CLAUDE.md                  # Dokumen panduan pengembang (berkas ini)
└── run.log                    # File log runtime gabungan (diarahkan dari pythonw.exe)
```

---

## 3. ARSITEKTUR & ALIRAN DATA (ARCHITECTURE BLUEPRINT)

### A. Aliran Interaksi Live Stream (Audio & UI)
```
[User Mic] ──────> (sd.InputStream) ──────> [main.py (WS Connect)] ──────> [Gemini Live API (Sub2API Proxy)]
                                                                                     │
[User Speaker] <── (sd.RawOutputStream) <─── [main.py (Audio Response)] <────────────┘
```

### B. Aliran Eksekusi Tool & Browser Routing
```
                     [Gemini Live API Tool Call]
                                 │
                          [main.py Dispatcher]
                                 │
             ┌───────────────────┴───────────────────┐
      (action="go_to",                       (action="go_to",
    browser="browseros")                     browser="firefox")
             │                                       │
     [BrowserOS Chrome]                       [Hermes Daemon]
        (Port 9200)                      (HTTP-to-Stdio Port 8085)
             │                                       │
      [Chrome Browser]                     [Firefox MCP Bridge]
                                                     │
                                             [Firefox Debugger]
                                              (Marionette 6000)
```

### C. Aliran Sinkronisasi Memori (Honcho)
```
[ALICE (memory_manager.py)] ────(HTTP PUT peer card)────> [Honcho Server (Linux Armbian Port 8000)]
             │                                                                ▲
             ▼                                                                │
[Local Disk memories/USER.md] ────────────────────────────────────────────────┘
```

---

## 4. ATURAN ROUTING & KONTROL BROWSER (STRICT)

Sistem membedakan secara tegas metode kontrol browser. Tidak boleh ada pencampuran perintah:

### A. BrowserOS / Chrome Control
- **Sasaran**: Chrome milik sistem yang dikelola oleh instance BrowserOS.
- **Teka-teki Pemanggilan**: Hanya gunakan tool MCP bawaan BrowserOS (`tabs`, `navigate`, `act`, `read`, `snapshot`) yang memiliki label deskripsi **`[BrowserOS Chrome ONLY]`**.
- **Endpoint**: Diarahkan ke port `9200` atau `9102` menggunakan JSON-RPC.

### B. Firefox Control
- **Sasaran**: Aplikasi Firefox Developer yang berjalan lokal dengan remote debugger Marionette aktif pada port `6000` dan remote-debugging port `9222`.
- **Teka-teki Pemanggilan**: Hanya gunakan tool Custom MCP Firefox (`list_pages`, `new_page`, `navigate_page`, `select_page`, `close_page`, `take_snapshot`, `click_by_uid`, `fill_by_uid`, `hover_by_uid`) yang bertanda **`[Firefox ONLY]`**.
- **Kebijakan Navigasi & Interaksi**:
  - **Dilarang Keras** melakukan fallback secara diam-diam ke Chrome/BrowserOS jika Firefox mengalami kegagalan loading halaman. Laporkan error koneksi/DNS apa adanya ke user.
  - Untuk aksi interaktif (klik, ngetik, hover), **wajib** menggunakan rute tool BiDi dengan konversi UID (misalnya: jika model memanggil `browser_control(action='type', ref='e12', text='xyz')`, parsing parameter `ref` menjadi clean integer `12` lalu teruskan ke `fill_by_uid`).
  - Mengambil data teks/Scraping halaman Firefox wajib memicu `take_snapshot(maxLines=1500, includeAll=True)` untuk mem-bypass filter elemen non-interactive dan menghindari kegagalan parser substring pada data bertipe non-string.

---

## 5. ATURAN SUBPROCESS WINDOWS (NO-WINDOW GUARD)

Ketika memanggil executable eksternal dari script Python (misalnya memanggil `git`, `npm`, `tasklist`, `curl`, atau `hermes.exe`):
- **Wajib** menyertakan parameter `creationflags=0x08000000` (atau flag `CREATE_NO_WINDOW` dari utility `windows_hide_flags()`) di dalam method `subprocess.Popen` atau `subprocess.run`.
- **Tujuan**: Mencegah munculnya pop-up command prompt hitam kosong di layar Windows user yang mengganggu kenyamanan visual.

---

## 6. SKEMA KONFIGURASI (`config/api_keys.json`)

Berkas `config/api_keys.json` menyimpan seluruh setelan port, API key fallback, nama hardware device, dan rute server:
```json
{
  "api_key": "YOUR_DIRECT_GEMINI_KEY",
  "sub2api_key": "YOUR_SUB2API_PROXY_KEY",
  "sub2api_base_url": "https://sub2api.randompulse.my.id/antigravity",
  "browseros_mcp_url": "http://127.0.0.1:9200/mcp",
  "mcp_custom_enabled": true,
  "mcp_custom_url": "http://127.0.0.1:8085/firefox/mcp",
  "mic_input_device": "Microphone (Realtek High Definition Audio)",
  "spk_output_device": "Speakers (Realtek High Definition Audio)",
  "model_name": "gemini-2.5-flash"
}
```

---

## 7. SISTEM MEMORI UNIFIED & KOORDINASI HONCHO

Sistem memori tidak lagi menggunakan database JSON lokal (`long_term.json`) di direktori Windows ALICE.
- **Modul `memory/memory_manager.py`**: Mengambil (`load_memory`) dan memperbarui (`update_memory`) data memori berformat Markdown dari berkas target `USER.md` secara native.
- **Penyimpanan Pusat (Armbian Host)**: Backend tersambung langsung ke Honcho API di `http://192.168.0.102:8000/v3/workspaces/hermes/peers/760143518/card` via HTTP PUT.
- **Format Markdown (USER.md)**: Harus terstruktur rapi dengan separator markdown standar untuk membedakan kategori (misal: `# User Profile`, `# Environment Facts`).

---

## 8. PROTOKOL PENGEMBANGAN TOOL BARU & REST_ALICE

Apabila user meminta asisten menambahkan kemampuan (tool) baru secara dinamis:

### Langkah Integrasi oleh Kode/AI (Hermes):
1. **Buat Aksi**: Buat modul Python baru di folder `actions/` (misalnya `actions/my_feature.py`). Fungsi utama wajib mengekspos signature:
   ```python
   def my_feature(parameters=None, response=None, player=None, session_memory=None) -> str:
       # Logika program...
       return "Hasil eksekusi"
   ```
2. **Impor Aksi**: Buka `main.py`, tambahkan impor berkas: `from actions.my_feature import my_feature`.
3. **Daftarkan Skema**: Tambahkan definisi skema parameter JSON tool ke dalam array `TOOL_DECLARATIONS` di `main.py`.
4. **Dispatcher**: Tambahkan blok `elif name == "my_feature":` di dalam fungsi dispatcher eksekusi tool di `main.py`.
5. **Verifikasi Sintaks**: Jalankan `python -m py_compile main.py actions/my_feature.py` untuk menjamin tidak ada typo sintaks.

### Langkah Relaunch (Restart Service):
Setelah file berhasil diubah atau tool baru selesai ditambahkan, ALICE **wajib di-restart** agar pythonw memuat modul baru dari cache memori disk. Jalankan perintah ini via Windows Terminal:
```powershell
taskkill /F /IM python.exe ; taskkill /F /IM pythonw.exe ; schtasks /end /tn "RunAlice" ; schtasks /run /tn "RunAlice"
```
*(Atau minta ALICE melakukan restart otonom dengan memanggil perintah di atas melalui tool `system_control`)*
