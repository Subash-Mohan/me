import argparse
import getpass
import sys
from collections.abc import Sequence

from app.db.session import SessionLocal
from app.services.owner import (
    EmptyPassphraseError,
    OwnerAlreadyExistsError,
    create_owner_user,
)


def _read_passphrase_interactively() -> str:
    p1 = getpass.getpass("Enter passphrase: ")
    p2 = getpass.getpass("Confirm passphrase: ")
    if p1 != p2:
        print("Passphrases do not match.", file=sys.stderr)
        raise SystemExit(2)
    return p1


def cmd_create_owner(args: argparse.Namespace) -> int:
    if args.passphrase is not None:
        passphrase = args.passphrase
    else:
        passphrase = _read_passphrase_interactively()
    with SessionLocal() as session:
        try:
            user = create_owner_user(session, passphrase)
        except EmptyPassphraseError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except OwnerAlreadyExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        session.commit()
        print(f"Owner created: {user.id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="me", description="Me admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    co = sub.add_parser("create-owner", help="Create the owner user")
    co.add_argument(
        "passphrase",
        nargs="?",
        default=None,
        help="Passphrase (omit to be prompted with no echo)",
    )
    co.set_defaults(func=cmd_create_owner)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
