# RAB Workflow Assistant

Aplikasi fullstack lokal untuk penyusunan RAB kegiatan kementerian berbasis workflow kegiatan, bukan sekadar tabel input anggaran manual.

## Fitur yang sudah dibangun
- CRUD kegiatan
- CRUD sub komponen/tahapan
- Kode sub komponen otomatis `A/B/C/D/...`
- Pemilihan bentuk kegiatan per tahapan
- Rule engine sederhana untuk rekomendasi akun belanja
- Default detail item per akun
- Editor detail belanja yang bisa diubah langsung
- Perhitungan subtotal, total akun, total sub komponen, dan total kegiatan
- Validasi sisa pagu dan warning jika melampaui pagu
- Ekspor Excel dan PDF
- Seed sample data `Hilirisasi Kelapa`
- Import referensi tarif dari workbook SBM yang Anda lampirkan

## Stack
- Backend: FastAPI
- Database: SQLite
- Frontend: HTML + CSS + vanilla JavaScript SPA
- Publish gratis: Streamlit Community Cloud via `streamlit_app.py`
- Excel import/export: openpyxl
- PDF export: reportlab

## Menjalankan aplikasi
1. Aktifkan virtual environment:
```powershell
.\.venv\Scripts\activate
```
2. Jalankan seed bila perlu:
```powershell
python scripts/seed.py --reset
```
3. Jalankan server:
```powershell
uvicorn app.main:app --reload
```
4. Buka:
```text
http://127.0.0.1:8000
```

## Catatan sumber biaya SBM
Saat startup, aplikasi akan mencoba membaca workbook ini:

`C:\Users\Admin\OneDrive - Kementerian Perindustrian Divisi Agro\MONEV 4.0\2026\LAIN-LAIN\DATA LAMPIRAN PMK 32 2025.xlsx`

Atau Anda dapat set environment variable:

```powershell
$env:SBM_SOURCE_PATH="C:\path\ke\file.xlsx"
```

## Struktur project
- `app/main.py`
  Entry point FastAPI dan REST API.
- `app/services/rab.py`
  Domain service, rule engine, summary, seed sample activity.
- `app/services/sbm.py`
  Import workbook SBM ke tabel `cost_references`.
- `app/services/exports.py`
  Ekspor Excel dan PDF.
- `app/static/`
  Frontend SPA.
- `docs/architecture.md`
  Ringkasan arsitektur dan alur bisnis.
- `docs/publish.md`
  Panduan share cepat dan publish proper ke server / Docker.

## Publish agar link bisa dibagikan
Ada dua jalur:

1. `Share cepat`
   Jalankan app lokal lalu buka tunnel publik ke `http://127.0.0.1:8000`.
2. `Publish proper`
   Build Docker image lalu deploy ke server atau platform yang mendukung Docker + persistent volume.

Panduan detail ada di:

`docs/publish.md`

Untuk publish gratis via Streamlit Cloud, gunakan entrypoint:

```text
streamlit_app.py
```

Panduan langkah demi langkah ada di:

`docs/streamlit.md`

Untuk deploy VPS/Docker yang siap domain:

```bash
cp .env.example .env
docker compose up -d --build
```

Edit `.env` sebelum menjalankan compose untuk mengisi domain dan Basic Auth.

## Rule mapping awal
- `OFFICE_MEETING` -> `521211`
- `OFFICE_MEETING + has_speaker=true` -> `522151`
- `OUT_OF_TOWN_IDENTIFICATION` -> `524111`
- `ATTEND_EXTERNAL_MEETING + travel_scope=within_city` -> `524114`
- `ATTEND_EXTERNAL_MEETING + travel_scope=out_of_town` -> `524119`
- `LOCAL_FACTORY_VISIT` -> `524113`
- `TECHNICAL_GUIDANCE` -> `521211`
- `TECHNICAL_GUIDANCE + has_speaker=true` -> `522151`

## Referensi biaya SBM yang dipakai
- `HONOR`
- `UH DN`
- `HOTEL`
- `PM`
- `SEWA`
- `KONSUM`
- `TRANS DARAT`
- `TAKSI BANDARA`
- `PESAWAT DN`
