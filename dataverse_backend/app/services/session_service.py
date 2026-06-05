"""Chat session, dataset, agent-run, and report orchestration."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from ..api.upload_parsing import parse_uploaded_dataframe
from ..core.config import settings
from .analysis_pipeline import AnalysisPipeline
from .data_quality import json_safe
from .report_generator import ReportGenerator
from .session_store import (
    load_dataframe_for_dataset,
    persist_dataframe_for_dataset,
    persist_dataframe_for_session,
    persist_semantic_map_for_dataset,
    persist_semantic_map_for_session,
)
from .supabase_client import local_persistence, supabase_client, utc_now_iso
from .title_generator import TitleGenerator


class SessionService:
    def __init__(self) -> None:
        self.supabase = supabase_client
        self.local = local_persistence

    async def create_session(self, title: str = "New Chat", user_id: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title or "New Chat",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
            "active_dataset_id": None,
            "metadata": {},
        }
        row = await self._insert("chat_sessions", payload)
        return {"session_id": row["id"], "id": row["id"], "title": row["title"], "created_at": row["created_at"]}

    async def list_sessions(self) -> list[dict[str, Any]]:
        if self.supabase.configured:
            rows = await self.supabase.select("chat_sessions", "select=*&order=updated_at.desc&limit=50")
        else:
            rows = sorted(self.local.read_table("chat_sessions"), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        messages = await self._all_rows("chat_messages")
        counts: dict[str, int] = {}
        for message in messages:
            counts[str(message.get("session_id"))] = counts.get(str(message.get("session_id")), 0) + 1
        return [
            {
                "id": row["id"],
                "title": row.get("title") or "New Chat",
                "active_dataset_id": row.get("active_dataset_id"),
                "updated_at": row.get("updated_at"),
                "message_count": counts.get(str(row["id"]), 0),
            }
            for row in rows
        ]

    async def get_session(self, session_id: str) -> dict[str, Any]:
        session = await self._get_by_id("chat_sessions", session_id)
        if not session:
            raise KeyError("Session not found")
        messages = [row for row in await self._all_rows("chat_messages") if row.get("session_id") == session_id]
        datasets = [row for row in await self._all_rows("datasets") if row.get("session_id") == session_id]
        agent_runs = [row for row in await self._all_rows("agent_runs") if row.get("session_id") == session_id]
        reports = [row for row in await self._all_rows("reports") if row.get("session_id") == session_id]
        return {
            **session,
            "messages": sorted(messages, key=lambda row: row.get("created_at") or ""),
            "datasets": sorted(datasets, key=lambda row: row.get("created_at") or "", reverse=True),
            "agent_runs": sorted(agent_runs, key=lambda row: row.get("started_at") or ""),
            "reports": sorted(reports, key=lambda row: row.get("created_at") or "", reverse=True),
        }

    async def update_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload["updated_at"] = utc_now_iso()
        return await self._update("chat_sessions", session_id, payload)

    async def delete_session(self, session_id: str) -> None:
        await self._delete("chat_sessions", session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        message_type: str = "text",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "message_type": message_type,
            "payload": payload or {},
            "created_at": now,
        }
        message = await self._insert("chat_messages", row)
        await self.update_session(session_id, {"last_message_at": now})
        return message

    async def upload_dataset(self, session_id: str, filename: str, content: bytes) -> dict[str, Any]:
        if not await self._get_by_id("chat_sessions", session_id):
            raise KeyError("Session not found")
        df = parse_uploaded_dataframe(filename, content)
        dataset_id = str(uuid.uuid4())
        safe_name = Path(filename).name or "dataset.csv"
        file_type = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "csv"
        storage_path = f"{session_id}/{dataset_id}/{safe_name}"
        local_path = persist_dataframe_for_dataset(session_id, dataset_id, df, filename=safe_name)
        persist_dataframe_for_session(session_id, df, filename=safe_name)
        if self.supabase.configured:
            await self.supabase.upload_bytes(settings.SUPABASE_DATASET_BUCKET, storage_path, content)
            persisted_path = storage_path
        else:
            persisted_path = self.local.copy_into(local_path, f"datasets/{storage_path}")
        profile = AnalysisPipeline().profile_dataset(df)
        profile["preview"] = json_safe(df.head(25).to_dict(orient="records"))
        columns = [{"name": str(col), "dtype": str(df[col].dtype)} for col in df.columns]
        semantic_map = profile.get("semantic_map") if isinstance(profile.get("semantic_map"), dict) else {}
        now = utc_now_iso()
        dataset = {
            "id": dataset_id,
            "session_id": session_id,
            "user_id": None,
            "filename": safe_name,
            "original_filename": safe_name,
            "storage_path": persisted_path,
            "file_type": file_type,
            "file_size": len(content),
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "columns": columns,
            "schema_profile": json_safe(profile),
            "semantic_map": semantic_map,
            "status": "uploaded",
            "created_at": now,
            "updated_at": now,
        }
        await self._insert("datasets", dataset)
        await self.update_session(session_id, {"active_dataset_id": dataset_id})
        await self.add_message(
            session_id,
            "user",
            f"Uploaded dataset {safe_name}",
            payload={"dataset_id": dataset_id, "filename": safe_name, "row_count": len(df), "column_count": len(df.columns)},
        )
        return dataset

    async def list_datasets(self) -> list[dict[str, Any]]:
        if self.supabase.configured:
            rows = await self.supabase.select("datasets", "select=*&order=created_at.desc&limit=50")
        else:
            rows = sorted(self.local.read_table("datasets"), key=lambda item: item.get("created_at") or "", reverse=True)[:50]
        return rows

    async def list_session_datasets(self, session_id: str) -> list[dict[str, Any]]:
        return [row for row in await self._all_rows("datasets") if row.get("session_id") == session_id]

    async def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        return await self._get_by_id("datasets", dataset_id)

    async def delete_dataset(self, dataset_id: str) -> None:
        await self._delete("datasets", dataset_id)

    async def analyze(
        self,
        session_id: str,
        *,
        dataset_id: str | None = None,
        user_prompt: str = "Analyze this dataset",
        run_xai: bool = True,
        generate_report: bool = True,
    ) -> dict[str, Any]:
        session = await self._get_by_id("chat_sessions", session_id)
        if not session:
            raise KeyError("Session not found")
        dataset_id = dataset_id or session.get("active_dataset_id")
        if not dataset_id:
            raise ValueError("No dataset is attached to this session")
        dataset = await self.get_dataset(dataset_id)
        if not dataset:
            raise KeyError("Dataset not found")
        df, metadata = load_dataframe_for_dataset(session_id, dataset_id)
        if df is None:
            raise ValueError("Dataset file is not available locally for analysis")

        await self.add_message(session_id, "user", user_prompt, payload={"dataset_id": dataset_id})
        analysis_steps = self._analysis_steps()
        analysis_run = await self._start_agent(
            session_id,
            dataset_id,
            "AnalysisAgent",
            {"prompt": user_prompt},
            steps=analysis_steps,
        )
        facts = await AnalysisPipeline().run_full_analysis_async(
            df,
            query=user_prompt,
            run_xai=run_xai,
            session_id=session_id,
            filename=metadata.get("filename") or dataset.get("filename"),
            use_llm=True,
            provider="openai",
        )
        await self._complete_agent(analysis_run["id"], {
            "summary": facts.get("executive_summary"),
            "dataset_profile": facts.get("dataset_profile"),
            "business_metrics": facts.get("business_metrics"),
            "charts": facts.get("charts"),
            "warnings": facts.get("warnings"),
            "steps": analysis_steps,
        })

        xai_steps = self._xai_report_steps(facts.get("prediction"), run_xai=run_xai, generate_report=generate_report)
        xai_run = await self._start_agent(
            session_id,
            dataset_id,
            "XAIReportAgent",
            {"analysis_run_id": analysis_run["id"]},
            steps=xai_steps,
        )
        xai_output = facts.get("xai") if run_xai else {"status": "skipped", "plain_english_explanation": "XAI was skipped for this request."}
        await self._complete_agent(xai_run["id"], {
            "summary": xai_output.get("plain_english_explanation") if isinstance(xai_output, dict) else "XAI completed",
            "xai": xai_output,
            "recommendations": facts.get("recommendations"),
            "steps": xai_steps,
        })

        title = await TitleGenerator().generate(
            filename=dataset.get("filename"),
            query=user_prompt,
            dataset_type=(facts.get("semantic_map") or {}).get("dataset_type"),
            semantic_map=facts.get("semantic_map"),
        )
        await self.update_session(session_id, {"title": title, "active_dataset_id": dataset_id})
        if isinstance(facts.get("semantic_map"), dict):
            persist_semantic_map_for_dataset(session_id, dataset_id, facts["semantic_map"])
            persist_semantic_map_for_session(session_id, facts["semantic_map"])
            await self._update("datasets", dataset_id, {"semantic_map": facts["semantic_map"], "updated_at": utc_now_iso()})

        report_payload = None
        if generate_report:
            report_payload = await self.generate_report(session_id, dataset_id, title, facts, xai_output if isinstance(xai_output, dict) else {})

        answer = facts.get("executive_summary") or "Analysis complete."
        assistant_payload = {
            "agents": self._agent_summary(
                analysis_run,
                xai_run,
                analysis_steps=analysis_steps,
                xai_steps=xai_steps,
                facts=facts,
                xai_output=xai_output if isinstance(xai_output, dict) else {},
            ),
            "charts": normalize_charts(facts.get("charts") or []),
            "tables": build_tables(facts),
            "warnings": facts.get("warnings") or [],
            "recommendations": facts.get("recommendations") or [],
            "report": report_payload,
        }
        await self.add_message(session_id, "assistant", answer, payload=assistant_payload)
        return {
            "session_id": session_id,
            "dataset_id": dataset_id,
            "title": title,
            "agents": assistant_payload["agents"],
            "answer": answer,
            "tables": assistant_payload["tables"],
            "charts": assistant_payload["charts"],
            "warnings": assistant_payload["warnings"],
            "recommendations": assistant_payload["recommendations"],
            "report": report_payload,
        }

    async def chat_message(self, session_id: str, content: str, dataset_id: str | None = None) -> dict[str, Any]:
        return await self.analyze(session_id, dataset_id=dataset_id, user_prompt=content, run_xai=True, generate_report=True)

    async def generate_report(self, session_id: str, dataset_id: str, title: str, facts: dict[str, Any], xai_output: dict[str, Any]) -> dict[str, Any]:
        report_id = str(uuid.uuid4())
        generated = await ReportGenerator().generate(title=title, facts=facts, xai_output=xai_output)
        html_path = f"{session_id}/{report_id}/report.html"
        pdf_path = f"{session_id}/{report_id}/report.pdf"
        if self.supabase.configured:
            await self.supabase.upload_bytes(settings.SUPABASE_REPORT_BUCKET, html_path, str(generated["html"]).encode("utf-8"), "text/html")
            await self.supabase.upload_bytes(settings.SUPABASE_REPORT_BUCKET, pdf_path, generated["pdf"], "application/pdf")  # type: ignore[arg-type]
            html_url = await self.supabase.signed_url(settings.SUPABASE_REPORT_BUCKET, html_path)
            pdf_url = await self.supabase.signed_url(settings.SUPABASE_REPORT_BUCKET, pdf_path)
        else:
            self.local.write_bytes(f"reports/{html_path}", str(generated["html"]).encode("utf-8"))
            self.local.write_bytes(f"reports/{pdf_path}", generated["pdf"])  # type: ignore[arg-type]
            base = settings.BACKEND_BASE_URL.rstrip("/")
            html_url = f"{base}/api/reports/{report_id}/download?format=html"
            pdf_url = f"{base}/api/reports/{report_id}/download?format=pdf"
        now = utc_now_iso()
        report_row = {
            "id": report_id,
            "session_id": session_id,
            "dataset_id": dataset_id,
            "title": title,
            "report_type": "analysis",
            "format": "html,pdf",
            "storage_path": html_path,
            "public_url": html_url,
            "metadata": {"html_path": html_path, "pdf_path": pdf_path, "html_url": html_url, "pdf_url": pdf_url},
            "created_at": now,
        }
        await self._insert("reports", report_row)
        return {"report_id": report_id, "html_url": html_url, "pdf_url": pdf_url}

    async def list_reports(self, session_id: str) -> list[dict[str, Any]]:
        return [row for row in await self._all_rows("reports") if row.get("session_id") == session_id]

    async def get_report_download(self, report_id: str, fmt: str) -> tuple[str | None, Path | None]:
        report = await self._get_by_id("reports", report_id)
        if not report:
            return None, None
        metadata = report.get("metadata") or {}
        key = "pdf_path" if fmt == "pdf" else "html_path"
        if self.supabase.configured:
            url = await self.supabase.signed_url(settings.SUPABASE_REPORT_BUCKET, metadata.get(key) or report.get("storage_path"))
            return url, None
        path = self.local.root / "reports" / str(metadata.get(key, ""))
        return None, path if path.exists() else None

    async def _start_agent(
        self,
        session_id: str,
        dataset_id: str,
        agent_name: str,
        input_payload: dict[str, Any],
        *,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "dataset_id": dataset_id,
            "agent_name": agent_name,
            "status": "running",
            "input": input_payload,
            "output": {"steps": steps or []},
            "error": None,
            "started_at": utc_now_iso(),
            "completed_at": None,
        }
        await self.add_message(session_id, "agent", f"{agent_name} started", payload={"agent_name": agent_name, "status": "running"})
        return await self._insert("agent_runs", row)

    async def _complete_agent(self, run_id: str, output: dict[str, Any]) -> None:
        await self._update("agent_runs", run_id, {"status": "completed", "output": json_safe(output), "completed_at": utc_now_iso()})

    def _agent_summary(
        self,
        analysis_run: dict[str, Any],
        xai_run: dict[str, Any],
        *,
        analysis_steps: list[dict[str, Any]],
        xai_steps: list[dict[str, Any]],
        facts: dict[str, Any],
        xai_output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": "AnalysisAgent",
                "status": "completed",
                "summary": facts.get("executive_summary") or "Profiled dataset, mapped semantics, computed EDA, trends, metrics, and chart-ready facts.",
                "steps": analysis_steps,
            },
            {
                "name": "XAIReportAgent",
                "status": "completed",
                "summary": xai_output.get("plain_english_explanation") or "Interpreted analysis results, explainability output, limitations, and recommendations.",
                "steps": xai_steps,
            },
        ]

    def _completed_step(self, name: str) -> dict[str, Any]:
        return {"name": name, "status": "completed", "timestamp": utc_now_iso()}

    def _analysis_steps(self) -> list[dict[str, Any]]:
        return [
            self._completed_step("Parsing dataset"),
            self._completed_step("Building semantic map"),
            self._completed_step("Computing EDA"),
            self._completed_step("Computing business metrics"),
            self._completed_step("Detecting trends"),
            self._completed_step("Prediction readiness"),
        ]

    def _xai_report_steps(
        self,
        prediction: dict[str, Any] | None,
        *,
        run_xai: bool,
        generate_report: bool,
    ) -> list[dict[str, Any]]:
        prediction_status = (prediction or {}).get("status")
        explanation_step = "Explaining why prediction and XAI were skipped"
        if run_xai and prediction_status == "complete":
            explanation_step = "Running SHAP or fallback explanation"
        return [
            self._completed_step("Checking model availability"),
            self._completed_step(explanation_step),
            self._completed_step("Generating recommendations"),
            self._completed_step("Generating report with Gemini" if generate_report else "Skipping report generation"),
        ]

    async def _insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.supabase.configured:
            return await self.supabase.insert(table, payload)
        return self.local.insert(table, payload)

    async def _update(self, table: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.supabase.configured:
            return await self.supabase.update(table, row_id, payload)
        return self.local.update(table, row_id, payload)

    async def _delete(self, table: str, row_id: str) -> None:
        if self.supabase.configured:
            await self.supabase.delete(table, row_id)
        else:
            self.local.delete(table, row_id)

    async def _all_rows(self, table: str) -> list[dict[str, Any]]:
        if self.supabase.configured:
            return await self.supabase.select(table, "select=*")
        return self.local.read_table(table)

    async def _get_by_id(self, table: str, row_id: str) -> dict[str, Any] | None:
        if self.supabase.configured:
            rows = await self.supabase.select(table, f"select=*&id=eq.{quote(row_id)}&limit=1")
        else:
            rows = [row for row in self.local.read_table(table) if str(row.get("id")) == str(row_id)]
        return rows[0] if rows else None


def normalize_charts(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for chart in charts[:6]:
        data = chart.get("data") or []
        x_key = chart.get("x_key") or chart.get("x") or "label"
        y_key = chart.get("y_key") or chart.get("y")
        if isinstance(data, list) and data:
            normalized.append({
                "type": chart.get("type", "bar"),
                "title": chart.get("title", "Chart"),
                "data": data,
                "x_key": x_key,
                "y_key": y_key,
            })
    return normalized


def build_tables(facts: dict[str, Any]) -> list[dict[str, Any]]:
    profile = facts.get("dataset_profile") or {}
    quality = facts.get("data_quality") or {}
    metrics = facts.get("business_metrics") or {}
    rows = [
        {"metric": "Rows", "value": profile.get("row_count", 0)},
        {"metric": "Columns", "value": profile.get("column_count", 0)},
        {"metric": "Missing cells", "value": quality.get("missing_cells", 0)},
        {"metric": "Duplicate rows", "value": quality.get("duplicate_rows", 0)},
    ]
    for key in ("total_revenue", "total_quantity", "total_profit", "gross_margin"):
        if metrics.get(key) is not None:
            rows.append({"metric": key.replace("_", " ").title(), "value": metrics[key]})
    return [{"title": "Analysis Summary", "columns": ["metric", "value"], "rows": rows}]


session_service = SessionService()
