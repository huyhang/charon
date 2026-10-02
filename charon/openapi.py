"""Export the OpenAPI spec without starting the service.

python -m charon.openapi docs/openapi.json
"""

import json
import sys
from pathlib import Path

from charon.api.app import create_api


def render() -> str:
    return json.dumps(create_api().openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> None:
    if len(argv) != 1:
        raise SystemExit("usage: python -m charon.openapi <output.json>")
    output = Path(argv[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render())


if __name__ == "__main__":
    main(sys.argv[1:])
