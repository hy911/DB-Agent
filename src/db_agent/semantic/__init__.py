"""Semantic layer: the agent's typed map of in-scope tables, domains and access rules."""

from __future__ import annotations

from db_agent.semantic.loader import SemanticLayerError, load_semantic_layer
from db_agent.semantic.model import (
    AccessControl,
    Column,
    Domain,
    SemanticLayer,
    Table,
)

__all__ = [
    "AccessControl",
    "Column",
    "Domain",
    "SemanticLayer",
    "SemanticLayerError",
    "Table",
    "load_semantic_layer",
]
