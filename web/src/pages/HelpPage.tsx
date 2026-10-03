import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GROUPS, TOPICS } from "../help/content";

export default function HelpPage() {
  const { topic } = useParams();
  const [q, setQ] = useState("");
  const [navOpen, setNavOpen] = useState(false); // hanya berpengaruh di layar kecil
  const current = TOPICS.find((t) => t.id === topic) ?? TOPICS[0];
  const idx = TOPICS.indexOf(current);
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return TOPICS;
    return TOPICS.filter((t) => `${t.title} ${t.summary} ${t.keywords}`.toLowerCase().includes(s));
  }, [q]);

  return (
    <div className="page wide help-layout">
      <aside className={`help-nav card ${navOpen ? "open" : ""}`} aria-label="Sub-menu panduan">
        <button className="btn small help-nav-toggle" onClick={() => setNavOpen((v) => !v)} aria-expanded={navOpen}>
          {navOpen ? "Tutup daftar topik ▴" : `Daftar topik (${TOPICS.length}) ▾`}
        </button>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Cari: template, blind test, status C…"
          aria-label="Cari panduan"
        />
        {GROUPS.map((g) => {
          const items = filtered.filter((t) => t.group === g);
          if (!items.length) return null;
          return (
            <nav key={g}>
              <div className="help-group">{g}</div>
              {items.map((t) => (
                <Link
                  key={t.id}
                  to={`/panduan/${t.id}`}
                  className={t.id === current.id ? "on" : ""}
                  onClick={() => setNavOpen(false)}
                >
                  {t.title}
                </Link>
              ))}
            </nav>
          );
        })}
        {!filtered.length && <p className="muted small">Tidak ada topik yang cocok.</p>}
      </aside>

      <article className="help-main card">
        <div className="help-crumb small muted">
          Panduan · {current.group}
        </div>
        <h1>{current.title}</h1>
        <p className="muted">{current.summary}</p>
        <div className="help-content">{current.body}</div>
        <div className="help-pager">
          {idx > 0 ? (
            <Link className="btn ghost" to={`/panduan/${TOPICS[idx - 1].id}`}>
              ← {TOPICS[idx - 1].title}
            </Link>
          ) : (
            <span />
          )}
          {idx < TOPICS.length - 1 && (
            <Link className="btn" to={`/panduan/${TOPICS[idx + 1].id}`}>
              {TOPICS[idx + 1].title} →
            </Link>
          )}
        </div>
      </article>
    </div>
  );
}
