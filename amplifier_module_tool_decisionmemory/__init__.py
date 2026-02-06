"""
Decision Memory module for Amplifier.

Provides persistent storage and retrieval of strategic decisions.
Designed to integrate with SAGE but usable by any tool.

Storage location: ~/.amplifier/memories/decisions/{project-slug}/decisions.jsonl
"""

__amplifier_module_type__ = "tool"

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from amplifier_core import ModuleCoordinator, ToolResult

logger = logging.getLogger(__name__)

# Storage location follows Amplifier conventions
DECISIONS_BASE_DIR = Path.home() / ".amplifier" / "memories" / "decisions"

# Decision status types
DecisionStatus = Literal["active", "superseded", "implemented", "rejected"]

# Domain types (matches SAGE domains)
DomainType = Literal["architecture", "design", "product", "implementation", "outcomes", "general"]


async def mount(coordinator: ModuleCoordinator, config: dict[str, Any] | None = None):
    """Mount the decision memory tool."""
    config = config or {}
    tool = DecisionMemoryTool(coordinator, config)
    await coordinator.mount("tools", tool, name=tool.name)

    # Register capabilities for other modules (like SAGE) to use directly
    coordinator.register_capability("decisions.record", tool.record_decision)
    coordinator.register_capability("decisions.query", tool.query_decisions)
    coordinator.register_capability("decisions.get_recent", tool.get_recent_decisions)

    logger.info(f"Mounted decision memory tool (project: {tool.project_slug})")


