# Laily Property Draft Automation

Bot Telegram Python untuk menerima listing hartanah dan menyediakan **draf tempatan sahaja**
bagi Facebook Marketplace dan Mudah.my PRO Niaga. Penerangan disediakan dalam Bahasa Melayu dan English.
Tiada fungsi menerbitkan, submit untuk review, activate, boost atau schedule. Tiada automasi pelayar atau API tersembunyi.

## Apa yang sudah disediakan

- `python-telegram-bot`, SQLite, penyulitan Fernet untuk teks asal, sumber, gambar, butiran ejen dan butiran audit.
- Akses hanya untuk satu ID pengguna Telegram dalam chat peribadi; pemeriksaan turut meliputi callback butang.
- Teks, gambar, caption dan album disimpan. Setiap foto album disimpan segera; pratonton digabungkan selepas 2 saat senyap.
  Album lewat masih dikaitkan selepas restart kerana ID album disimpan dalam pangkalan data.
- Pengekstrakan konservatif berasaskan label; fakta tidak berlabel atau bercanggah dibiarkan kosong.
  Semak dan betulkan dengan Edit. Tiada AI luar menerima data listing.
- Pengecaman pendua melalui teks ternormal, ID foto Telegram dan gabungan ciri hartanah.
  Padanan hanyalah calon; iklan unit berlainan boleh berkongsi ciri. Tiada rekod atau gambar dibuang secara automatik.
- Rekod asal dan rujukan forward dikekalkan. Pautan sumber hanya dibuat jika saluran awam dan ID mesej tersedia.
  Telegram mungkin menyembunyikan asal; bot tidak dapat memulihkan maklumat itu.
- Pengesahan hak guna listing **dan semua gambar** diperlukan sebelum eksport. Edit atau tambahan album membatalkannya.
- ZIP dalam memori mengandungi draf berasingan BM/EN, teks asal, sumber dan foto.

## Had integrasi yang perlu difahami

Facebook: `INTEGRATION_UNAVAILABLE`. Mudah: `INTEGRATION_UNAVAILABLE`.
**Save Draft menyimpan secara tempatan sahaja.** Tiada akses akaun platform atau pautan draf akaun.
Semakan dokumentasi rasmi disekat rangkaian (403); baca [rekod penyelidikan](docs/INTEGRATIONS.md).
Fungsi Add Draft dalam akaun Mudah tidak dengan sendirinya memberi kebenaran API.
Facebook Page posts tidak digunakan sebagai pengganti Marketplace listings.

## 1. Pasang Python dan buka folder projek

Gunakan Python **3.12 atau lebih baharu** daripada https://www.python.org/downloads/.
Windows: pilih “Add Python to PATH” semasa pemasangan. Muat turun projek daripada GitHub dan ekstrak,
atau clone repository. Buka Terminal (macOS) atau PowerShell (Windows), kemudian `cd` ke folder projek.

macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Penggunaan `python.exe` secara terus tidak memerlukan perubahan execution policy PowerShell.
Untuk pemasangan runtime sahaja, gunakan `requirements.txt`. Fail dev memasang pytest juga.
`requirements.lock` merekod semua versi yang diuji dalam cloud Python 3.12; guna
`python -m pip install -r requirements.lock` untuk mengulang pemasangan versi yang sama.

## 2. Cuba satu listing contoh dahulu (tanpa token)

macOS:

```sh
python -m laily.demo --data-dir ./demo-data
python -m pytest -q
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m laily.demo --data-dir ./demo-data
.\.venv\Scripts\python.exe -m pytest -q
```

Demo menggunakan data rekaan berlabel, menjana dua draf dwibahasa dan menunjukkan ketersediaan belum disahkan.
Data demo disulitkan dalam folder sementara lalu dipadam; demo tidak menghubungi Telegram atau platform.
Ujian turut mensimulasikan forward Telegram, aliran pengesahan/eksport, sekatan pengguna dan penyimpanan tersulit.

## 3. Sediakan rahsia dalam `.env`

Dapatkan token bot **@LailyPropertyHelperBot** melalui akaun @BotFather yang menguruskannya.
Pastikan token itu milik bot yang betul. Jangan hantar token melalui chat ini atau commit ke GitHub.
Dapatkan ID angka akaun Telegram anda daripada sumber yang anda percayai; username bukan ID.

Jana kunci penyulitan (guna executable Windows di atas jika perlu):

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Salin hasilnya ke `.env` menggunakan editor tempatan:

```dotenv
TELEGRAM_BOT_TOKEN=<token daripada BotFather>
AUTHORIZED_TELEGRAM_USER_ID=<ID angka anda>
DATA_ENCRYPTION_KEY=<kunci dijana>
DATA_DIR=./data
```

Jangan guna kurungan contoh sebagai nilai sebenar. Simpan salinan kunci dalam password manager.
Jika kunci hilang, rekod tidak boleh dipulihkan. Menukar nilai kunci tidak memigrasikan data lama.
`.env` dan `data/` dikecualikan melalui `.gitignore`. Semak `git status` sebelum commit.
macOS/Linux: `chmod 600 .env`. Windows: hadkan akses folder kepada akaun anda menggunakan Security Properties.
Jangan kongsi akaun OS, folder data atau sandaran dengan pengguna yang tidak dibenarkan.

