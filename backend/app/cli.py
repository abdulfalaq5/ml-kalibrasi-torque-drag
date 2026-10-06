"""CLI admin.

docker compose exec app python -m app.cli set-admin-password
docker compose exec app python -m app.cli refresh-meta   # baca ulang Calibrate DD, BHA, wellbore dari file
docker compose exec app python -m app.cli recompute-quality
"""

import argparse
import getpass
import secrets
import sys

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.db.models import AdminUser, LoginAttempt, utcnow
from app.db.session import SessionLocal

MIN_LEN = 12


def set_admin_password(username: str | None) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(AdminUser).limit(1))
        if user is None:
            username = username or input("New admin username: ").strip()
            if not username:
                print("Username is empty.", file=sys.stderr)
                return 1
            user = AdminUser(username=username, password_hash="")
            db.add(user)
        elif username and username != user.username:
            user.username = username  # tetap satu akun: ganti nama, bukan menambah
        pw = getpass.getpass(f"New password for '{user.username}' (empty = generate random): ")
        if not pw:
            pw = secrets.token_urlsafe(18)
            print(f"Random password: {pw}\nStore it in a password manager now.")
        else:
            if len(pw) < MIN_LEN:
                print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
                return 1
            if getpass.getpass("Repeat password: ") != pw:
                print("Passwords do not match.", file=sys.stderr)
                return 1
        user.password_hash = hash_password(pw)
        user.updated_at = utcnow()
        # buka kunci login setelah password diganti
        db.execute(delete(LoginAttempt).where(LoginAttempt.username == user.username))
        db.commit()
        print(f"Password for admin '{user.username}' updated.")
    return 0


def refresh_meta() -> int:
    """Baca ulang meta dari file yang sudah diimpor (Calibrate DD, BHA, wellbore, FF casing)."""
    from pathlib import Path

    from app.db.models import UploadedFile, Well
    from app.parsers.workbook import parse_workbook
    from app.services.importer import OK_STATUSES

    keys = ("calibration_drag_klbf", "calibration_torque_ftlbf", "bha", "wellbore", "csg_ff")
    n = changed = 0
    with SessionLocal() as db:
        for w in db.scalars(select(Well)):
            files = sorted(
                (f for f in w.files if f.status in OK_STATUSES),
                key=lambda f: f.version or 0,
            )
            if not files or not Path(files[-1].path).exists():
                continue
            f: UploadedFile = files[-1]
            pw = parse_workbook(Path(f.path), f.filename, f.rel_path)
            meta = dict(w.meta or {})
            new = {k: pw.meta[k] for k in keys if k in pw.meta}
            n += 1
            if any(meta.get(k) != v for k, v in new.items()):
                meta.update(new)
                w.meta = meta
                changed += 1
        db.commit()
    print(f"Wells checked: {n}, metadata updated: {changed}")
    return 0


def backfill_band(model_id: int | None) -> int:
    from app.db.models import MLModel
    from app.services.training import active_model, backfill_band_coverage

    with SessionLocal() as db:
        m = db.get(MLModel, model_id) if model_id else active_model(db)
        if m is None or not m.path:
            print("Model not found", file=sys.stderr)
            return 1
        for op, v in backfill_band_coverage(db, m).items():
            print(
                f"model #{m.id} {op}: inside P10–P90 "
                + ", ".join(f"{k} {x:.0%}" for k, x in v.items())
            )
    return 0


def recompute_quality() -> int:
    from app.services.quality import recompute_all

    with SessionLocal() as db:
        print(recompute_all(db))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "set-admin-password", help="Change (or create) the password of the single admin account"
    )
    p.add_argument("--username", help="Also change the username (optional)")
    for name in ("refresh-meta", "refresh-calibration"):  # nama lama tetap diterima
        sub.add_parser(
            name, help="Re-read DD Calibrate offsets, BHA and wellbore of imported files"
        )
    sub.add_parser("recompute-quality", help="Recompute the data quality of every well")
    pb = sub.add_parser("backfill-band", help="Add the P10–P90 band coverage to an existing model")
    pb.add_argument("--model-id", type=int, help="Default: the active model")
    args = ap.parse_args()
    if args.cmd == "set-admin-password":
        return set_admin_password(args.username)
    if args.cmd in ("refresh-meta", "refresh-calibration"):
        return refresh_meta()
    if args.cmd == "backfill-band":
        return backfill_band(args.model_id)
    if args.cmd == "recompute-quality":
        return recompute_quality()
    return 1


if __name__ == "__main__":
    sys.exit(main())
