from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from gestor_escuela.api.schemas import SchoolConfigurationPut


def load_configuration(path: Path) -> SchoolConfigurationPut:
    with path.open(encoding="utf-8") as source:
        raw = json.load(source)
    return SchoolConfigurationPut.model_validate(raw)


def import_configuration(
    *,
    api_url: str,
    school_id: UUID,
    configuration: SchoolConfigurationPut,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    endpoint = f"{api_url.rstrip('/')}/schools/{school_id}/configuration"
    auth_headers = (
        {"X-Actor-Id": str(actor_id)}
        if actor_id is not None
        else {"X-Actor-Role": "ADMIN"}
    )
    request = Request(
        endpoint,
        data=configuration.model_dump_json().encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **auth_headers,
        },
        method="PUT",
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Configuration import failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GestorEscuela API: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Configuration import returned an unexpected response")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import school configuration from JSON")
    parser.add_argument("--school-id", required=True, type=UUID)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--actor-id",
        type=UUID,
        help="User UUID with ADMIN membership; required after school bootstrap",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configuration = load_configuration(args.file)
    result = import_configuration(
        api_url=args.api_url,
        school_id=args.school_id,
        configuration=configuration,
        actor_id=args.actor_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
