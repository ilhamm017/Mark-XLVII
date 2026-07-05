---
name: adding_new_tools
description: Panduan langkah demi langkah bagi ALICE dan Hermes untuk menambahkan, mendaftarkan, dan memperbarui tool/aksi baru secara dinamis di dalam codebase ALICE.
---
# Dynamic Tool Addition Skill

Gunakan panduan ini ketika user meminta ALICE melakukan sesuatu yang membutuhkan *tool* atau kemampuan baru yang belum ada di daftar tool bawaan:

1. **Gunakan Hermes untuk Membuat Kode**: ALICE harus memanggil `ask_hermes` untuk merancang, membuat kode, dan mengintegrasikan tool baru tersebut.
2. **Langkah Integrasi oleh Hermes**:
   - **Langkah A: Buat File Action Baru**
     Buat file baru di direktori `actions/` (misalnya `actions/my_new_action.py`). Fungsi utama harus memiliki signature seperti berikut:
     ```python
     def my_new_action(parameters=None, response=None, player=None, session_memory=None) -> str:
         # Logika tool di sini...
         return "Hasil eksekusi"
     ```
   - **Langkah B: Patch main.py untuk Registrasi**
     Lakukan patch pada file `main.py` untuk mendaftarkan tool baru:
     1. Tambahkan import di bagian atas: `from actions.my_new_action import my_new_action`
     2. Tambahkan skema JSON tool ke dalam array `TOOL_DECLARATIONS` di `main.py`.
     3. Tambahkan cabang `elif name == "my_new_action":` di bagian dispatcher pemanggilan tool (sekitar baris 1800+) agar fungsi tersebut dieksekusi.
   - **Langkah C: Tulis Startup Briefing & Restart Otomatis**
     Sebelum me-restart ALICE, buat file `core/startup_briefing.txt` di folder Windows (`X:\Mark-XLVII\core\startup_briefing.txt`) berisi ringkasan update/perbaikan yang baru saja dilakukan. Kamu bisa menulisnya langsung lewat SSH/PowerShell atau membuatnya di server Linux lalu di-scp ke Windows.
     Setelah file briefing terbuat, picu restart ALICE dengan menjalankan perintah:
     ```powershell
     Stop-Process -Name python -ErrorAction SilentlyContinue; Stop-Process -Name pythonw -ErrorAction SilentlyContinue; schtasks /end /tn "RunAlice"; schtasks /run /tn "RunAlice"
     ```
     Dengan cara ini, begitu ALICE menyala kembali, dia akan langsung membaca file tersebut, melaporkan perbaikan terbarunya kepada user secara ramah, lalu otomatis menghapus file briefing tersebut agar tidak berulang.
