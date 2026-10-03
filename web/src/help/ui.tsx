import { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Komponen kecil untuk halaman panduan. */

export function Steps({ children }: { children: ReactNode }) {
  return <ol className="steps">{children}</ol>;
}

export function Step({ n, title, children }: { n: number | string; title: string; children?: ReactNode }) {
  return (
    <li className="step">
      <span className="step-n">{n}</span>
      <div className="step-body">
        <b>{title}</b>
        {children && <div className="help-text">{children}</div>}
      </div>
    </li>
  );
}

/** Nama tombol / menu di layar. */
export function Ui({ children }: { children: ReactNode }) {
  return <span className="ui-label">{children}</span>;
}

export function Go({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="btn small" to={to}>
      {children} →
    </Link>
  );
}

export function Tip({ children, kind = "tip" }: { children: ReactNode; kind?: "tip" | "warn" }) {
  return <div className={`help-tip ${kind}`}>{children}</div>;
}

export type FlowNode = { title: string; desc?: string; to?: string; tone?: "user" | "system" | "out" };

/** Diagram alur sederhana: kotak bersambung panah, membungkus di layar kecil. */
export function Flow({ nodes, title }: { nodes: FlowNode[]; title?: string }) {
  return (
    <figure className="flow">
      {title && <figcaption>{title}</figcaption>}
      <div className="flow-row">
        {nodes.map((n, i) => (
          <div key={i} className="flow-item">
            <div className={`flow-node ${n.tone ?? "system"}`}>
              <b>{n.title}</b>
              {n.desc && <span>{n.desc}</span>}
              {n.to && (
                <Link to={n.to} className="small">
                  buka
                </Link>
              )}
            </div>
            {i < nodes.length - 1 && <span className="flow-arrow" aria-hidden="true">→</span>}
          </div>
        ))}
      </div>
      <div className="flow-legend small muted">
        <span className="flow-dot user" /> tindakan pengguna <span className="flow-dot system" /> proses sistem{" "}
        <span className="flow-dot out" /> keluaran
      </div>
    </figure>
  );
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
