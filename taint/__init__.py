"""Dynamic-taint tracking for XFlowFuzz."""

from .taint_engine import TaintEngine
from .taint_label import TaintLabel
from .witness import LabelTraceEntry, Witness

__all__ = ["LabelTraceEntry", "TaintEngine", "TaintLabel", "Witness"]
