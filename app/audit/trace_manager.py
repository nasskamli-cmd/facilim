"""
app/audit/trace_manager.py — Traçage de bout en bout des traitements.

Chaque traitement d'un dossier est encapsulé dans une Trace qui lie
tous les événements, agents et décisions de ce traitement.
Permet le replay et l'explication juridique d'une décision.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger("facilim.audit.trace")


@dataclass
class TraceStep:
    agent:       str
    action:      str
    input_hash:  str | None = None
    output_hash: str | None = None
    duree_ms:    int = 0
    score:       float | None = None
    flag:        bool = False
    metadata:    dict[str, Any] = field(default_factory=dict)
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProcessingTrace:
    trace_id:   str = field(default_factory=lambda: str(uuid.uuid4()))
    dossier_id: str | None = None
    usager_id:  str | None = None
    steps:      list[TraceStep] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at:   str | None = None
    replayable: bool = True

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)
        logger.debug(
            f"[TRACE:{self.trace_id[:8]}] {step.agent} | {step.action}"
            + (f" | score={step.score}" if step.score is not None else "")
            + (" | FLAG" if step.flag else "")
        )

    def close(self) -> None:
        self.ended_at = datetime.now(timezone.utc).isoformat()

    def has_flags(self) -> bool:
        return any(s.flag for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id":   self.trace_id,
            "dossier_id": self.dossier_id,
            "usager_id":  self.usager_id,
            "steps":      [
                {
                    "agent":      s.agent,
                    "action":     s.action,
                    "duree_ms":   s.duree_ms,
                    "score":      s.score,
                    "flag":       s.flag,
                    "timestamp":  s.timestamp,
                }
                for s in self.steps
            ],
            "started_at": self.started_at,
            "ended_at":   self.ended_at,
            "has_flags":  self.has_flags(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# Registre en mémoire des traces actives (production : Redis)
_active_traces: dict[str, ProcessingTrace] = {}


def start_trace(dossier_id: str | None = None, usager_id: str | None = None) -> ProcessingTrace:
    trace = ProcessingTrace(dossier_id=dossier_id, usager_id=usager_id)
    _active_traces[trace.trace_id] = trace
    logger.info(f"[TRACE] Démarrage | trace={trace.trace_id[:8]}" + (f" | dossier={dossier_id[:8]}" if dossier_id else ""))
    return trace


def get_trace(trace_id: str) -> ProcessingTrace | None:
    return _active_traces.get(trace_id)


def close_trace(trace: ProcessingTrace) -> dict[str, Any]:
    trace.close()
    _active_traces.pop(trace.trace_id, None)
    return trace.to_dict()


@contextmanager
def timed_step(
    trace: ProcessingTrace,
    agent: str,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceStep, None, None]:
    """Context manager pour mesurer et tracer une étape de traitement."""
    step = TraceStep(agent=agent, action=action, metadata=metadata or {})
    start = time.monotonic()
    try:
        yield step
    finally:
        step.duree_ms = int((time.monotonic() - start) * 1000)
        trace.add_step(step)
