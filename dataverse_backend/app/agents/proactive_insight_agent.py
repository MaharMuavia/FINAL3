from typing import Dict, Any, List
from jinja2 import Template
import os
from .core.tool_registry import ToolRegistry, SessionContext
from ..llm.llm_client import LLMClient


class ProactiveInsightAgent:
    """Agent for generating proactive insights after dataset upload."""

    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self.llm_client = llm_client
        self.tool_registry = tool_registry

    async def generate_insights(
        self,
        dataset_path: str,
        session_id: str,
        memory: Any
    ) -> List[Dict[str, Any]]:
        """Generate 3 proactive insights for a newly uploaded dataset."""
        from ..memory.conversation_memory import ConversationMemory

        if not isinstance(memory, ConversationMemory):
            raise TypeError("memory must be a ConversationMemory instance")

        # Get dataset profile first
        session = memory.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session_context = SessionContext(
            session_id=session_id,
            dataset_path=dataset_path,
            working_dataset_path=None
        )

        # Run quick analysis tools
        profile_result = await self.tool_registry.call_tool(
            "dataset_profile", {"n_sample_rows": 3}, session_context
        )

        stats_result = await self.tool_registry.call_tool(
            "compute_statistics", {"columns": [], "include_percentiles": False}, session_context
        )

        missing_result = await self.tool_registry.call_tool(
            "missing_value_analysis", {"columns": []}, session_context
        )

        # Compile results for LLM
        analysis_context = {
            "profile": profile_result.data,
            "statistics": stats_result.data,
            "missing_analysis": missing_result.data
        }

        # Generate insights using LLM
        insights = await self._generate_insights_with_llm(analysis_context)

        return insights

    async def _generate_insights_with_llm(self, analysis_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Use LLM to generate 3 key insights from analysis."""

        # Load proactive scan template
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "prompts",
            "proactive_scan.j2"
        )

        with open(template_path, 'r') as f:
            template_content = f.read()

        template = Template(template_content)
        prompt = template.render(analysis_context=analysis_context)

        # Call LLM
        insights_json = await self.llm_client.generate_json(prompt, max_tokens=1024)

        return insights_json.get("insights", [])
