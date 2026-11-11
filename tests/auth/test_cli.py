from collections.abc import Iterator

import pytest

from src.auth import cli
from src.auth.schemas import OwnerCreate


def _answers(*values: str) -> Iterator[str]:
    return iter(values)


class TestCreateOwnerCommand:
    def test_rejects_phone_that_is_not_ten_digits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = _answers("clave-del-dueno", "clave-del-dueno")
        monkeypatch.setattr("src.auth.cli.getpass.getpass", lambda _: next(answers))

        with pytest.raises(SystemExit, match="Datos inválidos"):
            cli.main(["create-owner", "--email", "d@example.com", "--name", "D", "--phone", "55"])

    def test_rejects_mismatched_password_confirmation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = _answers("clave-del-dueno", "otra-clave")
        monkeypatch.setattr("src.auth.cli.getpass.getpass", lambda _: next(answers))

        with pytest.raises(SystemExit, match="no coinciden"):
            cli.main(
                ["create-owner", "--email", "d@example.com", "--name", "D", "--phone", "5512345678"]
            )

    def test_passes_validated_data_to_creation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = _answers("clave-del-dueno", "clave-del-dueno")
        monkeypatch.setattr("src.auth.cli.getpass.getpass", lambda _: next(answers))
        received: list[OwnerCreate] = []

        async def fake_create_owner(data: OwnerCreate) -> None:
            received.append(data)

        monkeypatch.setattr(cli, "_create_owner", fake_create_owner)

        cli.main(
            [
                "create-owner",
                "--email",
                "Dueno@Example.com",
                "--name",
                "Dueño",
                "--phone",
                "5599998888",
            ]
        )

        assert received[0].email == "Dueno@example.com"
        assert received[0].phone == "5599998888"

    def test_password_is_never_a_cli_argument(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["create-owner", "--email", "d@example.com", "--password", "x"])
