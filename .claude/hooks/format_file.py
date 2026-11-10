import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or payload.get("tool_response", {}).get("filePath")
    if not file_path or not file_path.endswith(".py") or not Path(file_path).exists():
        return 0

    subprocess.run([sys.executable, "-m", "ruff", "format", "--quiet", file_path], check=False)  # noqa: S603
    lint = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", file_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if lint.returncode != 0:
        sys.stderr.write(f"ruff encontró errores en {file_path}:\n{lint.stdout}{lint.stderr}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
