"""Server-side Supabase REST and Storage client with local fallback support."""
from __future__ import annotations

import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..core.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseClient:
    """Tiny service-role Supabase client.

    This intentionally lives only in the backend. The service role key must never
    be exposed to the frontend.
    """

    def __init__(self) -> None:
        self.url = (settings.SUPABASE_URL or "").rstrip("/")
        self.service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY

    @property
    def configured(self) -> bool:
        return bool(self.url and self.service_role_key)

    def _headers(self, *, prefer: str | None = None, content_type: str = "application/json") -> dict[str, str]:
        headers = {
            "apikey": self.service_role_key or "",
            "Authorization": f"Bearer {self.service_role_key or ''}",
            "Content-Type": content_type,
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"{self.url}/rest/v1/{table}",
            json=payload,
            headers=self._headers(prefer="return=representation"),
        )
        data = response.json()
        return data[0] if isinstance(data, list) and data else data

    async def select(self, table: str, query: str = "select=*") -> list[dict[str, Any]]:
        response = await self._request("GET", f"{self.url}/rest/v1/{table}?{query}", headers=self._headers())
        data = response.json()
        return data if isinstance(data, list) else []

    async def update(self, table: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = await self._request(
            "PATCH",
            f"{self.url}/rest/v1/{table}?id=eq.{quote(row_id)}",
            json=payload,
            headers=self._headers(prefer="return=representation"),
        )
        data = response.json()
        return data[0] if isinstance(data, list) and data else None

    async def delete(self, table: str, row_id: str) -> None:
        await self._request("DELETE", f"{self.url}/rest/v1/{table}?id=eq.{quote(row_id)}", headers=self._headers())

    async def upload_bytes(self, bucket: str, storage_path: str, content: bytes, content_type: str | None = None) -> str:
        content_type = content_type or mimetypes.guess_type(storage_path)[0] or "application/octet-stream"
        encoded = "/".join(quote(part, safe="") for part in storage_path.split("/"))
        await self._request(
            "POST",
            f"{self.url}/storage/v1/object/{bucket}/{encoded}",
            content=content,
            headers={
                "apikey": self.service_role_key or "",
                "Authorization": f"Bearer {self.service_role_key or ''}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        return storage_path

    async def signed_url(self, bucket: str, storage_path: str, expires_in: int = 3600) -> str | None:
        encoded = "/".join(quote(part, safe="") for part in storage_path.split("/"))
        response = await self._request(
            "POST",
            f"{self.url}/storage/v1/object/sign/{bucket}/{encoded}",
            json={"expiresIn": expires_in},
            headers=self._headers(),
        )
        payload = response.json()
        signed = payload.get("signedURL") or payload.get("signedUrl")
        if not signed:
            return None
        return signed if str(signed).startswith("http") else f"{self.url}/storage/v1{signed}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        return response


class LocalPersistence:
    """JSON/file fallback used when Supabase is not configured."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("session_storage") / "dataverse_chat"
        self.datasets_dir = self.root / "datasets"
        self.reports_dir = self.root / "reports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def table_path(self, table: str) -> Path:
        return self.root / f"{table}.json"

    def read_table(self, table: str) -> list[dict[str, Any]]:
        path = self.table_path(table)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def write_table(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.table_path(table).write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self.read_table(table)
        rows.append(payload)
        self.write_table(table, rows)
        return payload

    def update(self, table: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = self.read_table(table)
        updated: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("id")) == str(row_id):
                row.update(payload)
                updated = row
                break
        self.write_table(table, rows)
        return updated

    def delete(self, table: str, row_id: str) -> None:
        self.write_table(table, [row for row in self.read_table(table) if str(row.get("id")) != str(row_id)])

    def copy_into(self, source: Path, storage_path: str) -> str:
        target = self.root / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return str(target)

    def write_bytes(self, storage_path: str, content: bytes) -> str:
        target = self.root / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)


supabase_client = SupabaseClient()
local_persistence = LocalPersistence()
