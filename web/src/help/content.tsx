import { ReactNode } from "react";
import { Flow, Go, Step, Steps, Table, Tip, Ui } from "./ui";

export type Topic = {
  id: string;
  group: string;
  title: string;
  summary: string;
  keywords: string;
  body: ReactNode;
};

export const GROUPS = ["Mulai", "Langkah demi langkah", "Use case", "Alur sistem", "Referensi"];

const STATUS_ROWS: ReactNode[][] = [
  [<b>A · Layak</b>, "Lolos semua pemeriksaan", "Ya"],
  [<b>B · Layak + peringatan</b>, "Lolos pemeriksaan wajib, ada catatan statistik", "Ya, ditandai"],
  [<b>C · Ditahan</b>, "Gagal pemeriksaan kritis (mis. data aktual < 8 titik, satuan salah)", "Tidak, menunggu tinjauan"],
  [<b>X · Dikecualikan</b>, "Dikecualikan engineer lewat tinjauan", "Tidak"],
];

export const TOPICS: Topic[] = [
  // ------------------------------------------------------------------ Mulai
  {
    id: "ringkasan",
    group: "Mulai",
    title: "Apa yang dilakukan sistem ini",
    summary: "Gambaran singkat, istilah, dan alur kerja dari data sampai hasil.",
    keywords: "ringkasan pengantar wellplan friction factor ml kalibrasi",
    body: (
      <>
        <p>
          Simulasi torque &amp; drag <b>WellPlan</b> memakai asumsi friction factor (FF), sehingga hasilnya sering berbeda dari
          pembacaan di lapangan. Sistem ini belajar dari sumur yang sudah dibor (rencana WellPlan + data aktual), lalu memberi
          <b> prediksi terkalibrasi</b> untuk sumur baru: hookload (pick up, slack off, rotating weight) dan torque (off/on bottom)
          per kedalaman.
        </p>
        <Flow
          title="Alur kerja garis besar"
          nodes={[
            { title: "1. Login", tone: "user" },
            { title: "2. Masukkan data sumur", desc: "folder / unggah / template", tone: "user", to: "/sumur" },
            { title: "3. Gerbang kualitas", desc: "status A/B/C", tone: "system", to: "/kualitas" },
            { title: "4. Bekukan dataset & latih", desc: "validasi per sumur", tone: "user", to: "/model" },
            { title: "5. Blind test", desc: "sekali, jujur", tone: "system", to: "/model" },
            { title: "6. Prediksi sumur baru", tone: "user", to: "/sumur" },
            { title: "7. Dashboard & ekspor", desc: "grafik, Excel, PDF", tone: "out", to: "/dashboard" },
            { title: "8. Evaluasi", desc: "setelah dibor", tone: "out", to: "/evaluasi" },
          ]}
        />
        <h3>Menu aplikasi</h3>
        <Table
          head={["Menu", "Untuk apa"]}
          rows={[
            [<Ui>Data sumur</Ui>, "Memasukkan data (pindai folder, unggah file/template), prediksi sumur baru, daftar sumur"],
            [<Ui>Kualitas data</Ui>, "Status A/B/C tiap sumur-section, alasan, keputusan tinjauan engineer, laporan kualitas"],
            [<Ui>Model</Ui>, "Membekukan dataset, melatih & membandingkan model, laporan akurasi, blind test"],
            [<Ui>Dashboard</Ui>, "Tiga grafik (Hookload, Torque, Selisih), batas aman, ekspor Excel dan PDF"],
            [<Ui>Evaluasi</Ui>, "Perbandingan prediksi dengan data aktual setelah sumur dibor"],
            [<Ui>Panduan</Ui>, "Halaman ini"],
          ]}
        />
        <h3>Istilah penting</h3>
        <Table
          head={["Istilah", "Arti"]}
          rows={[
            ["Sumur-section", "Satu file = satu section sumur (mis. 8,5\"). Kualitas dan prediksi dihitung per sumur-section."],
            ["FF (friction factor)", "Asumsi gesekan di WellPlan; tiap FF menghasilkan satu kurva rencana. Baseline = FF 0,3."],
            ["Out-of-fold", "Prediksi untuk sumur latih dari model yang tidak pernah melihat sumur itu (perbandingan jujur)."],
            ["Blind test", "~20% sumur dikunci sejak awal dan hanya diuji sekali di akhir."],
            ["Pita 10–90%", "Rentang ketidakpastian prediksi ML."],
          ]}
        />
      </>
    ),
  },
  {
    id: "login",
    group: "Mulai",
    title: "Login dan keluar",
    summary: "Masuk dengan akun admin, sesi 8 jam, penguncian 15 menit.",
    keywords: "login masuk password lupa terkunci keluar sesi",
    body: (
      <>
        <Steps>
          <Step n={1} title="Buka alamat aplikasi">
            Laptop: <code>http://127.0.0.1:8000</code>. Server: alamat <code>https://…</code> dari admin.
          </Step>
          <Step n={2} title="Isi Username dan Password">
            Klik ikon mata di kolom password untuk menampilkan/menyembunyikan password.
          </Step>
          <Step n={3} title="Klik Masuk">
            Anda diarahkan ke <Ui>Data sumur</Ui>. Sesi berlaku 8 jam.
          </Step>
          <Step n={4} title="Keluar">
            Klik <Ui>Keluar</Ui> di kanan atas.
          </Step>
        </Steps>
        <Tip kind="warn">
          Setelah 5 kali salah password, login terkunci 15 menit. Lupa password: operator menjalankan <code>make password</code> di
          server (sekaligus membuka kunci).
        </Tip>
      </>
    ),
  },

  // ------------------------------------------------------------------ Langkah
  {
    id: "siapkan-file",
    group: "Langkah demi langkah",
    title: "1. Menyiapkan file sumur",
    summary: "Format yang diterima: file asli WellPlan (A/B) atau template.",
    keywords: "format file excel xlsx xlsm roadmap laporan wellplan template section nama file",
    body: (
      <>
        <p>
          <b>Satu file Excel = satu section sumur.</b> Tiga jenis file diterima:
        </p>
        <Table
          head={["Jenis", "Ciri", "Perlu isian manual?"]}
          rows={[
            [
              <b>Laporan WellPlan (.xlsm)</b>,
              "sheet Summary, Tripping Load Analysis, Off Bottom Torque analysis, Survey Outputs, Drilling Data",
              "Tidak (nama, section, tipe terbaca otomatis)",
            ],
            [
              <b>Roadmap (.xlsx)</b>,
              "sheet Drag, Torque, T&D Actual Reading",
              "Pilih Tipe sumur (dan Section bila tidak ada di nama file)",
            ],
            [<b>Template</b>, "diunduh dari aplikasi; sheet Info Sumur, Drag, Torque, (T&D), Survey", "Tidak (isi di sheet Info Sumur)"],
          ]}
        />
        <h3>Aturan nama</h3>
        <ul>
          <li>
            Section di nama file: <code>_8.5in</code>, <code>8.50in</code>, <code>12.25 HS</code>, <code>22inHS</code>.
          </li>
          <li>
            Untuk impor folder: <code>data/inbox/&lt;J|S|Horizontal&gt;/&lt;nama sumur&gt;/&lt;file&gt;</code>. Nama folder = kode
            sumur, folder induk = tipe sumur.
          </li>
        </ul>
        <Tip>
          File .xlsm dibaca tanpa menjalankan macro. Angka yang tersimpan sebagai teks, satuan Klbs/kip/1000 lbf/ft-lbf/kft-lbf
          dikenali otomatis.
        </Tip>
      </>
    ),
  },
  {
    id: "impor-folder",
    group: "Langkah demi langkah",
    title: "2a. Impor massal dari folder",
    summary: "Cara tercepat untuk puluhan sumur: Pindai folder.",
    keywords: "impor massal folder inbox pindai scan processed rejected training",
    body: (
      <>
        <Steps>
          <Step n={1} title="Taruh file di folder inbox">
            Operator menyalin file ke <code>data/inbox/</code> (data client: <code>make inbox-training</code>).
          </Step>
          <Step n={2} title="Buka Data sumur → Impor massal dari folder">
            Panel menampilkan jumlah file yang menunggu.
          </Step>
          <Step n={3} title="Klik Pindai folder">
            ±30 detik untuk 94 file. File yang baru diubah &lt; 1 menit dilewati (mungkin masih disalin).
          </Step>
          <Step n={4} title="Baca hasil">
            Tab <Ui>Per sumur-section</Ui>: status kualitas A/B/C + alasan. Tab <Ui>Per file</Ui>: diterima / diterima dengan
            peringatan / duplikat / dilewati / ditolak + alasan.
          </Step>
        </Steps>
        <Tip>
          File diterima dipindah ke <code>data/processed/</code>, file ditolak ke <code>data/rejected/</code> beserta file
          <code> .alasan.txt</code>. File yang sama tidak diimpor dua kali; file yang isinya berubah menjadi versi baru.
        </Tip>
        <Go to="/sumur">Buka Data sumur</Go>
      </>
    ),
  },
  {
    id: "impor-unggah",
    group: "Langkah demi langkah",
    title: "2b. Unggah file atau template (data latih)",
    summary: "Unduh template, isi, unggah, lihat status kualitas.",
    keywords: "unggah upload template data latih impor file excel info sumur actual reading",
    body: (
      <>
        <Steps>
          <Step n={1} title="Data sumur → Impor file Excel (data latih) → Template data latih (.xlsx)">
            Punya file asli WellPlan? Lewati langkah 1–2, langsung unggah.
          </Step>
          <Step n={2} title="Isi template">
            <b>Info Sumur</b>: nama, section, tipe (J/S/Horizontal), block weight. <b>Drag</b>: kedalaman (ft) + hookload (kip)
            Tripping In / Tripping Out / Rotating Off Bottom per FF. <b>Torque</b>: Rotating On/Off Bottom (ft-lbf) per FF.
            <b> T&amp;D Actual Reading</b>: pembacaan lapangan (minimal 8 kedalaman). <b>Survey</b> opsional. Lihat sheet Contoh.
          </Step>
          <Step n={3} title="Unggah">
            Tarik file ke kotak unggah (bisa banyak). Untuk roadmap .xlsx asli, buka <Ui>Isian manual</Ui> dan pilih Tipe sumur.
          </Step>
          <Step n={4} title="Hasil">
            Tabel per file: status impor, sumur, section, tipe, <b>status kualitas</b>. A/B dipakai pada pelatihan berikutnya.
          </Step>
        </Steps>
        <Tip kind="warn">Jangan ubah judul kolom atau menyisipkan kolom di template. Angka memakai titik sebagai desimal.</Tip>
        <Go to="/sumur">Buka Data sumur</Go>
      </>
    ),
  },
  {
    id: "kualitas",
    group: "Langkah demi langkah",
    title: "3. Memeriksa kualitas data",
    summary: "Status A/B/C/X, membaca alasan, mencatat keputusan tinjauan.",
    keywords: "kualitas data status a b c x ditahan tinjauan review terima kecualikan perbaiki laporan",
    body: (
      <>
        <Table head={["Status", "Arti", "Masuk training?"]} rows={STATUS_ROWS} />
        <Steps>
          <Step n={1} title="Buka Kualitas data">Kotak A/B/C/X di atas bisa diklik untuk menyaring.</Step>
          <Step n={2} title="Klik baris sumur">Semua pemeriksaan tampil: kritis (merah), peringatan (kuning), lolos.</Step>
          <Step n={3} title="Catat keputusan">
            Pilih <Ui>Terima (dengan catatan)</Ui> (C → B), <Ui>Kecualikan dari training</Ui> (X), atau{" "}
            <Ui>Perbaiki (minta file baru)</Ui> (tetap C). Isi alasan, klik <Ui>Simpan keputusan</Ui>. Nama dan waktu tercatat.
          </Step>
          <Step n={4} title="Unduh laporan">
            <Ui>Unduh laporan kualitas (.xlsx)</Ui> untuk dikirim ke client (daftar sumur yang perlu diperbaiki).
          </Step>
        </Steps>
        <h3>Pemeriksaan yang dilakukan</h3>
        <Table
          head={["Kritis (gagal → C)", "Peringatan (→ B)"]}
          rows={[
            ["Rencana pick up & slack off ada", "Rasio aktual/WellPlan menyimpang dari sumur sekelas"],
            ["Satuan wajar (tidak beda ~1000×)", "Lompatan tak wajar antar titik"],
            ["Nilai fisik wajar (hookload > 0, torsi ≥ 0)", "Nilai berulang persis (salin tempel)"],
            ["Slack off ≤ rotating ≤ pick up", "Titik jauh lebih sedikit dari sumur sekelas"],
            ["≥ 8 titik aktual di rentang WellPlan", "Rasio torsi jauh dari 1, urutan kedalaman di file turun"],
            ["Section & tipe diketahui, bukan duplikat", ""],
          ]}
        />
        <Go to="/kualitas">Buka Kualitas data</Go>
      </>
    ),
  },
  {
    id: "latih",
    group: "Langkah demi langkah",
    title: "4. Membekukan dataset dan melatih model",
    summary: "Dataset beku + blind test terkunci, lalu bandingkan algoritma.",
    keywords: "model latih training bekukan dataset algoritma xgboost random forest ridge svr mlp ditahan aktif",
    body: (
      <>
        <Steps>
          <Step n={1} title="Model → Dataset (versi beku) → Bekukan dataset baru">
            Mengambil semua sumur berstatus A/B, menyimpan snapshot + hash. Dataset pertama mengunci ~20% sumur sebagai blind test.
            (Bila belum dibekukan, pelatihan pertama membekukan otomatis.)
          </Step>
          <Step n={2} title="Model → Latih model">
            Pilih <Ui>Dataset</Ui> (bawaan: terbaru) dan <Ui>Algoritma</Ui>: <i>Bandingkan semua</i> (Ridge, XGBoost, Random
            Forest, SVR; centang <Ui>Sertakan MLP</Ui> bila perlu). Klik <Ui>Latih model</Ui>. Proses ±3–5 menit, status
            diperbarui otomatis.
          </Step>
          <Step n={3} title="Lihat status di Riwayat model">
            <b>selesai + aktif</b> = dipakai untuk prediksi. <b>ditahan</b> = lebih buruk dari model aktif (tidak diaktifkan
            otomatis; bisa <Ui>Aktifkan</Ui> manual bila yakin).
          </Step>
        </Steps>
        <Flow
          title="Yang terjadi saat Latih model"
          nodes={[
            { title: "Dataset beku", desc: "sumur blind disisihkan" },
            { title: "Uji manfaat fitur", desc: "dipakai bila error turun ≥1%" },
            { title: "Semua algoritma", desc: "validasi per sumur (5 fold)" },
            { title: "Pilih terbaik", desc: "per operasi" },
            { title: "Kurva belajar, SHAP", desc: "pita 10–90%" },
            { title: "Banding model aktif", desc: "aktif / ditahan", tone: "out" },
          ]}
        />
        <Go to="/model">Buka Model</Go>
      </>
    ),
  },
  {
    id: "laporan-model",
    group: "Langkah demi langkah",
    title: "5. Membaca laporan model dan blind test",
    summary: "Arti RMSE, 'ML lebih dekat', tab analisis, blind test sekali.",
    keywords: "laporan model rmse mape r2 ml lebih dekat kurva belajar shap blind test section tipe kedalaman",
    body: (
      <>
        <Steps>
          <Step n={1} title="Klik Laporan di Riwayat model">Tabel utama per operasi muncul di bawah.</Step>
          <Step n={2} title="Baca tabel utama">
            <b>RMSE WellPlan → RMSE ML</b>: rata-rata kesalahan (makin kecil makin baik), satuan kN / kN·m. <b>ML vs WellPlan</b>:
            persen perbaikan. <b>ML lebih dekat</b>: persen titik ketika ML lebih dekat ke aktual daripada WellPlan.
          </Step>
          <Step n={3} title="Pakai tab analisis">
            <Ui>Section × tipe</Ui> (baris kuning = &lt; 3 sumur, kurang andal), <Ui>Kedalaman</Ui>, <Ui>Per sumur</Ui>,
            <Ui>Titik terburuk</Ui>, <Ui>Algoritma</Ui>, <Ui>Tunggal vs kombinasi</Ui>, <Ui>Kurva belajar</Ui> (turun = tambah sumur
            membantu), <Ui>SHAP</Ui> (fitur paling berpengaruh).
          </Step>
          <Step n={4} title="Jalankan blind test (sekali)">
            Setelah model final dipilih, klik <Ui>Jalankan blind test</Ui>. Hasilnya dicatat apa adanya dan tidak bisa diulang.
          </Step>
          <Step n={5} title="Unduh untuk client">
            <Ui>Laporan (.xlsx)</Ui> (semua tabel) dan <Ui>Ringkasan PDF</Ui> (metrik, blind test, kurva belajar, SHAP).
          </Step>
        </Steps>
        <Tip>
          Angka validasi silang dihitung pada sumur yang tidak dilihat model, dan blind test pada sumur yang dikunci sejak awal. Bila
          ML tidak lebih baik di kombinasi tertentu, laporan menunjukkannya apa adanya.
        </Tip>
      </>
    ),
  },
  {
    id: "prediksi",
    group: "Langkah demi langkah",
    title: "6. Prediksi sumur baru",
    summary: "Unggah rencana WellPlan sumur yang akan dibor, hasil langsung keluar.",
    keywords: "prediksi sumur baru template rencana wellplan hasil prediksi excel pdf dashboard peringatan",
    body: (
      <>
        <Steps>
          <Step n={1} title="Data sumur → Prediksi sumur baru → Template sumur baru (.xlsx)">
            Atau langsung pakai file WellPlan asli sumur itu.
          </Step>
          <Step n={2} title="Isi Info Sumur, Drag, Torque (Survey bila ada)">Tanpa data aktual.</Step>
          <Step n={3} title="Unggah satu file">Sistem mengimpor, memeriksa, lalu memprediksi dengan model aktif.</Step>
          <Step n={4} title="Baca hasil">
            Tabel per operasi di kedalaman akhir: WellPlan (FF 0,3), <b>Prediksi ML</b>, rentang ML 10–90%, ML − WellPlan. Tombol{" "}
            <Ui>Buka dashboard</Ui>, <Ui>Hasil prediksi (.xlsx)</Ui>, <Ui>Ringkasan (PDF)</Ui>.
          </Step>
        </Steps>
        <Tip kind="warn">
          Perhatikan peringatan: section/tipe jarang di data latih, kedalaman di luar rentang latih, atau survey kosong berarti
          prediksi kurang andal.
        </Tip>
        <Go to="/sumur">Buka Data sumur</Go>
      </>
    ),
  },
  {
    id: "dashboard",
    group: "Langkah demi langkah",
    title: "7. Membaca dashboard",
    summary: "Tiga grafik, zoom, selisih, penandaan interval, pita ketidakpastian.",
    keywords: "dashboard grafik hookload torque selisih zoom pita interval ambang filter model satuan out-of-fold",
    body: (
      <>
        <Steps>
          <Step n={1} title="Pilih sumur">
            Saring dengan <Ui>Section</Ui>, <Ui>Tipe sumur</Ui>, <Ui>Kualitas</Ui>, lalu pilih <Ui>Sumur</Ui>. <Ui>Satuan</Ui>:
            imperial (ft, klbf, ft-lbf) atau SI. <Ui>Model</Ui>: aktif atau versi lain.
          </Step>
          <Step n={2} title="Baca tiga panel">
            <b>Hookload</b> dan <b>Torque</b>: WellPlan <span style={{ color: "#2a78d6" }}>biru</span>, ML{" "}
            <span style={{ color: "#eb6834" }}>oranye</span> (+ arsiran pita 10–90%), Aktual titik{" "}
            <span style={{ color: "#1baf7a" }}>hijau</span>. Garis penuh = pick up / torque off bottom, putus-putus = slack off /
            torque on bottom, titik-titik = rotating.
          </Step>
          <Step n={3} title="Panel Selisih">
            Selisih = A − B. <b>Kanan (+) = A lebih tinggi</b>, kiri (−) = lebih rendah. Pilih target dan <Ui>Absolut</Ui> /{" "}
            <Ui>Persen</Ui>.
          </Step>
          <Step n={4} title="Zoom">
            Tarik kotak di grafik; klik dua kali untuk kembali; <Ui>Reset zoom</Ui> untuk semua panel. Dengan{" "}
            <Ui>Samakan kedalaman saat zoom</Ui>, ketiga panel ikut. Arahkan kursor: garis penuntun muncul di ketiga panel dan
            nilainya tampil di bar bawah.
          </Step>
          <Step n={5} title="Penandaan interval">
            Atur seri dan ambang |selisih| di <Ui>Penandaan interval</Ui>; interval yang lewat ambang diarsir kuning dan didaftar di
            bawah grafik bersama tabel 5 selisih terbesar.
          </Step>
        </Steps>
        <Tip>
          Untuk sumur yang ikut melatih model, garis ML adalah prediksi <b>out-of-fold</b> (model yang tidak melihat sumur itu),
          sehingga perbandingan dengan aktual tetap jujur.
        </Tip>
        <Go to="/dashboard">Buka Dashboard</Go>
      </>
    ),
  },
  {
    id: "batas-aman",
    group: "Langkah demi langkah",
    title: "8. Batas aman",
    summary: "Menetapkan batas hookload/torsi dan melihat kedalaman saat batas tersentuh.",
    keywords: "batas aman limit torque top drive hookload slack off minimum kedalaman menyentuh margin",
    body: (
      <>
        <Steps>
          <Step n={1} title="Dashboard → Batas aman dan deteksi interval">Di bawah grafik.</Step>
          <Step n={2} title="Tambah batas">
            Pilih operasi (pick up maks, slack off min, torque on bottom maks, …), isi nilai dalam satuan tampilan, pilih berlaku
            untuk <i>semua sumur section ini</i> atau <i>sumur ini saja</i>, klik <Ui>Tambah batas</Ui>.
          </Step>
          <Step n={3} title="Baca hasil">
            Tabel: kedalaman pertama ketika ML, batas pita ML, dan WellPlan menyentuh batas (<i>aman</i> = tidak menyentuh), serta
            margin minimum. Di grafik: garis merah putus-titik pada nilai batas dan arsiran merah di bawah kedalaman tersentuh.
          </Step>
        </Steps>
        <Tip>Batas sumur menimpa batas section untuk operasi yang sama. Batas ikut tercetak di Excel (sheet Batas aman) dan PDF.</Tip>
      </>
    ),
  },
  {
    id: "ekspor",
    group: "Langkah demi langkah",
    title: "9. Ekspor Excel dan PDF",
    summary: "Mengunduh hasil per sumur, laporan model, laporan kualitas.",
    keywords: "ekspor excel pdf unduh laporan hasil prediksi download",
    body: (
      <>
        <Steps>
          <Step n={1} title="Dashboard → Ekspor Excel">
            Sheet <b>Info</b>, <b>Drag</b>, <b>Torque</b>, <b>T&amp;D Actual Reading</b> (struktur seperti file roadmap + kolom ML,
            pita, selisih), <b>Selisih</b>, <b>Grafik</b> (3 grafik), <b>Batas aman</b>, <b>Metrik</b>.
          </Step>
          <Step n={2} title="Dashboard → PDF">Ringkasan 2 halaman: status kualitas, versi model & dataset, metrik, batas aman, tiga grafik.</Step>
          <Step n={3} title="Model → Laporan (.xlsx) / Ringkasan PDF">Laporan akurasi model untuk client.</Step>
          <Step n={4} title="Kualitas data → Unduh laporan kualitas (.xlsx)">Status semua sumur dan alasan.</Step>
        </Steps>
        <Tip>Grafik selisih di Excel mengikuti target yang dipilih di panel Selisih saat menekan Ekspor.</Tip>
      </>
    ),
  },
  {
    id: "evaluasi",
    group: "Langkah demi langkah",
    title: "10. Evaluasi setelah sumur dibor",
    summary: "Prediksi lama otomatis dibandingkan dengan data aktual.",
    keywords: "evaluasi prediksi aktual setelah dibor perbandingan akurasi",
    body: (
      <>
        <Steps>
          <Step n={1} title="Sumur pernah diprediksi">Lewat Prediksi sumur baru (sebelum dibor).</Step>
          <Step n={2} title="Unggah file berisi data aktualnya">
            Di <Ui>Impor file Excel (data latih)</Ui>, dengan nama sumur dan section yang sama.
          </Step>
          <Step n={3} title="Buka Evaluasi">
            Per operasi: RMSE WellPlan vs ML terhadap aktual dan persen titik ketika ML lebih dekat.
          </Step>
        </Steps>
        <Go to="/evaluasi">Buka Evaluasi</Go>
      </>
    ),
  },

  // ------------------------------------------------------------------ Use case
  {
    id: "uc-onboarding",
    group: "Use case",
    title: "UC-1 · Memulai dengan data 40+ sumur",
    summary: "Dari folder data client sampai model pertama dan laporan.",
    keywords: "use case onboarding awal 40 sumur pertama kali",
    body: (
      <>
        <p>
          <b>Aktor:</b> engineer + operator. <b>Tujuan:</b> model pertama dan laporan akurasi untuk client.
        </p>
        <Flow
          nodes={[
            { title: "Salin data ke inbox", desc: "make inbox-training", tone: "user" },
            { title: "Pindai folder", tone: "user", to: "/sumur" },
            { title: "Tinjau status C", tone: "user", to: "/kualitas" },
            { title: "Bekukan dataset v1", desc: "blind test terkunci", tone: "user", to: "/model" },
            { title: "Latih: bandingkan semua", tone: "system" },
            { title: "Jalankan blind test", tone: "user" },
            { title: "Laporan model + kualitas", tone: "out" },
          ]}
        />
        <Steps>
          <Step n={1} title="Pindai folder">Pastikan tidak ada file ditolak; bila ada, baca alasannya.</Step>
          <Step n={2} title="Kualitas data">Untuk setiap status C: terima / kecualikan / perbaiki dengan alasan.</Step>
          <Step n={3} title="Model">Bekukan dataset, latih (Bandingkan semua), baca laporan, jalankan blind test.</Step>
          <Step n={4} title="Kirim ke client">Laporan kualitas (.xlsx), laporan model (.xlsx + PDF).</Step>
        </Steps>
      </>
    ),
  },
  {
    id: "uc-tambah",
    group: "Use case",
    title: "UC-2 · Menambah sumur dan melatih ulang",
    summary: "Data sumur baru yang sudah dibor masuk, model diperbarui dengan aman.",
    keywords: "use case tambah data latih ulang retrain versi baru ditahan",
    body: (
      <>
        <Steps>
          <Step n={1} title="Masukkan data">Pindai folder atau unggah file/template (data latih).</Step>
          <Step n={2} title="Periksa kualitas">Tinjau status C sumur baru.</Step>
          <Step n={3} title="Model → Bekukan dataset baru">Versi naik; sumur blind test lama tetap terkunci.</Step>
          <Step n={4} title="Latih model dengan dataset baru">
            Bila lebih baik → otomatis aktif. Bila lebih buruk → <b>ditahan</b>; model lama tetap dipakai.
          </Step>
        </Steps>
        <Tip>Setiap model mencatat versi dataset, jadi hasil lama selalu bisa ditelusuri dan dibandingkan.</Tip>
      </>
    ),
  },
  {
    id: "uc-prediksi",
    group: "Use case",
    title: "UC-3 · Prediksi sebelum mengebor + batas aman",
    summary: "Engineer menyiapkan program pengeboran sumur baru.",
    keywords: "use case prediksi sebelum bor program pengeboran batas aman torque limit",
    body: (
      <>
        <Flow
          nodes={[
            { title: "Template sumur baru", tone: "user" },
            { title: "Isi rencana WellPlan", tone: "user" },
            { title: "Unggah → prediksi", tone: "system" },
            { title: "Dashboard + batas aman", tone: "user" },
            { title: "Excel / PDF ke tim", tone: "out" },
          ]}
        />
        <Steps>
          <Step n={1} title="Prediksi sumur baru">Unduh template, isi, unggah. Catat peringatan.</Step>
          <Step n={2} title="Buka dashboard">Bandingkan ML dengan WellPlan; perhatikan pita 10–90%.</Step>
          <Step n={3} title="Tambah batas aman">Mis. torsi top drive. Lihat kedalaman ketika pita atas ML menyentuh batas.</Step>
          <Step n={4} title="Ekspor">Excel (detail per kedalaman) dan PDF (ringkasan) untuk rapat program pengeboran.</Step>
        </Steps>
      </>
    ),
  },
  {
    id: "uc-evaluasi",
    group: "Use case",
    title: "UC-4 · Mengevaluasi setelah pengeboran",
    summary: "Mengukur seberapa tepat prediksi sebelumnya.",
    keywords: "use case evaluasi pasca bor akurasi prediksi",
    body: (
      <Steps>
        <Step n={1} title="Unggah data aktual sumur yang sudah diprediksi">Nama sumur & section sama.</Step>
        <Step n={2} title="Buka Evaluasi">Bandingkan RMSE WellPlan vs ML dan persen titik ML lebih dekat.</Step>
        <Step n={3} title="Data masuk ke latihan berikutnya">
          Bila status kualitas A/B, sumur ini ikut melatih model berikutnya (UC-2).
        </Step>
      </Steps>
    ),
  },
  {
    id: "uc-masalah",
    group: "Use case",
    title: "UC-5 · File ditolak atau sumur berstatus C",
    summary: "Menangani data bermasalah dan meminta perbaikan ke client.",
    keywords: "use case ditolak gagal status c perbaiki file salah satuan titik sedikit",
    body: (
      <>
        <Table
          head={["Pesan", "Arti", "Tindakan"]}
          rows={[
            ["Format tidak dikenali", "Bukan roadmap atau laporan WellPlan", "Pakai template, atau periksa nama sheet"],
            ["Section tidak ditemukan", "Ukuran lubang tidak ada di nama file/isi", "Isi Section di Isian manual / Info Sumur"],
            ["Hanya N titik aktual (minimum 8)", "Data aktual terlalu sedikit", "Terima dengan catatan, atau minta data lengkap"],
            ["Kemungkinan salah satuan", "Nilai beda ~1000× dari WellPlan", "Periksa satuan kolom (kip vs lbf), perbaiki file"],
            ["Urutan SO ≤ ROT ≤ PU dilanggar", "Kolom tertukar atau salah catat", "Periksa kolom; perbaiki file"],
            ["Tidak ada data aktual", "File hanya rencana", "Untuk prediksi tidak masalah; untuk latihan perlu data aktual"],
          ]}
        />
        <Steps>
          <Step n={1} title="Kualitas data → klik sumur → catat keputusan Perbaiki">Dengan alasan yang jelas.</Step>
          <Step n={2} title="Unduh laporan kualitas">Kirim daftar sumur yang perlu diperbaiki ke client.</Step>
          <Step n={3} title="File perbaikan datang">Unggah/pindai lagi; versi baru menggantikan yang lama dan kualitas dihitung ulang.</Step>
        </Steps>
      </>
    ),
  },

  // ------------------------------------------------------------------ Alur sistem
  {
    id: "alur-data",
    group: "Alur sistem",
    title: "Alur data: dari file sampai prediksi",
    summary: "Apa yang dikerjakan sistem di balik layar pada setiap tahap.",
    keywords: "alur flow sistem proses data parser impor database dataset model prediksi",
    body: (
      <>
        <Flow
          title="1. Masuk data"
          nodes={[
            { title: "File Excel", desc: "folder / unggah / template", tone: "user" },
            { title: "Deteksi format", desc: "dari nama sheet" },
            { title: "Parser A / B", desc: "rencana per FF, aktual, survey" },
            { title: "Konversi satuan", desc: "asli + SI disimpan" },
            { title: "Database", desc: "per sumur-section", tone: "out" },
          ]}
        />
        <Flow
          title="2. Kualitas dan dataset"
          nodes={[
            { title: "Gerbang kualitas", desc: "9 kritis + 5 statistik" },
            { title: "Status A/B/C", desc: "+ tinjauan engineer" },
            { title: "Pasangkan aktual ↔ WellPlan", desc: "di kedalaman sama" },
            { title: "Fitur", desc: "WellPlan FF 0,3 & 0,5, survey, …" },
            { title: "Dataset beku", desc: "hash + blind test", tone: "out" },
          ]}
        />
        <Flow
          title="3. Model dan hasil"
          nodes={[
            { title: "Latih & validasi per sumur", desc: "5 fold" },
            { title: "Model aktif", desc: "atau ditahan" },
            { title: "Prediksi", desc: "grid kedalaman + pita" },
            { title: "Dashboard, batas aman", tone: "out" },
            { title: "Excel / PDF / Evaluasi", tone: "out" },
          ]}
        />
      </>
    ),
  },
  {
    id: "alur-status",
    group: "Alur sistem",
    title: "Siklus status: file, sumur, model",
    summary: "Arti setiap status dan perubahannya.",
    keywords: "status siklus file diterima ditolak diganti sumur a b c x model antri berjalan selesai ditahan gagal aktif",
    body: (
      <>
        <h3>File</h3>
        <Flow
          nodes={[
            { title: "diproses" },
            { title: "ok / peringatan", desc: "diterima", tone: "out" },
            { title: "diganti", desc: "bila versi baru masuk" },
          ]}
        />
        <p className="small muted">Atau <b>gagal</b> (ditolak, dengan alasan). File identik tidak diimpor ulang (duplikat).</p>
        <h3>Sumur-section</h3>
        <Flow
          nodes={[
            { title: "Diimpor" },
            { title: "Pemeriksaan otomatis" },
            { title: "A / B / C" },
            { title: "Tinjauan", desc: "terima → B, kecualikan → X, perbaiki → C", tone: "user" },
            { title: "A/B masuk dataset", tone: "out" },
          ]}
        />
        <Table head={["Status", "Arti", "Masuk training?"]} rows={STATUS_ROWS} />
        <h3>Model</h3>
        <Flow
          nodes={[
            { title: "antri" },
            { title: "berjalan" },
            { title: "selesai + aktif", desc: "lebih baik / pertama", tone: "out" },
            { title: "atau ditahan", desc: "lebih buruk dari aktif" },
          ]}
        />
        <p className="small muted">
          <b>gagal</b>: pesan galat tampil di Riwayat model (mis. sumur latih kurang dari 5). Blind test: <b>sudah</b> = tidak bisa
          diulang.
        </p>
      </>
    ),
  },

  // ------------------------------------------------------------------ Referensi
  {
    id: "keluaran",
    group: "Referensi",
    title: "Daftar keluaran sistem",
    summary: "Semua file/hasil yang bisa diperoleh dan dari menu mana.",
    keywords: "output keluaran hasil laporan file unduh",
    body: (
      <Table
        head={["Keluaran", "Dari mana", "Isi"]}
        rows={[
          ["Template isian", "Data sumur → Impor / Prediksi → langkah 1", "Template data latih & sumur baru (+ Petunjuk, Contoh)"],
          ["Hasil pindai folder", "Data sumur → Pindai folder", "Status per file dan per sumur-section"],
          ["Laporan kualitas data (.xlsx)", "Kualitas data", "Status A/B/C/X, skor, alasan, tinjauan"],
          ["Dataset beku (.csv.gz)", "Model → Dataset → Unduh", "Data latih + hash, sumur blind"],
          ["Laporan model (.xlsx / PDF)", "Model → Laporan", "Akurasi per operasi/section/tipe/kedalaman/sumur, blind test, kurva belajar, SHAP"],
          ["Hasil prediksi sumur baru", "Data sumur → Prediksi sumur baru", "Tabel ringkas + Excel + PDF"],
          ["Dashboard", "Dashboard", "3 grafik, pita, batas aman, interval ditandai"],
          ["Ekspor per sumur (.xlsx / PDF)", "Dashboard → Ekspor Excel / PDF", "Drag, Torque, T&D + ML & selisih, grafik, batas aman"],
          ["Evaluasi", "Evaluasi", "Prediksi vs aktual setelah dibor"],
        ]}
      />
    ),
  },
  {
    id: "faq",
    group: "Referensi",
    title: "FAQ dan pemecahan masalah",
    summary: "Pertanyaan yang sering muncul.",
    keywords: "faq tanya masalah error tidak bisa kenapa",
    body: (
      <Table
        head={["Pertanyaan", "Jawaban"]}
        rows={[
          ["Apakah harus memakai template?", "Tidak. File asli WellPlan (.xlsm laporan atau .xlsx roadmap) bisa langsung diunggah. Untuk roadmap, pilih Tipe sumur di Isian manual."],
          ["Tombol Pindai folder tidak aktif", "Folder inbox kosong. Operator menyalin file ke data/inbox."],
          ["File 'dilewati' saat pindai", "File baru diubah < 1 menit. Tunggu, lalu pindai lagi."],
          ["Mengapa sumur saya status C?", "Buka Kualitas data, klik sumurnya: alasan kritis tertulis. Lihat UC-5."],
          ["Model baru 'ditahan'", "Akurasinya lebih buruk dari model aktif. Model lama tetap dipakai; bisa diaktifkan manual."],
          ["Bisakah blind test diulang?", "Tidak, sengaja hanya sekali per model agar hasilnya jujur."],
          ["Grafik ML tidak muncul", "Sumur belum diprediksi: klik Prediksi ulang di dashboard, atau belum ada model aktif."],
          ["Satuan grafik", "Pilih Satuan imperial (ft, klbf, ft-lbf) atau SI (m, kN, kN·m) di dashboard."],
          ["Login terkunci", "Tunggu 15 menit, atau operator menjalankan make password."],
        ]}
      />
    ),
  },
];
