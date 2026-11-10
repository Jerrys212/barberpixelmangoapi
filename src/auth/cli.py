import argparse
import asyncio
import getpass
import sys

from pydantic import TypeAdapter, ValidationError

from src.auth import service as auth_service
from src.auth.schemas import OwnerCreate, Password
from src.database import session_factory, transaction_scope
from src.exceptions import AppError
from src.registry import load_models


def _prompt_password() -> str:
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Confirma la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    return password


async def _create_owner(data: OwnerCreate) -> None:
    async with session_factory() as session, transaction_scope(session) as scoped:
        owner = await auth_service.create_owner(scoped, data)
        sys.stdout.write(f"OWNER creado: {owner.email}\n")


async def _reset_owner_password(password: str) -> None:
    async with session_factory() as session, transaction_scope(session) as scoped:
        owner = await auth_service.reset_owner_password(scoped, password)
        sys.stdout.write(f"Contraseña actualizada y sesiones revocadas: {owner.email}\n")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m src.auth.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-owner", help="Crea la cuenta OWNER")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--phone", required=True, help="Formato E.164, p. ej. +525512345678")

    commands.add_parser("reset-owner-password", help="Cambia la contraseña del OWNER")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    load_models()
    try:
        if args.command == "create-owner":
            data = OwnerCreate(
                email=args.email,
                full_name=args.name,
                phone=args.phone,
                password=_prompt_password(),
            )
            asyncio.run(_create_owner(data))
        else:
            password = TypeAdapter(Password).validate_python(_prompt_password())
            asyncio.run(_reset_owner_password(password))
    except ValidationError as exc:
        raise SystemExit(f"Datos inválidos:\n{exc}") from exc
    except AppError as exc:
        raise SystemExit(exc.detail) from exc


if __name__ == "__main__":
    main()