class DecisionMemoryTool:
    """Store and retrieve strategic decisions across sessions.

    Provides persistent memory for strategic decisions made during SAGE consultations
    or other advisory interactions. Decisions are stored in JSONL format following
    Amplifier conventions.
    """

    name = "decision_memory"
    description = """Query and manage strategic decisions made during consultations.

**Operations:**
- `record`: Save a new decision
- `query`: Search past decisions by domain, tags, date, or status
- `update`: Update decision status (implemented, superseded, rejected)
- `list`: List recent decisions
- `get`: Get a specific decision by ID

**Use Cases:**
- Record important architecture/design decisions for future reference
- Query past decisions before making related choices
- Track decision status (active → implemented/superseded/rejected)
- Provide context to SAGE from previous consultations

**Example - Record:**
```json
{
  "operation": "record",
  "decision": {
    "domain": "architecture",
    "question": "Should we use microservices?",
    "recommendation": "Start with a modular monolith",
    "reasoning": "Team size and timeline don't justify microservices overhead",
    "tradeoffs": ["Simpler deployment", "Harder to scale independently later"],
    "tags": ["infrastructure", "mvp"]
  }
}
```

**Example - Query:**
```json
{
  "operation": "query",
  "query": {
    "domain": "architecture",
    "status": "active",
    "limit": 5
  }
}
```"""

    def __init__(self, coordinator: ModuleCoordinator, config: dict[str, Any]):
        self.coordinator = coordinator
        self.config = config
        self.project_slug = self._get_project_slug()
        self.decisions_dir = DECISIONS_BASE_DIR / self.project_slug
        self.decisions_file = self.decisions_dir / "decisions.jsonl"

        # Ensure directory exists
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def _get_project_slug(self) -> str:
        """Get project slug from coordinator or derive from cwd."""
        # Try to get from coordinator config
        if hasattr(self.coordinator, "config"):
            if slug := self.coordinator.config.get("project_slug"):
                return slug

        # Fall back to current working directory name
        cwd = Path.cwd()
        return cwd.name.lower().replace(" ", "-")

    @property
    def input_schema(self) -> dict:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["record", "query", "update", "list", "get"],
                    "description": "Operation to perform",
                },
                "decision": {
                    "type": "object",
                    "description": "Decision to record (for 'record' operation)",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "enum": ["architecture", "design", "product", "implementation", "outcomes", "general"],
                            "description": "Domain of the decision",
                        },
                        "question": {"type": "string", "description": "The question that was asked"},
                        "recommendation": {"type": "string", "description": "The recommendation made"},
                        "reasoning": {"type": "string", "description": "Why this recommendation"},
                        "tradeoffs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Explicit tradeoffs of this decision",
                        },
                        "outcome": {"type": "string", "description": "Expected outcome"},
                        "context": {"type": "object", "description": "Original context provided"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization",
                        },
                        "supersedes": {"type": "string", "description": "ID of decision this supersedes"},
                    },
                    "required": ["domain", "question", "recommendation"],
                },
                "query": {
                    "type": "object",
                    "description": "Query parameters (for 'query' and 'list' operations)",
                    "properties": {
                        "domain": {"type": "string", "description": "Filter by domain"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags (any match)",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "superseded", "implemented", "rejected"],
                            "description": "Filter by status",
                        },
                        "since": {"type": "string", "description": "ISO date - decisions after this"},
                        "search": {"type": "string", "description": "Text search in question/recommendation"},
                        "limit": {"type": "integer", "default": 10, "description": "Max results to return"},
                    },
                },
                "decision_id": {"type": "string", "description": "Decision ID (for 'update' and 'get')"},
                "status": {
                    "type": "string",
                    "enum": ["active", "superseded", "implemented", "rejected"],
                    "description": "New status (for 'update')",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        """Execute decision memory operation."""
        operation = input.get("operation")

        if operation == "record":
            return await self._record(input.get("decision", {}))
        elif operation == "query":
            return await self._query(input.get("query", {}))
        elif operation == "update":
            return await self._update(input.get("decision_id"), input.get("status"))
        elif operation == "list":
            return await self._list(input.get("query", {}).get("limit", 10))
        elif operation == "get":
            return await self._get(input.get("decision_id"))

        return ToolResult(success=False, error={"message": f"Unknown operation: {operation}"})

    async def _record(self, decision: dict) -> ToolResult:
        """Record a new decision."""
        if not decision.get("question") or not decision.get("recommendation"):
            return ToolResult(success=False, error={"message": "Decision must include 'question' and 'recommendation'"})

        # Build the record
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": getattr(self.coordinator, "session_id", None),
            "project": self.project_slug,
            "status": "active",
            "domain": decision.get("domain", "general"),
            "question": decision["question"],
            "recommendation": decision["recommendation"],
            "reasoning": decision.get("reasoning"),
            "tradeoffs": decision.get("tradeoffs", []),
            "outcome": decision.get("outcome"),
            "context": decision.get("context", {}),
            "tags": decision.get("tags", []),
            "supersedes": decision.get("supersedes"),
        }

        # If this supersedes another decision, mark the old one
        if record["supersedes"]:
            await self._update(record["supersedes"], "superseded")

        # Append to JSONL file (atomic for single writes)
        with self.decisions_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"Recorded decision {record['id']} in domain {record['domain']}")

        return ToolResult(
            success=True,
            output={
                "message": "Decision recorded",
                "decision_id": record["id"],
                "domain": record["domain"],
                "timestamp": record["timestamp"],
            },
        )

    async def _query(self, params: dict) -> ToolResult:
        """Query past decisions with filters."""
        decisions = self._read_all()

        # Apply filters
        if domain := params.get("domain"):
            decisions = [d for d in decisions if d.get("domain") == domain]

        if tags := params.get("tags"):
            decisions = [d for d in decisions if any(t in d.get("tags", []) for t in tags)]

        if status := params.get("status"):
            decisions = [d for d in decisions if d.get("status") == status]

        if since := params.get("since"):
            decisions = [d for d in decisions if d.get("timestamp", "") >= since]

        if search := params.get("search"):
            search_lower = search.lower()
            decisions = [
                d
                for d in decisions
                if search_lower in d.get("question", "").lower() or search_lower in d.get("recommendation", "").lower()
            ]

        # Sort by timestamp descending
        decisions.sort(key=lambda d: d.get("timestamp", ""), reverse=True)

        # Apply limit
        limit = params.get("limit", 10)
        decisions = decisions[:limit]

        return ToolResult(success=True, output={"count": len(decisions), "decisions": decisions})

    async def _update(self, decision_id: str | None, status: str | None) -> ToolResult:
        """Update a decision's status."""
        if not decision_id:
            return ToolResult(success=False, error={"message": "decision_id is required"})
        if not status:
            return ToolResult(success=False, error={"message": "status is required"})

        decisions = self._read_all()
        updated = False

        for d in decisions:
            if d["id"] == decision_id:
                d["status"] = status
                d["updated_at"] = datetime.now(UTC).isoformat()
                updated = True
                break

        if not updated:
            return ToolResult(success=False, error={"message": f"Decision {decision_id} not found"})

        # Rewrite the file
        self._write_all(decisions)

        return ToolResult(success=True, output={"message": f"Decision {decision_id} updated to status '{status}'"})

    async def _list(self, limit: int = 10) -> ToolResult:
        """List recent decisions."""
        return await self._query({"limit": limit, "status": "active"})

    async def _get(self, decision_id: str | None) -> ToolResult:
        """Get a specific decision by ID."""
        if not decision_id:
            return ToolResult(success=False, error={"message": "decision_id is required"})

        decisions = self._read_all()
        for d in decisions:
            if d["id"] == decision_id:
                return ToolResult(success=True, output={"decision": d})

        return ToolResult(success=False, error={"message": f"Decision {decision_id} not found"})

    def _read_all(self) -> list[dict]:
        """Read all decisions from file."""
        if not self.decisions_file.exists():
            return []

        decisions = []
        with self.decisions_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        decisions.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid JSON line in {self.decisions_file}")
                        continue
        return decisions

    def _write_all(self, decisions: list[dict]) -> None:
        """Write all decisions to file (for updates)."""
        with self.decisions_file.open("w", encoding="utf-8") as f:
            for d in decisions:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # =========================================================================
    # Capability Methods (for direct use by other modules like SAGE)
    # =========================================================================

    async def record_decision(self, decision: dict) -> str | None:
        """Capability: Record decision, return ID."""
        result = await self._record(decision)
        if result.success and result.output:
            return result.output.get("decision_id")
        return None

    async def query_decisions(self, **params) -> list[dict]:
        """Capability: Query decisions."""
        result = await self._query(params)
        if result.success and result.output:
            return result.output.get("decisions", [])
        return []

    async def get_recent_decisions(self, domain: str | None = None, limit: int = 5) -> list[dict]:
        """Capability: Get recent active decisions, optionally filtered by domain."""
        params = {"status": "active", "limit": limit}
        if domain:
            params["domain"] = domain
        return await self.query_decisions(**params)
