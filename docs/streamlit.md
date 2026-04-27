# Publish Gratis ke Streamlit Community Cloud

Panduan ini untuk menjalankan versi Streamlit dari aplikasi RAB. File utama yang dipakai Streamlit Cloud adalah `streamlit_app.py`.

## Yang perlu disiapkan
- Akun GitHub.
- Akun Streamlit Community Cloud.
- Repository GitHub berisi project ini.
- File `data/sbm-cache.xlsx` ikut masuk repository agar referensi provinsi, kota, dan biaya SBM tersedia di cloud.

Jika repository dibuat public, semua file yang dipush juga bisa dilihat publik. Jika data SBM tidak boleh dibuka untuk umum, gunakan repository private dan jangan taruh password di file project.

## Jalankan lokal versi Streamlit
```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Aplikasi akan terbuka di browser. Jika ingin memakai password lokal:

```powershell
$env:STREAMLIT_APP_PASSWORD="password-yang-kuat"
streamlit run streamlit_app.py
```

## Push ke GitHub
Jika project belum menjadi git repository:

```powershell
git init
git add .
git commit -m "Prepare RAB app for Streamlit deployment"
```

Buat repository baru di GitHub, lalu jalankan perintah dari GitHub. Contohnya:

```powershell
git branch -M main
git remote add origin https://github.com/NAMA_USER/NAMA_REPO.git
git push -u origin main
```

## Deploy di Streamlit Cloud
1. Buka Streamlit Community Cloud.
2. Pilih `Create app` atau `New app`.
3. Hubungkan akun GitHub.
4. Pilih repository aplikasi RAB.
5. Isi `Main file path` dengan:

```text
streamlit_app.py
```

6. Buka bagian secrets lalu isi password aplikasi:

```toml
APP_PASSWORD = "password-yang-kuat"
```

7. Klik deploy.

Setelah selesai, Streamlit akan memberikan link publik yang bisa dibagikan.

## Catatan penting
- Streamlit Cloud cocok untuk demo, uji coba internal kecil, dan link gratis tanpa domain.
- Database SQLite di Streamlit Cloud bukan pilihan terbaik untuk data produksi jangka panjang atau banyak user bersamaan. Data bisa hilang saat redeploy/restart.
- Untuk produksi resmi, gunakan jalur Docker/VPS atau database eksternal yang persisten.
- Jika aplikasi tidak diberi `APP_PASSWORD`, link Streamlit dapat dibuka siapa pun yang punya URL.
