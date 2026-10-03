import { Q_LABEL, QStatus } from "../api";

const CLS: Record<QStatus, string> = { A: "ok", B: "warn", C: "bad", X: "bad" };

export default function QualityBadge({ s, long }: { s: QStatus | null | undefined; long?: boolean }) {
  if (!s) return <span className="badge">–</span>;
  return (
    <span className={`badge ${CLS[s]}`} title={Q_LABEL[s]}>
      {s}
      {long ? ` · ${Q_LABEL[s]}` : ""}
    </span>
  );
}
