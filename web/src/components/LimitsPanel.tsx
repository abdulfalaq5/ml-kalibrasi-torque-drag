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
      <h3>Operating limits</h3>
      <p className="muted small">
        Limits from the client (e.g. hookload capacity, top drive torque limit, minimum slack off), for this well only or for
        all wells in section {profile.well.section_in}". The system finds the first depth where the ML prediction, the
        P10–P90 band bound, and the T&amp;D Model reach the limit. Limits are dotted red lines in the charts; the area below the ML
        crossing depth is shaded red.
      </p>
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Limit</th>
                <th>Applies to</th>
                <th className="num">ML reaches ({du})</th>
                <th className="num">ML band reaches ({du})</th>
                <th className="num">T&amp;D Model reaches ({du})</th>
                <th className="num">Minimum ML margin</th>
                <th>Note</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.cross_ml !== null ? "row-bad" : ""}>
                  <td>{OP_LABEL[r.op]}</td>
                  <td>
                    {r.kind === "max" ? "max" : "min"} {fmt(r.value)} {profile.operations[r.op].unit}
                  </td>
                  <td>{r.scope === "well" ? "this well" : `section ${profile.well.section_in}"`}</td>
                  <td className="num">{r.cross_ml === null ? "not reached" : fmt(r.cross_ml, 0)}</td>
                  <td className="num">{r.cross_ml_band === null ? "not reached" : fmt(r.cross_ml_band, 0)}</td>
                  <td className="num">{r.cross_wellplan === null ? "not reached" : fmt(r.cross_wellplan, 0)}</td>
                  <td className="num">{fmt(r.margin_ml)}</td>
                  <td className="small">{r.note ?? ""}</td>
                  <td>
                    <button className="btn small ghost" onClick={() => confirm("Delete this limit?") && del.mutate(r.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted small">No limits for this well/section yet.</p>
      )}
      <form className="row gap wrap" onSubmit={submit} style={{ marginTop: 8 }}>
        <select value={op} onChange={(e) => setOp(e.target.value as Op)}>
          {OPS.map((o) => (
            <option key={o} value={o}>
              {OP_LABEL[o]} ({DEFAULT_KIND[o] === "max" ? "max" : "min"})
            </option>
          ))}
        </select>
        <input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} placeholder="value" required style={{ width: 110 }} />
        <span className="small">{profile.operations[op].unit}</span>
        <select value={scope} onChange={(e) => setScope(e.target.value as "well" | "section")}>
          <option value="section">all wells in section {profile.well.section_in}"</option>
          <option value="well">this well only</option>
        </select>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note (optional)" />
        <button className="btn small primary" disabled={add.isPending}>
          Add limit
        </button>
      </form>
    </section>
  );
}
