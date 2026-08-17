from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gestor_escuela.import_config import load_configuration


def test_load_configuration_accepts_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "school.json"
    path.write_text(
        json.dumps(
            {
                "groups": [{"id": "G1", "label": "1º A"}],
                "time_slots": [{"id": "S1", "label": "09:00", "order": 1}],
                "teachers": [
                    {
                        "id": "P01",
                        "profile": "TUTOR",
                        "can_cover_groups": ["G1"],
                    }
                ],
                "activities": [
                    {
                        "id": "A-S1-G1",
                        "slot_id": "S1",
                        "activity_type": "CLASS",
                        "teacher_id": "P01",
                        "group_id": "G1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    configuration = load_configuration(path)

    assert configuration.groups[0].id == "G1"
    assert configuration.teachers[0].can_cover_groups == {"G1"}


def test_load_configuration_rejects_invalid_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"groups": []}', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_configuration(path)
