"""CLI admin.

docker compose exec app python -m app.cli set-admin-password
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
            username = username or input("Username admin baru: ").strip()
            if not username:
                print("Username kosong.", file=sys.stderr)
                return 1
            user = AdminUser(username=username, password_hash="")
            db.add(user)
        elif username and username != user.username:
            user.username = username  # tetap satu akun: ganti nama, bukan menambah
        pw = getpass.getpass(f"Password baru untuk '{user.username}' (kosong = buat acak): ")
        if not pw:
            pw = secrets.token_urlsafe(18)
            print(f"Password acak: {pw}\nSimpan di pengelola password sekarang.")
        else:
            if len(pw) < MIN_LEN:
                print(f"Password minimal {MIN_LEN} karakter.", file=sys.stderr)
                return 1
            if getpass.getpass("Ulangi password: ") != pw:
                print("Password tidak sama.", file=sys.stderr)
                return 1
        user.password_hash = hash_password(pw)
        user.updated_at = utcnow()
        # buka kunci login setelah password diganti
        db.execute(delete(LoginAttempt).where(LoginAttempt.username == user.username))
        db.commit()
        print(f"Password admin '{user.username}' diperbarui.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("set-admin-password", help="Ganti (atau buat) password satu akun admin")
    p.add_argument("--username", help="Ganti username sekaligus (opsional)")
    args = ap.parse_args()
    if args.cmd == "set-admin-password":
        return set_admin_password(args.username)
    return 1


if __name__ == "__main__":
    sys.exit(main())
