from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

from autoscholar.exceptions import ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ValidationError(f"YAML file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValidationError(f"YAML root must be a mapping: {path}")
    return raw


def write_yaml(path: Path, payload: dict) -> None:
    ensure_parent(path)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict:
    if not path.exists():
        raise ValidationError(f"JSON file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError(f"JSON root must be an object: {path}")
    return raw


def read_json_model(path: Path, model: type[ModelT]) -> ModelT:
    adapter = TypeAdapter(model)
    try:
        return adapter.validate_python(read_json(path))
    except Exception as exc:
        raise ValidationError(f"Invalid JSON model in {path}: {exc}") from exc


def read_json_list(path: Path, key: str, model: type[ModelT]) -> list[ModelT]:
    raw = read_json(path)
    value = raw.get(key, [])
    adapter = TypeAdapter(list[model])  # type: ignore[index]
    try:
        return adapter.validate_python(value)
    except Exception as exc:
        raise ValidationError(f"Invalid JSON list '{key}' in {path}: {exc}") from exc


def write_json(path: Path, payload: dict) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    if not path.exists():
        raise ValidationError(f"JSONL file not found: {path}")
    adapter = TypeAdapter(model)
    records: list[ModelT] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            records.append(adapter.validate_python(payload))
        except Exception as exc:
            raise ValidationError(f"Invalid JSONL record at {path}:{line_number}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: Iterable[BaseModel | dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: BaseModel | dict) -> None:
    ensure_parent(path)
    payload = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def touch_jsonl(path: Path) -> None:
    ensure_parent(path)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    if not path.exists():
        raise ValidationError(f"Text file not found: {path}")
    return path.read_text(encoding="utf-8")


def dump_records(records: Sequence[BaseModel]) -> list[dict]:
    return [record.model_dump(mode="json") for record in records]
