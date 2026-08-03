import json
import csv
from pathlib import Path
from typing import List, Dict, Set, Any
from dataclasses import dataclass, asdict

@dataclass
class AttackRecord:
    """Data record for a single fuzzing iteration."""
    iteration: int
    path_nodes: List[str]
    target_sink: str
    is_success: bool
    tool_calls_count: int
    has_witness: bool
    scheduler_score: float
    actual_execution: List[str]
    realized_taint_paths: List[List[str]]


class EvaluationFramework:
    """
    Academic Evaluation Framework for XFlowFuzz.
    Tracks and calculates the core metrics defined in the paper.
    """
    def __init__(self, total_attack_paths: int, sensitive_sinks: Set[str]):
        self.total_paths = total_attack_paths
        self.sensitive_sinks = sensitive_sinks
        
        self.records: List[AttackRecord] = []
        self.realized_paths: Set[tuple] = set()
        self.reached_sensitive_sinks: Set[str] = set()
        
        # Output directory for reports
        self.output_dir = Path(__file__).parent.parent / "results"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log_iteration(self, iteration: int, path: List[str], target_sink: str,
                      is_success: bool, tool_calls: int, has_witness: bool, score: float,
                      actual_execution: List[str] | None = None,
                      realized_taint_paths: List[List[str]] | None = None):
        """Log one campaign iteration.

        Path coverage is updated from dynamically confirmed taint paths, not
        merely from the scheduler's target path. This keeps the denominator and
        numerator consistent with XFlowFuzz's path-sensitive coverage definition.
        """
        execution = list(actual_execution or [])
        confirmed_paths = [list(item) for item in (realized_taint_paths or [])]
        record = AttackRecord(
            iteration=iteration,
            path_nodes=list(path),
            target_sink=target_sink,
            is_success=is_success,
            tool_calls_count=tool_calls,
            has_witness=has_witness,
            scheduler_score=score,
            actual_execution=execution,
            realized_taint_paths=confirmed_paths,
        )
        self.records.append(record)

        # 1. PATH COVERAGE: only concrete source-to-sink taint paths count.
        for realized_path in confirmed_paths:
            if realized_path:
                self.realized_paths.add(tuple(realized_path))

        # Backward compatibility for callers that do not yet provide paths.
        if is_success and not confirmed_paths:
            self.realized_paths.add(tuple(path))

        # 2. SINK COVERAGE: a sink counts when it was actually invoked.
        for tool in execution:
            if tool in self.sensitive_sinks:
                self.reached_sensitive_sinks.add(tool)

        if not execution and is_success and target_sink in self.sensitive_sinks:
            self.reached_sensitive_sinks.add(target_sink)

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate transparent campaign metrics with explicit definitions."""
        total_attempts = len(self.records)
        successful_records = [record for record in self.records if record.is_success]
        trigger_records = [record for record in self.records if record.has_witness]
        success_count = len(successful_records)
        distinct_paths = len(self.realized_paths)

        path_coverage = (
            distinct_paths / self.total_paths * 100
            if self.total_paths > 0 else 0.0
        )
        success_rate = (
            success_count / total_attempts * 100
            if total_attempts > 0 else 0.0
        )

        first_trigger_iteration = (
            min(record.iteration for record in trigger_records)
            if trigger_records else None
        )
        mean_trigger_iteration = (
            sum(record.iteration for record in trigger_records) / len(trigger_records)
            if trigger_records else None
        )

        witness_count = sum(1 for record in self.records if record.has_witness)
        total_sensitive = len(self.sensitive_sinks)
        sink_coverage = (
            len(self.reached_sensitive_sinks) / total_sensitive * 100
            if total_sensitive > 0 else 0.0
        )
        avg_tool_calls = (
            sum(record.tool_calls_count for record in successful_records) / success_count
            if success_count > 0 else 0.0
        )
        average_target_score = (
            sum(record.scheduler_score for record in self.records) / total_attempts
            if total_attempts > 0 else 0.0
        )
        new_paths_per_attempt = (
            distinct_paths / total_attempts
            if total_attempts > 0 else 0.0
        )
        attempts_per_new_path = (
            total_attempts / distinct_paths
            if distinct_paths > 0 else None
        )

        return {
            "total_attempts": total_attempts,
            "distinct_realized_paths": distinct_paths,
            "path_coverage_percent": round(path_coverage, 2),
            "success_rate_percent": round(success_rate, 2),
            "first_trigger_iteration": first_trigger_iteration,
            "mean_trigger_iteration": (
                round(mean_trigger_iteration, 2)
                if mean_trigger_iteration is not None else None
            ),
            "witness_count": witness_count,
            "sink_coverage_percent": round(sink_coverage, 2),
            "avg_tool_calls_per_success": round(avg_tool_calls, 2),
            "new_paths_per_attempt": round(new_paths_per_attempt, 4),
            "attempts_per_new_path": (
                round(attempts_per_new_path, 2)
                if attempts_per_new_path is not None else None
            ),
            "average_target_score": round(average_target_score, 2),
            # Compatibility aliases retained for old analysis scripts.
            "time_to_trigger_avg_iters": first_trigger_iteration or 0,
            "scheduler_efficiency_score": round(average_target_score, 2),
        }

    def summary(self) -> str:
        """Export a human-readable report with unambiguous metric names."""
        metrics = self._calculate_metrics()
        success_count = len([record for record in self.records if record.is_success])
        first_trigger = (
            str(metrics["first_trigger_iteration"])
            if metrics["first_trigger_iteration"] is not None else "N/A"
        )
        mean_trigger = (
            str(metrics["mean_trigger_iteration"])
            if metrics["mean_trigger_iteration"] is not None else "N/A"
        )
        attempts_per_path = (
            str(metrics["attempts_per_new_path"])
            if metrics["attempts_per_new_path"] is not None else "N/A"
        )

        report = f"""
{'='*58}
   XFLOWFUZZ: ACADEMIC EVALUATION REPORT
{'='*58}
1. Path Coverage          : {metrics['path_coverage_percent']}% ({len(self.realized_paths)}/{self.total_paths} distinct paths)
2. Sink Coverage          : {metrics['sink_coverage_percent']}% ({len(self.reached_sensitive_sinks)}/{len(self.sensitive_sinks)} sensitive sinks)
3. Attempt Success Rate   : {metrics['success_rate_percent']}% ({success_count}/{metrics['total_attempts']} attempts)
4. Witness Count          : {metrics['witness_count']} verified leaks
5. Time to First Trigger  : {first_trigger} iteration
6. Mean Trigger Iteration : {mean_trigger}
7. Avg Tool Calls/Success : {metrics['avg_tool_calls_per_success']}
8. New Paths per Attempt  : {metrics['new_paths_per_attempt']}
9. Attempts per New Path  : {attempts_per_path}
10. Avg Target Score      : {metrics['average_target_score']}
{'='*58}
"""
        return report

    def export_json(self, filename: str = "eval_results.json"):
        """Export raw data to JSON for visualization."""
        filepath = self.output_dir / filename
        data = {
            "metrics": self._calculate_metrics(),
            "raw_records": [asdict(r) for r in self.records]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[Export] Saved JSON evaluation report to: {filepath}")

    def export_csv(self, filename: str = "eval_results.csv"):
        """Export iteration history to CSV."""
        if not self.records:
            return
            
        filepath = self.output_dir / filename
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self.records[0]).keys())
            writer.writeheader()
            for record in self.records:
                writer.writerow(asdict(record))
        print(f"[Export] Saved CSV iterations to: {filepath}")
# ---------------------------------------------------------------------------
# Runtime/cost metrics retained from Person A's evaluation layer.
# ---------------------------------------------------------------------------
from statistics import mean
from typing import Iterable, Mapping

@dataclass(frozen=True)
class TokenPricing:
    input_per_million: float
    output_per_million: float

@dataclass(frozen=True)
class CostEstimate:
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float

@dataclass(frozen=True)
class LatencySummary:
    total_s: float
    average_s: float
    minimum_s: float
    maximum_s: float

@dataclass(frozen=True)
class RuntimeMetrics:
    runs: int
    successful_runs: int
    triggered_runs: int
    reproducibility: float
    trials_to_trigger: int | None
    time_to_trigger_s: float | None
    latency: LatencySummary
    input_tokens: int
    output_tokens: int
    estimated_cost: CostEstimate | None


def summarize_latency(rows: Iterable[Mapping[str, Any]]) -> LatencySummary:
    values = [float(row.get("elapsed_s", 0.0) or 0.0) for row in rows]
    if not values:
        return LatencySummary(0.0, 0.0, 0.0, 0.0)
    return LatencySummary(sum(values), mean(values), min(values), max(values))


def reproducibility(rows: Iterable[Mapping[str, Any]]) -> float:
    values = list(rows)
    if not values:
        return 0.0
    return sum(bool(row.get("success")) for row in values) / len(values)


def trials_to_trigger(rows: Iterable[Mapping[str, Any]]) -> int | None:
    for index, row in enumerate(rows, 1):
        if bool(row.get("detected")):
            return index
    return None


def time_to_trigger(rows: Iterable[Mapping[str, Any]]) -> float | None:
    elapsed = 0.0
    for row in rows:
        elapsed += float(row.get("elapsed_s", 0.0) or 0.0)
        if bool(row.get("detected")):
            return elapsed
    return None


def estimate_cost(input_tokens: int, output_tokens: int, pricing: TokenPricing) -> CostEstimate:
    input_cost = input_tokens / 1_000_000 * pricing.input_per_million
    output_cost = output_tokens / 1_000_000 * pricing.output_per_million
    return CostEstimate(input_cost, output_cost, input_cost + output_cost)


def evaluate_runtime(rows: Iterable[Mapping[str, Any]], *, pricing: TokenPricing | None = None) -> RuntimeMetrics:
    values = list(rows)
    input_tokens = sum(int(row.get("input_tokens", 0) or 0) for row in values)
    output_tokens = sum(int(row.get("output_tokens", 0) or 0) for row in values)
    return RuntimeMetrics(
        runs=len(values),
        successful_runs=sum(bool(row.get("success")) for row in values),
        triggered_runs=sum(bool(row.get("detected")) for row in values),
        reproducibility=reproducibility(values),
        trials_to_trigger=trials_to_trigger(values),
        time_to_trigger_s=time_to_trigger(values),
        latency=summarize_latency(values),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimate_cost(input_tokens, output_tokens, pricing) if pricing else None,
    )
