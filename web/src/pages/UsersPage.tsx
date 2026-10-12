import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate, Role, ROLE_LABEL, UserItem } from "../api";
import { fetchMe, useUsers } from "../role";

const MIN_PASSWORD = 12;

type Draft = { username: string; password: string; role: Role };
const EMPTY: Draft = { username: "", password: "", role: "guest" };

function UserForm({
  initial,
  editing,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: Draft;
  editing: boolean;
  busy: boolean;
  onSubmit: (d: Draft) => void;
  onCancel?: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(d);
  };
  return (
    <form className="row gap wrap small" onSubmit={submit}>
      <label className="inline">
        Username
        <input value={d.username} onChange={(e) => setD({ ...d, username: e.target.value })} required minLength={3} maxLength={64} />
      </label>
      <label className="inline">
        {editing ? "New password" : "Password"}
        <input
          type="password"
          value={d.password}
          onChange={(e) => setD({ ...d, password: e.target.value })}
          autoComplete="new-password"
          required={!editing}
          minLength={MIN_PASSWORD}
          placeholder={editing ? "leave empty to keep" : `min. ${MIN_PASSWORD} characters`}
        />
      </label>
      <label className="inline">
        Role
        <select value={d.role} onChange={(e) => setD({ ...d, role: e.target.value as Role })}>
          {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
      <button className="btn primary small" disabled={busy}>
        {editing ? "Save" : "Add user"}
      </button>
      {onCancel && (
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      )}
    </form>
  );
}

export default function UsersPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const users = useUsers(true);
  const [editId, setEditId] = useState<number | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  const done = () => {
    setErr(null);
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["wells"] });
  };
  const onError = (e: unknown) => setErr((e as Error).message);

  const create = useMutation({
    mutationFn: (d: Draft) => api.post<UserItem>("/api/users", d),
    onSuccess: () => {
      done();
      setFormKey((k) => k + 1); // clear the form
    },
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, d }: { id: number; d: Draft }) =>
      api.patch<UserItem>(`/api/users/${id}`, { username: d.username, role: d.role, password: d.password || undefined }),
    onSuccess: () => {
      done();
      setEditId(null);
      qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError,
  });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/api/users/${id}`),
    onSuccess: done,
    onError,
  });

  return (
    <div className="page">
      <p className="muted small tabs-note">
        <b>Users</b> = accounts that can sign in. A <b>user</b> sees only the Monitoring and Dashboard menus, and only the
        monitoring wells they own (the wells they uploaded, or wells an admin assigned to them in Monitoring). An{" "}
        <b>admin</b> sees every menu and all monitoring wells.
      </p>

      <section className="card">
        <h2>Add a user</h2>
        <UserForm key={formKey} initial={EMPTY} editing={false} busy={create.isPending} onSubmit={(d) => create.mutate(d)} />
      </section>

      <section className="card">
        <h2>Users ({users.data?.length ?? 0})</h2>
        {err && <div className="alert error">{err}</div>}
        {users.isError && <div className="alert error">{(users.error as Error).message}</div>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th className="num">Monitoring wells</th>
                <th>Created</th>
                <th>Last changed</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(users.data ?? []).map((u) =>
                editId === u.id ? (
                  <tr key={u.id}>
                    <td colSpan={6}>
                      <UserForm
                        initial={{ username: u.username, password: "", role: u.role }}
                        editing
                        busy={update.isPending}
                        onSubmit={(d) => update.mutate({ id: u.id, d })}
                        onCancel={() => setEditId(null)}
                      />
                    </td>
                  </tr>
                ) : (
                  <tr key={u.id}>
                    <td>
                      <b>{u.username}</b>
                      {u.username === me.data?.username && <span className="muted small"> (you)</span>}
                    </td>
                    <td>
                      <span className={`badge ${u.role === "admin" ? "ok" : ""}`}>{ROLE_LABEL[u.role] ?? u.role}</span>
                    </td>
                    <td className="num">{u.monitoring_wells}</td>
                    <td className="small">{u.created_at ? fmtDate(u.created_at) : "–"}</td>
                    <td className="small">{fmtDate(u.updated_at)}</td>
                    <td className="nowrap">
                      <button className="btn small" onClick={() => setEditId(u.id)}>
                        Edit
                      </button>{" "}
                      {u.username !== me.data?.username && (
                        <button
                          className="btn small ghost"
                          disabled={del.isPending}
                          onClick={() =>
                            confirm(
                              `Delete user ${u.username}? They can no longer sign in. Their ${u.monitoring_wells} monitoring well(s) stay and become visible to admins only.`,
                            ) && del.mutate(u.id)
                          }
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
