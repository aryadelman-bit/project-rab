# Publish Guide VPS/Docker

Panduan ini menyiapkan `RAB Workflow Assistant` agar bisa dibuka lewat link stabil dari VPS.

## Arsitektur Deploy

Komponen yang dipakai:

- `rab-app`: FastAPI app
- `rab_data`: persistent volume untuk `rab.db`, export, dan `sbm-cache.xlsx`
- `caddy`: reverse proxy dengan HTTPS otomatis
- Basic Auth opsional lewat env `RAB_BASIC_AUTH_USERNAME` dan `RAB_BASIC_AUTH_PASSWORD`

File deploy yang sudah tersedia:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `deploy/Caddyfile`
- `scripts/docker-entrypoint.sh`

## Prasyarat VPS

Gunakan VPS Ubuntu 22.04/24.04 atau server Linux lain yang mendukung Docker.

Pastikan:

- Domain/subdomain sudah diarahkan ke IP VPS
- Port `80` dan `443` terbuka
- Docker dan Docker Compose sudah terpasang

Contoh install Docker di Ubuntu:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Logout lalu login kembali agar user bisa menjalankan `docker`.

## Upload Project Ke VPS

Opsi paling sederhana:

```bash
scp -r "Project RAB" user@IP_VPS:/opt/rab-workflow
```

Atau jika project sudah masuk Git repository:

```bash
git clone <repo-url> /opt/rab-workflow
cd /opt/rab-workflow
```

## Konfigurasi Environment

Masuk ke folder project:

```bash
cd /opt/rab-workflow
cp .env.example .env
nano .env
```

Isi contoh:

```env
APP_DOMAIN=rab.example.go.id
RAB_BASIC_AUTH_USERNAME=admin
RAB_BASIC_AUTH_PASSWORD=ganti-password-kuat
```

Catatan:

- `APP_DOMAIN` harus domain/subdomain yang DNS-nya mengarah ke VPS.
- Jika hanya ingin test dengan IP tanpa HTTPS otomatis, isi `APP_DOMAIN=:80`.
- Jangan commit file `.env`.

## Jalankan Aplikasi

Build dan jalankan:

```bash
docker compose up -d --build
```

Cek status:

```bash
docker compose ps
docker compose logs -f rab-app
docker compose logs -f caddy
```

Buka:

```text
https://rab.example.go.id
```

Jika Basic Auth diaktifkan, browser akan meminta username/password.

## Data Dan File SBM

Container memakai persistent volume `rab_data` di `/app/data`.

Saat container pertama kali jalan:

- `scripts/docker-entrypoint.sh` membuat folder data
- `sbm-cache.xlsx` dari image disalin ke volume jika belum ada
- `scripts/seed.py` mengisi catalog dan sample data tanpa mereset database yang sudah ada

File penting di dalam volume:

- `/app/data/rab.db`
- `/app/data/sbm-cache.xlsx`
- `/app/data/exports`

## Backup Database

Backup SQLite dari container:

```bash
docker compose exec rab-app sh -c 'sqlite3 /app/data/rab.db ".backup /app/data/rab-backup.db"'
docker cp "$(docker compose ps -q rab-app)":/app/data/rab-backup.db ./rab-backup.db
```

Jika image belum punya CLI `sqlite3`, gunakan backup file langsung saat container dihentikan:

```bash
docker compose stop rab-app
docker run --rm -v rab-workflow_rab_data:/data -v "$PWD":/backup alpine cp /data/rab.db /backup/rab-backup.db
docker compose start rab-app
```

Nama volume bisa berbeda. Cek dengan:

```bash
docker volume ls
```

## Update Aplikasi

Setelah ada perubahan kode:

```bash
cd /opt/rab-workflow
docker compose up -d --build
```

Database tidak hilang selama volume `rab_data` tidak dihapus.

## Reset Data

Gunakan hanya jika memang ingin menghapus data lama:

```bash
docker compose exec rab-app python scripts/seed.py --reset
```

## Keamanan Minimum

Untuk deploy publik, minimal aktifkan:

- HTTPS lewat Caddy
- Basic Auth lewat `.env`
- Backup berkala file `rab.db`
- Firewall hanya membuka port `22`, `80`, dan `443`

Contoh firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Catatan Produksi

SQLite cukup untuk pilot kecil dan pemakaian ringan.

Jika nanti aplikasi dipakai banyak pegawai secara bersamaan, rencana teknis berikutnya adalah migrasi ke PostgreSQL dan menambah login user berbasis role.
