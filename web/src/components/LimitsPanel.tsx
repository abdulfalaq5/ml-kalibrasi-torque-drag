import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmt, Op, OP_LABEL, OPS, Profile } from "../api";

const DEFAULT_KIND: Record<Op, "max" | "min"> = {
  pick_up: "max",
  slack_off: "min",
  rotating_weight: "max",
  torque_off_bottom: "max",
  torque_on_bottom: "max",
};

export default function LimitsPanel({ profile }: { profile: Profile }) {
  const qc = useQueryClient();
  const [op, setOp] = useState<Op>("pick_up");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<"well" | "section">("section");
  const [note, setNote] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["profile"] });
  const add = useMutation({
    mutationFn: () =>
      api.post("/api/limits", {
        operation: op,
        value: Number(value),
        kind: DEFAULT_KIND[op],
        unit_system: profile.unit_system,
        note: note || null,
        ...(scope === "well" ? { well_id: profile.well.id } : { section_in: profile.well.section_in }),
      }),
    onSuccess: () => {
      setValue("");
      setNote("");
      refresh();
    },
    onError: (e) => alert((e as Error).message),
  });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/limits/${id}`), onSuccess: refresh });
  const rows = OPS.flatMap((o) => (profile.operations[o].limits ?? []).map((l) => ({ op: o, ...l })));
  const du = profile.depth_unit;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value) add.mutate();
  };

  return (
    <section className="card">
      <h3>Batas aman dan deteksi interval</h3>
      <p className="muted small">
        Batas dari client (mis. kapasitas hookload, batas torsi top drive, slack off minimum). Berlaku untuk sumur ini saja atau untuk
        semua sumur di section {profile.well.section_in}". Sistem menghitung kedalaman pertama ketika kurva ML, batas atas/bawah pita
        ketidakpastian, dan WellPlan melewati batas. Area di bawah kedalaman itu diarsir merah di grafik.
      </p>
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Operasi</th>
                <th>Batas</th>
                <th>Berlaku</th>
                <th className="num">ML menyentuh ({du})</th>
                <th className="num">Pita ML menyentuh ({du})</th>
                <th className="num">WellPlan menyentuh ({du})</th>
                <th className="num">Margin minimum ML</th>
                <th>Catatan</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.cross_ml !== null ? "row-bad" : ""}>
                  <td>{OP_LABEL[r.op]}</td>
                  <td>
                    {r.kind === "max" ? "maks" : "min"} {fmt(r.value)} {profile.operations[r.op].unit}
                  </td>
                  <td>{r.scope === "sumur" ? "sumur ini" : `section ${profile.well.section_in}"`}</td>
                  <td className="num">{r.cross_ml === null ? "aman" : fmt(r.cross_ml, 0)}</td>
                  <td className="num">{r.cross_ml_band === null ? "aman" : fmt(r.cross_ml_band, 0)}</td>
                  <td className="num">{r.cross_wellplan === null ? "aman" : fmt(r.cross_wellplan, 0)}</td>
                  <td className="num">{fmt(r.margin_ml)}</td>
                  <td className="small">{r.note ?? ""}</td>
                  <td>
                    <button className="btn small ghost" onClick={() => confirm("Hapus batas ini?") && del.mutate(r.id)}>
                      Hapus
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted small">Belum ada batas untuk sumur/section ini.</p>
      )}
      <form className="row gap wrap" onSubmit={submit} style={{ marginTop: 8 }}>
        <select value={op} onChange={(e) => setOp(e.target.value as Op)}>
          {OPS.map((o) => (
            <option key={o} value={o}>
              {OP_LABEL[o]} ({DEFAULT_KIND[o] === "max" ? "maks" : "min"})
            </option>
          ))}
        </select>
        <input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} placeholder="nilai" required style={{ width: 110 }} />
        <span className="small">{profile.operations[op].unit}</span>
        <select value={scope} onChange={(e) => setScope(e.target.value as "well" | "section")}>
          <option value="section">semua sumur section {profile.well.section_in}"</option>
          <option value="well">sumur ini saja</option>
        </select>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="catatan (opsional)" />
        <button className="btn small primary" disabled={add.isPending}>
          Tambah batas
        </button>
      </form>
    </section>
  );
}
