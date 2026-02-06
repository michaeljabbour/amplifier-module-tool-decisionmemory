# Amplifier Module: Decision Memory

Persistent storage and retrieval of strategic decisions for the Amplifier ecosystem.

## Overview

This module provides a simple, file-based memory system for tracking strategic decisions made during SAGE consultations or other advisory interactions. Decisions are stored in JSONL format following Amplifier conventions.

## Installation

Add to your bundle:

```yaml
tools:
  - module: tool-decisionmemory
    source: git+https://github.com/michaeljabbour/amplifier-module-tool-decisionmemory@main
```

Or for local development:

```bash
export AMPLIFIER_MODULE_TOOL_DECISIONMEMORY=~/dev/amplifier-module-tool-decisionmemory
```

## Storage

Decisions are stored at:
```
~/.amplifier/memories/decisions/{project-slug}/decisions.jsonl
```

## Operations

| Operation | Description |
|-----------|-------------|
| `record` | Save a new decision |
| `query` | Search decisions by domain, tags, date, status |
| `update` | Change decision status |
| `list` | List recent active decisions |
| `get` | Get specific decision by ID |

## Decision Schema

```json
{
  "id": "uuid",
  "timestamp": "2025-01-21T...",
  "domain": "architecture|design|product|implementation|outcomes",
  "question": "The question asked",
  "recommendation": "The recommendation made",
  "reasoning": "Why this recommendation",
  "tradeoffs": ["tradeoff 1", "tradeoff 2"],
  "outcome": "Expected outcome",
  "tags": ["tag1", "tag2"],
  "status": "active|superseded|implemented|rejected"
}
```

## Usage Examples

### Record a Decision
```json
{
  "operation": "record",
  "decision": {
    "domain": "architecture",
    "question": "Should we use microservices or monolith?",
    "recommendation": "Start with modular monolith",
    "reasoning": "Team size doesn't justify microservices overhead",
    "tradeoffs": ["Simpler ops", "Harder to scale independently"],
    "tags": ["infrastructure", "mvp"]
  }
}
```

### Query Past Decisions
```json
{
  "operation": "query",
  "query": {
    "domain": "architecture",
    "status": "active",
    "limit": 5
  }
}
```

### Update Decision Status
```json
{
  "operation": "update",
  "decision_id": "abc-123",
  "status": "implemented"
}
```

## Integration with SAGE

When both SAGE and Decision Memory are mounted, SAGE can automatically record decisions via the `decisions.record` capability.

## Capabilities

The module registers these capabilities for direct use by other modules:

| Capability | Signature |
|------------|-----------|
| `decisions.record` | `record_decision(decision: dict) -> str` |
| `decisions.query` | `query_decisions(**params) -> list[dict]` |
| `decisions.get_recent` | `get_recent_decisions(domain?, limit?) -> list[dict]` |

## License

MIT
