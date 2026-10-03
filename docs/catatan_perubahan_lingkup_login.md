# Draf catatan perubahan lingkup: login satu akun admin

*Draf untuk dilampirkan sebagai addendum / revisi dokumen. Sesuaikan nomor pasal dan nama pihak.*

**Latar belakang.** Proposal (Bagian 7, daftar "tidak termasuk") dan perjanjian paket 3 minggu
(Pasal 9 ayat 1, Lampiran A) menyebut aplikasi "tanpa login dan manajemen pengguna". Karena
aplikasi dibuka melalui domain publik dan memuat data rahasia, para pihak sepakat menambahkan
pengamanan login.

**Perubahan.** Lampiran A ditambah fitur nomor 9:

> 9. Login satu akun admin: satu username dan password (disimpan sebagai hash), sesi berlaku
> 8 jam, semua halaman dan data hanya dapat diakses setelah login, penguncian sementara setelah
> 5 kali salah, penggantian password melalui perintah administrasi.

**Yang tetap tidak termasuk:** lebih dari satu akun, peran/role, manajemen pengguna, SSO,
pemulihan password lewat email.

**Biaya dan jadwal:** ____ (tanpa tambahan biaya / tambahan Rp ____), jadwal tetap 15 hari kerja.

Disetujui,

| Pihak Pertama | Pihak Kedua |
|---|---|
| Nama: | Nama: |
| Tanggal: | Tanggal: |

---

# Draf catatan lingkup: impor massal dari folder (paket 6 minggu)

Proposal fitur 1 menyebut "unggah" file. Untuk 40+ sumur, file juga dapat ditaruh di folder
`data/inbox/<tipe>/<sumur>/` di server dan diimpor dengan tombol **Pindai folder** (file dipindah ke
`processed/` atau `rejected/` beserta alasan). Ini penyesuaian kecil pada fitur 1, tanpa tambahan
biaya/jadwal (atau: ____). Unggah manual tetap tersedia.

Disetujui: ______________________ (Pihak Pertama) ______________________ (Pihak Kedua)
