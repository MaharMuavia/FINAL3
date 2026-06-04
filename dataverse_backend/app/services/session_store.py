"""Local session storage for deterministic analysis endpoints."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from ..state.persistent_session_state import session_manager
from ..state.session_state import SessionState


def create_session_id() -> str:
    return str(uuid.uuid4())


def persist_dataframe_for_session(session_id: str, df: pd.DataFrame, filename: str | None = None) -> Path:
    persistent = session_manager.get_session(session_id)
    persistent.session_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = persistent.dataset_path
    persistent._write_dataframe(df, dataset_path)
    metadata = {
        "session_id": session_id,
        "filename": filename or "uploaded_dataset",
        "dataset_path": str(dataset_path),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(col) for col in df.columns],
    }
    (persistent.session_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    persistent.set("raw_dataframe", df.copy())
    persistent.set("dataset_filename", metadata["filename"])
    persistent.set("dataset_path", str(dataset_path))

    simple = SessionState.get(session_id)
    simple.set("raw_dataframe", df.copy())
    simple.set("dataset_filename", metadata["filename"])
    simple.set("dataset_path", str(dataset_path))
    return dataset_path


def persist_semantic_map_for_session(session_id: str, semantic_map: dict[str, Any]) -> Path:
    persistent = session_manager.get_session(session_id)
    persistent.session_dir.mkdir(parents=True, exist_ok=True)
    path = persistent.session_dir / "semantic_map.json"
    path.write_text(json.dumps(semantic_map, indent=2, default=str), encoding="utf-8")
    persistent.set("semantic_map", semantic_map)
    SessionState.get(session_id).set("semantic_map", semantic_map)
    return path


def load_semantic_map_for_session(session_id: str) -> dict[str, Any] | None:
    persistent = session_manager.get_session(session_id)
    value = persistent.get_value("semantic_map")
    if isinstance(value, dict):
        return value
    simple_value = SessionState.get(session_id).get_value("semantic_map")
    if isinstance(simple_value, dict):
        return simple_value
    path = persistent.session_dir / "semantic_map.json"
    if path.exists():
        semantic_map = json.loads(path.read_text(encoding="utf-8"))
        persistent.set("semantic_map", semantic_map)
        SessionState.get(session_id).set("semantic_map", semantic_map)
        return semantic_map
    return None


def load_dataframe_for_session(session_id: str) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    persistent = session_manager.get_session(session_id)
    metadata: dict[str, Any] = {}
    meta_path = persistent.session_dir / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    df = persistent.get_value("raw_dataframe")
    if df is not None:
        return df.copy(), metadata
    simple = SessionState.get(session_id)
    df = simple.get_value("raw_dataframe")
    if df is not None:
        return df.copy(), metadata
    for candidate in (persistent.session_dir / "dataset.parquet", persistent.session_dir / "dataset.pkl"):
        if candidate.exists():
            loaded = pd.read_pickle(candidate) if candidate.suffix == ".pkl" else persistent._read_dataframe(candidate)
            persistent.set("raw_dataframe", loaded.copy())
            simple.set("raw_dataframe", loaded.copy())
            return loaded, metadata
    return None, metadata


def delete_session(session_id: str) -> bool:
    persistent = session_manager.get_session(session_id)
    if not persistent.session_dir.exists():
        return False
    shutil.rmtree(persistent.session_dir)
    return True
