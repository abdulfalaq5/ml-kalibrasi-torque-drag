// Footer disembunyikan sementara; ubah ke true untuk menampilkan lagi.
const SHOW_FOOTER = false;

export default function Footer() {
  if (!SHOW_FOOTER) return null;
  return (
    <footer className="footer">
      <div>Initiated by Bambang Setiawan</div>
      <div>In Collaboration with PHR RTO Team</div>
      <div>Prototype Version 1.0 | 2026</div>
    </footer>
  );
}