## 4. Jalankan bot

macOS:

```sh
python -m laily.bot
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m laily.bot
```

Hanya satu proses polling untuk token yang sama. Sambungan keluar HTTPS ke `api.telegram.org` diperlukan.
Tiada port masuk atau webhook diperlukan. Hentikan dengan Ctrl+C.
Kegagalan startup tidak mencetak exception yang mungkin mengandungi token.

Dalam chat peribadi dengan bot:

1. Hantar `/start`.
2. Forward satu listing, termasuk gambar atau album jika ada.
3. Lihat **Preview Facebook** dan **Preview Mudah**. Kedua-dua pratonton ialah draf teks, bukan posting.
4. Pilih **Edit** jika fakta tidak diekstrak. Format mesej JSON diterangkan oleh bot.
5. Sahkan ketersediaan dengan pemilik/ejen dan edit `availability` serta `availability_confirmed` jika benar.
6. Pilih **Save Draft**, kemudian sahkan kebenaran menggunakan listing dan gambar.
7. Pilih pakej Facebook atau Mudah untuk menerima ZIP bagi kemasukan manual.

Contoh format yang mudah diekstrak:

```text
Jenis: Kondominium
Lokasi: Kajang
Harga: RM 450,000
Bilik tidur: 3
Bilik air: 2
Keluasan: 1,000 sqft
Pegangan: Leasehold
Kemudahan: Kolam renang
Ejen: Nama dan nombor yang anda dibenarkan gunakan
```

Gunakan harga sewa dengan tempoh jelas, contohnya `RM 1,500 / bulan`. Bot tidak meneka mata wang,
tempoh sewa, ukuran atau ketersediaan. Nilai luar format ditandakan untuk semakan.
Teks fakta asal dikekalkan dalam kedua-dua bahasa supaya nama tempat dan butiran penting tidak diterjemah secara salah;
struktur dan label penerangan BM/EN berbeza. Terjemahan bebas dan pemahaman bahasa semula jadi tidak disediakan.

Contoh Edit:

```json
{"location":"Kajang", "price":"RM 450,000", "availability":"Tersedia, disahkan dengan ejen", "availability_confirmed":true}
```

Gunakan `null` untuk memadam fakta yang tidak tepat. `/help` membatalkan mod edit.

Arahan: `/start`, `/help`, `/drafts` (20 rekod terkini), `/facebook ID`, `/mudah ID`, `/status`.
Tanpa ID, arahan pratonton menggunakan draf terkini. Tiada UI carian atau pagination pada versi ini.

## Status

| Status | Maksud |
|---|---|
| LOCAL_DRAFT | Rekod tersimpan dalam SQLite tempatan |
| NEEDS_REVIEW | Fakta, harga, ketersediaan, hak guna atau calon pendua perlu disemak |
| INTEGRATION_UNAVAILABLE | Simpanan draf akaun belum disahkan/didayakan |
| PLATFORM_DRAFT_SAVED | Dikhaskan; tidak pernah dilaporkan oleh versi ini |
| ERROR | Operasi gagal; lihat audit tempatan |

Status tempatan, semakan dan platform adalah berasingan. ZIP masih boleh disediakan dengan status NEEDS_REVIEW;
pakej itu menyenaraikan isu untuk disemak dan tidak membuktikan listing sedia diterbitkan.

## Operasi dan keselamatan

- SQLite ialah stor tempatan untuk satu pengguna/proses, bukan perkhidmatan berskala banyak pengguna.
  Had 10 MB setiap foto Telegram. Gambar disimpan tersulit dalam rekod; album besar meningkatkan penggunaan memori.
- Audit append-only pada peringkat aplikasi dalam jadual `audit`: penerimaan, edit, akses ditolak,
  pratonton, pengesahan, eksport dan ralat. Audit tidak kebal pengubahan oleh pentadbir OS.
- Telegram bot chats bukan end-to-end encrypted. Pakej ZIP yang dihantar **tidak disulitkan** dan wujud dalam Telegram.
  Gunakan chat peribadi dan peranti selamat; padam eksport apabila tidak diperlukan.
- Tiada cookies atau sesi platform disimpan; tiada kata laluan Facebook/Mudah diperlukan.
- Backup: hentikan bot, salin `data/` ke storan tersulit dan simpan kunci secara berasingan.
  Untuk pemulihan, pulangkan folder dan kunci yang sama. Uji sandaran sebelum bergantung padanya.
- Pembersihan penuh: hentikan bot dan padam folder `data/` bersama semua sandaran serta eksport jika sesuai.
  Polisi pemadaman automatik, pemulihan bencana dan pengurusan banyak pengguna belum dibina.
- Sesuai sebagai asas berorientasikan produksi; sebelum operasi sebenar, uji forward daripada akaun dibenarkan,
  sekatan akaun lain, album sebenar, pemulihan sandaran dan restart dengan kelayakan sendiri.
  Ujian langsung Telegram memerlukan token dan belum disahkan oleh demo offline.
- Jika token terdedah, revoke melalui BotFather. Jangan matikan TLS atau cuba memintas sekatan platform.
