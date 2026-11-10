import json
import subprocess
import sys

CHECKS: list[tuple[str, list[str]]] = [
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format", ["ruff", "format", "--check", "."]),
    ("mypy", ["mypy", "src"]),
    ("pytest", ["pytest", "-x", "-q"]),
]


def main() -> int:
    payload = json.load(sys.stdin)
    # Evita un bucle infinito: si ya bloqueamos una vez en este turno, dejamos terminar.
    if payload.get("stop_hook_active"):
        return 0

    failures: list[str] = []
    for name, args in CHECKS:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            failures.append(f"### {name}\n{result.stdout[-4000:]}{result.stderr[-2000:]}")

    if failures:
        sys.stderr.write("Fallaron los checks de calidad:\n\n" + "\n\n".join(failures))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
