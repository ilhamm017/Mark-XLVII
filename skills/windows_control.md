---
name: Windows control
description: Panduan mengontrol aplikasi desktop Windows, tata letak jendela, volume, dan pengaturan sistem.
---
# Windows Control Skill

Gunakan skill ini ketika user meminta kamu mengontrol Windows desktop:

1. **Membuka Aplikasi**: Gunakan tool `open_app` dengan argumen `app_name`. Contoh: `open_app(app_name="Chrome")`.
2. **Navigasi Desktop / Windows Layout**: Gunakan tool `desktop_control` untuk meminimalkan, memaksimalkan, atau memindahkan fokus jendela.
3. **Melihat Aplikasi Aktif**: Gunakan `get_active_window` atau `list_taskbar_apps` untuk memantau apa yang sedang dibuka oleh user.
4. **Pengaturan Sistem**: Gunakan `computer_settings` untuk mengatur volume, kecerahan layar, atau mematikan/me-restart komputer.
5. **Weather & System Monitor**: Untuk laporan cuaca gunakan `weather_report`, dan untuk status sistem RAM/CPU gunakan `_run_system_monitor` secara pasif atau laporkan status sistem ketika ditanya.
