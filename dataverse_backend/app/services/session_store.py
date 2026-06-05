"""Local filesystem session store for AI Data Scientist MVP."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

# Storage directory relative to current working directory
SESSION_STORAGE_DIR = Path("session_storage")

# In-memory fallback caches
_in_memory_dfs: dict[str, pd.DataFrame] = {}
_in_memory_dataset_dfs: dict[str, pd.DataFrame] = {}
_in_memory_semantic_maps: dict[str, dict[str, Any]] = {}
_in_memory_dataset_semantic_maps: dict[str, dict[str, Any]] = {}
_in_memory_metadata: dict[str, dict[str, Any]] = {}
_in_memory_dataset_metadata: dict[str, dict[str, Any]] = {}


def create_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def persist_dataframe_for_session(session_id: str, df: pd.DataFrame, filename: str | None = None) -> Path:
    """Save the dataframe and metadata locally in the session directory."""
    session_dir = SESSION_STORAGE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save dataframe as pickle for deterministic round-trips
    dataset_path = session_dir / "dataset.pkl"
    df.to_pickle(dataset_path)

    metadata = {
        "session_id": session_id,
        "filename": filename or "uploaded_dataset.csv",
        "dataset_path": str(dataset_path),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(col) for col in df.columns],
    }

    metadata_path = session_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Update in-memory caches
    _in_memory_dfs[session_id] = df.copy()
    _in_memory_metadata[session_id] = metadata

    return dataset_path


def persist_dataframe_for_dataset(session_id: str, dataset_id: str, df: pd.DataFrame, filename: str | None = None) -> Path:
    """Save a dataframe under a stable dataset_id inside the session."""
    dataset_dir = SESSION_STORAGE_DIR / session_id / "datasets" / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "dataset.pkl"
    df.to_pickle(dataset_path)

    metadata = {
        "session_id": session_id,
        "dataset_id": dataset_id,
        "filename": filename or "uploaded_dataset.csv",
        "dataset_path": str(dataset_path),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(col) for col in df.columns],
    }
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    _in_memory_dataset_dfs[dataset_id] = df.copy()
    _in_memory_dataset_metadata[dataset_id] = metadata
    return dataset_path


def persist_semantic_map_for_session(session_id: str, semantic_map: dict[str, Any]) -> Path:
    """Save the semantic map to the local session directory."""
    session_dir = SESSION_STORAGE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    path = session_dir / "semantic_map.json"
    path.write_text(json.dumps(semantic_map, indent=2, default=str), encoding="utf-8")

    # Update in-memory cache
    _in_memory_semantic_maps[session_id] = semantic_map

    return path


def persist_semantic_map_for_dataset(session_id: str, dataset_id: str, semantic_map: dict[str, Any]) -> Path:
    """Save a semantic map for a specific dataset."""
    dataset_dir = SESSION_STORAGE_DIR / session_id / "datasets" / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)

    path = dataset_dir / "semantic_map.json"
    path.write_text(json.dumps(semantic_map, indent=2, default=str), encoding="utf-8")
    _in_memory_dataset_semantic_maps[dataset_id] = semantic_map
    return path


def load_semantic_map_for_session(session_id: str) -> dict[str, Any] | None:
    """Load the semantic map for a session."""
    # Check in-memory first
    if session_id in _in_memory_semantic_maps:
        return _in_memory_semantic_maps[session_id]

    # Fallback to disk
    session_dir = SESSION_STORAGE_DIR / session_id
    path = session_dir / "semantic_map.json"
    if path.exists():
        try:
            semantic_map = json.loads(path.read_text(encoding="utf-8"))
            _in_memory_semantic_maps[session_id] = semantic_map
            return semantic_map
        except Exception:
            pass
    return None


def load_semantic_map_for_dataset(session_id: str, dataset_id: str) -> dict[str, Any] | None:
    """Load a semantic map for a specific dataset."""
    if dataset_id in _in_memory_dataset_semantic_maps:
        return _in_memory_dataset_semantic_maps[dataset_id]

    path = SESSION_STORAGE_DIR / session_id / "datasets" / dataset_id / "semantic_map.json"
    if path.exists():
        try:
            semantic_map = json.loads(path.read_text(encoding="utf-8"))
            _in_memory_dataset_semantic_maps[dataset_id] = semantic_map
            return semantic_map
        except Exception:
            pass
    return None


def load_dataframe_for_session(session_id: str) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Load the dataframe and its metadata for a session."""
    metadata = _in_memory_metadata.get(session_id, {})
    df = _in_memory_dfs.get(session_id)

    if df is not None:
        return df.copy(), metadata

    session_dir = SESSION_STORAGE_DIR / session_id
    meta_path = session_dir / "metadata.json"
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            _in_memory_metadata[session_id] = metadata
        except Exception:
            pass

    # Read from pickle if available
    pkl_path = session_dir / "dataset.pkl"
    if pkl_path.exists():
        try:
            df = pd.read_pickle(pkl_path)
            _in_memory_dfs[session_id] = df.copy()
            return df, metadata
        except Exception:
            pass

    # Fallback to searching csv/excel in the session directory if pickle fails
    for file in session_dir.glob("*"):
        if file.suffix.lower() == ".csv":
            try:
                df = pd.read_csv(file)
                _in_memory_dfs[session_id] = df.copy()
                return df, metadata
            except Exception:
                pass
        elif file.suffix.lower() in {".xlsx", ".xls"}:
            try:
                df = pd.read_excel(file)
                _in_memory_dfs[session_id] = df.copy()
                return df, metadata
            except Exception:
                pass

    return None, metadata


def load_dataframe_for_dataset(session_id: str, dataset_id: str) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Load a dataframe by dataset_id without relying on mutable session-level state."""
    metadata = _in_memory_dataset_metadata.get(dataset_id, {})
    df = _in_memory_dataset_dfs.get(dataset_id)

    if df is not None:
        return df.copy(), metadata

    dataset_dir = SESSION_STORAGE_DIR / session_id / "datasets" / dataset_id
    meta_path = dataset_dir / "metadata.json"
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            _in_memory_dataset_metadata[dataset_id] = metadata
        except Exception:
            pass

    pkl_path = dataset_dir / "dataset.pkl"
    if pkl_path.exists():
        try:
            df = pd.read_pickle(pkl_path)
            _in_memory_dataset_dfs[dataset_id] = df.copy()
            return df, metadata
        except Exception:
            pass

    return None, metadata


def delete_session(session_id: str) -> bool:
    """Delete a session's directory and clear its caches."""
    # Clear caches
    _in_memory_dfs.pop(session_id, None)
    _in_memory_metadata.pop(session_id, None)
    _in_memory_semantic_maps.pop(session_id, None)
    session_dataset_dir = SESSION_STORAGE_DIR / session_id / "datasets"
    if session_dataset_dir.exists():
        for dataset_dir in session_dataset_dir.iterdir():
            if dataset_dir.is_dir():
                _in_memory_dataset_dfs.pop(dataset_dir.name, None)
                _in_memory_dataset_metadata.pop(dataset_dir.name, None)
                _in_memory_dataset_semantic_maps.pop(dataset_dir.name, None)

    # Delete files
    session_dir = SESSION_STORAGE_DIR / session_id
    if not session_dir.exists():
        return False
    shutil.rmtree(session_dir, ignore_errors=True)
    return True
