"""Chat session, dataset, agent-run, and report orchestration."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from ..api.upload_parsing import parse_uploaded_dataframe
from ..core.config import settings
from .analysis_pipeline import AnalysisPipeline
from .data_quality import json_safe, normalize_chart_specs
from .report_generator import ReportGenerator
from .semantic_mapper import SemanticMapper
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

    async def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if self.supabase.configured:
            query = "select=*&order=updated_at.desc&limit=50"
            if user_id:
                query = f"select=*&user_id=eq.{quote(user_id)}&order=updated_at.desc&limit=50"
            rows = await self.supabase.select("chat_sessions", query)
        else:
            local_rows = self.local.read_table("chat_sessions")
            if user_id:
                local_rows = [row for row in local_rows if str(row.get("user_id")) == str(user_id)]
            rows = sorted(local_rows, key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
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
        session = await self._get_by_id("chat_sessions", session_id)
        if not session:
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
            persisted_path = self.local.write_bytes(f"datasets/{storage_path}", content)
        profile = AnalysisPipeline().profile_dataset(df)
        semantic_map = SemanticMapper().map_dataframe(df, filename=safe_name)
        profile["semantic_map"] = semantic_map
        semantic_type = semantic_map.get("dataset_type")
        if semantic_type and profile.get("dataset_type") in {None, "generic", "generic_tabular"}:
            profile["dataset_type"] = semantic_type
        profile["preview"] = json_safe(df.head(25).to_dict(orient="records"))
        columns = [{"name": str(col), "dtype": str(df[col].dtype)} for col in df.columns]
        persist_semantic_map_for_dataset(session_id, dataset_id, semantic_map)
        persist_semantic_map_for_session(session_id, semantic_map)
        now = utc_now_iso()
        dataset = {
            "id": dataset_id,
            "session_id": session_id,
            "user_id": session.get("user_id"),
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

    async def list_datasets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        if self.supabase.configured:
            query = "select=*&order=created_at.desc&limit=50"
            if user_id:
                query = f"select=*&user_id=eq.{quote(user_id)}&order=created_at.desc&limit=50"
            rows = await self.supabase.select("datasets", query)
        else:
            local_rows = self.local.read_table("datasets")
            if user_id:
                local_rows = [row for row in local_rows if str(row.get("user_id")) == str(user_id)]
            rows = sorted(local_rows, key=lambda item: item.get("created_at") or "", reverse=True)[:50]
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
        dataset_steps = self._dataset_steps()
        dataset_run = await self._start_agent(
            session_id,
            dataset_id,
            "DatasetAgent",
            {"dataset_id": dataset_id},
            steps=dataset_steps,
        )
        await self._complete_agent(dataset_run["id"], {
            "summary": f"Loaded {dataset.get('filename')} with {dataset.get('row_count')} rows and {dataset.get('column_count')} columns.",
            "dataset_profile": dataset.get("schema_profile"),
            "steps": dataset_steps,
        })

        analysis_steps = self._analysis_steps()
        report_steps = self._report_steps(run_xai=run_xai, generate_report=generate_report)
        analyst_run = await self._start_agent(
            session_id,
            dataset_id,
            "AnalystAgent",
            {"prompt": user_prompt},
            steps=analysis_steps + report_steps,
        )
        facts = await AnalysisPipeline().run_full_analysis_async(
            df,
            query=user_prompt,
            run_xai=run_xai,
            session_id=session_id,
            filename=metadata.get("filename") or dataset.get("filename"),
            use_llm=settings.USE_LLM_NARRATION,
            provider=settings.LLM_PROVIDER,
        )
        await self._complete_agent(analyst_run["id"], {
            "summary": facts.get("executive_summary"),
            "dataset_profile": facts.get("dataset_profile"),
            "business_metrics": facts.get("business_metrics"),
            "product_analysis": facts.get("product_analysis"),
            "charts": facts.get("charts"),
            "warnings": facts.get("warnings"),
            "steps": analysis_steps + report_steps,
        })
        xai_output = facts.get("xai") if run_xai else {"status": "skipped", "plain_english_explanation": "XAI was skipped for this request."}

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
        should_generate_report = bool(generate_report)
        report_facts = _promote_full_report_facts(facts) if should_generate_report else facts
        if should_generate_report:
            report_payload = await self.generate_report(session_id, dataset_id, title, report_facts, xai_output if isinstance(xai_output, dict) else {})

        answer = (facts.get("query_answer") or {}).get("answer") or facts.get("executive_summary") or "Analysis complete."
        response_charts = _response_charts(report_facts, include_report_level=should_generate_report)
        response_tables = _response_tables(report_facts if should_generate_report else facts)
        xai_payload = _response_xai(report_facts if should_generate_report else facts, xai_output if isinstance(xai_output, dict) else {})
        assistant_payload = {
            "agents": self._agent_summary(
                dataset_run,
                analyst_run,
                dataset_steps=dataset_steps,
                analysis_steps=analysis_steps,
                report_steps=report_steps,
                facts=report_facts,
                xai_output=xai_output if isinstance(xai_output, dict) else {},
            ),
            "kpis": facts.get("kpis") or [],
            "charts": response_charts,
            "tables": response_tables,
            "warnings": facts.get("warnings") or [],
            "recommendations": facts.get("recommendations") or [],
            "report": report_payload,
            "xai": xai_payload,
        }
        await self.add_message(session_id, "assistant", answer, payload=assistant_payload)
        return {
            "session_id": session_id,
            "dataset_id": dataset_id,
            "title": title,
            "agents": assistant_payload["agents"],
            "answer": answer,
            "kpis": assistant_payload["kpis"],
            "tables": response_tables,
            "charts": response_charts,
            "warnings": assistant_payload["warnings"],
            "recommendations": assistant_payload["recommendations"],
            "report": report_payload,
            "xai": xai_payload,
        }

    async def chat_message(self, session_id: str, content: str, dataset_id: str | None = None) -> dict[str, Any]:
        return await self.analyze(
            session_id,
            dataset_id=dataset_id,
            user_prompt=content,
            run_xai=True,
            generate_report=_explicit_report_request(content),
        )
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
        dataset_run: dict[str, Any],
        analyst_run: dict[str, Any],
        *,
        dataset_steps: list[dict[str, Any]],
        analysis_steps: list[dict[str, Any]],
        report_steps: list[dict[str, Any]],
        facts: dict[str, Any],
        xai_output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": "DatasetAgent",
                "status": "completed",
                "summary": "Loaded the attached dataset, profile, and semantic context for this session.",
                "steps": dataset_steps,
            },
            {
                "name": "AnalystAgent",
                "status": "completed",
                "summary": facts.get("executive_summary") or xai_output.get("plain_english_explanation") or "Computed analysis, charts, tables, explainability, recommendations, and report output.",
                "steps": analysis_steps + report_steps,
            },
        ]

    def _completed_step(self, name: str) -> dict[str, Any]:
        return {"name": name, "status": "completed", "timestamp": utc_now_iso()}

    def _dataset_steps(self) -> list[dict[str, Any]]:
        return [
            self._completed_step("Loading persisted dataset"),
            self._completed_step("Validating active dataset"),
            self._completed_step("Reading profile and semantic map"),
        ]

    def _analysis_steps(self) -> list[dict[str, Any]]:
        return [
            self._completed_step("Parsing dataset"),
            self._completed_step("Building semantic map"),
            self._completed_step("Computing EDA"),
            self._completed_step("Computing business metrics"),
            self._completed_step("Detecting trends"),
            self._completed_step("Prediction readiness"),
        ]

    def _report_steps(
        self,
        *,
        run_xai: bool,
        generate_report: bool,
    ) -> list[dict[str, Any]]:
        explanation_step = "Running XAI where model output is available" if run_xai else "Skipping XAI for this request"
        return [
            self._completed_step(explanation_step),
            self._completed_step("Generating recommendations"),
            self._completed_step("Generating professional report" if generate_report else "Skipping report generation"),
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
    normalized, _warnings = normalize_chart_specs(charts, limit=10)
    return normalized


def _response_charts(facts: dict[str, Any], *, include_report_level: bool) -> list[dict[str, Any]]:
    if include_report_level or str((facts.get("query_plan") or {}).get("report_mode")) == "full_analysis_report":
        return normalize_charts(facts.get("charts") or [])
    return normalize_charts((facts.get("query_answer") or {}).get("charts") or [])


def _response_tables(facts: dict[str, Any]) -> list[dict[str, Any]]:
    intent = str((facts.get("query_plan") or {}).get("intent") or "")
    query_tables = (facts.get("query_answer") or {}).get("tables") or []
    if query_tables and intent in {"total_sales", "top_product", "top_products", "revenue_by_month", "revenue_trend", "category_performance", "region_performance", "profit_summary", "prediction"}:
        return query_tables
    return build_tables(facts)


def _response_xai(facts: dict[str, Any], xai_output: dict[str, Any]) -> dict[str, Any] | None:
    query_plan = facts.get("query_plan") or {}
    prediction = facts.get("prediction") or {}
    if prediction.get("status") != "complete":
        return None
    if query_plan.get("intent") != "prediction" and str(query_plan.get("report_mode")) != "full_analysis_report":
        return None
    return xai_output or None


def _should_generate_report(facts: dict[str, Any]) -> bool:
    query_plan = facts.get("query_plan") or {}
    return str(query_plan.get("report_mode")) == "full_analysis_report" or str(query_plan.get("intent")) == "full_report"


def _explicit_report_request(content: str) -> bool:
    q = content.lower()
    if any(phrase in q for phrase in ["full report", "generate report", "make report", "make a report", "analysis report", "detailed report", "report of"]):
        return True
    return "report" in q and any(word in q for word in ["make", "generate", "create", "build"])


def _promote_full_report_facts(facts: dict[str, Any]) -> dict[str, Any]:
    promoted = dict(facts)
    query_plan = dict(promoted.get("query_plan") or {})
    query_plan["report_mode"] = "full_analysis_report"
    promoted["query_plan"] = query_plan
    charts = list(promoted.get("charts") or [])
    if not charts:
        charts = _merge_chart_sources(
            (promoted.get("query_answer") or {}).get("charts") or [],
            (promoted.get("food_analysis") or {}).get("charts") or [],
            (promoted.get("product_analysis") or {}).get("charts") or [],
        )
    promoted["charts"] = charts
    return promoted


def _merge_chart_sources(*chart_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in chart_groups:
        for chart in group:
            if not isinstance(chart, dict):
                continue
            key = (str(chart.get("title") or ""), str(chart.get("type") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(chart)
    return merged


def _dedupe_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    for table in tables:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows")
        if not rows:
            continue
        columns = tuple(str(column) for column in (table.get("columns") or []))
        key = (
            str(table.get("title") or ""),
            columns,
            json.dumps(rows, sort_keys=True, default=str),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(table)
    return deduped


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
    tables = [{"title": "Analysis Summary", "columns": ["metric", "value"], "rows": rows}]
    for table in (facts.get("query_answer") or {}).get("tables", []):
        if isinstance(table, dict) and table.get("rows"):
            tables.append(table)
    for table in (facts.get("food_analysis") or {}).get("tables", []):
        if isinstance(table, dict) and table.get("rows"):
            tables.append(table)
    for table in (facts.get("product_analysis") or {}).get("tables", []):
        if isinstance(table, dict) and table.get("rows"):
            tables.append(table)
    return _dedupe_tables(tables)[:8]


session_service = SessionService()
