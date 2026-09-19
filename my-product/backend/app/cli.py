from __future__ import annotations

import argparse
import getpass
import json

from sqlalchemy import text

from .database import engine
from .security import hash_password


ROLES = ("admin", "engineer", "sales", "manager", "customer")


def create_user(args: argparse.Namespace) -> None:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters")
    with engine.begin() as connection:
        result = connection.execute(text("""
            INSERT INTO sys_user (username, password_hash, real_name, role, status)
            VALUES (:username, :password_hash, :real_name, :role, 'active')
        """), {
            "username": args.username,
            "password_hash": hash_password(password),
            "real_name": args.real_name,
            "role": args.role,
        })
        user_id = int(result.lastrowid)
    print(f"Created user id={user_id} username={args.username} role={args.role}")


def check_database(_: argparse.Namespace) -> None:
    with engine.connect() as connection:
        version = connection.execute(text("SELECT VERSION()" )).scalar_one()
        table_count = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema=DATABASE() AND table_type='BASE TABLE'
        """)).scalar_one()
    print(f"database=ok version={version} tables={table_count}")


def import_pollutant_library(args: argparse.Namespace) -> None:
    from .importers import import_pollutants

    result = import_pollutants(args.file, args.username)
    print(json.dumps(result, ensure_ascii=False))


def restore_demo_baseline(args: argparse.Namespace) -> None:
    from .baseline import restore_baseline

    result = restore_baseline(args.username)
    print(json.dumps(result, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AMC backend administration")
    commands = parser.add_subparsers(required=True)
    user = commands.add_parser("create-user", help="Create a user with an Argon2 password hash")
    user.add_argument("--username", required=True)
    user.add_argument("--real-name", required=True)
    user.add_argument("--role", choices=ROLES, default="admin")
    user.set_defaults(handler=create_user)
    database = commands.add_parser("check-db", help="Verify the configured database connection")
    database.set_defaults(handler=check_database)
    pollutant_import = commands.add_parser(
        "import-pollutants", help="Validate and import the AMC pollutant Excel library"
    )
    pollutant_import.add_argument("--file", required=True)
    pollutant_import.add_argument("--username", default="admin")
    pollutant_import.set_defaults(handler=import_pollutant_library)
    baseline = commands.add_parser(
        "restore-baseline", help="Restore the original web1 customer/project/cleanroom/scheme baseline"
    )
    baseline.add_argument("--username", default="admin")
    baseline.set_defaults(handler=restore_demo_baseline)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
