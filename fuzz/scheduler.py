import random
from typing import List, Optional, Dict
from xFlowFuzz.graph.path_enum import AttackPath

class Scheduler:
    """
    Smart Heuristic-Driven Scheduler.
    Prioritizes attack paths based on Coverage Gain, Risk, Novelty, and Length 
    using probabilistic sampling (energy-assignment).
    """
    def __init__(self, all_paths: List[AttackPath], 
                 sensitive_sinks: set = None,
                 w_coverage: float = 1.0, 
                 w_risk: float = 2.0, 
                 w_novelty: float = 1.5, 
                 w_length: float = 0.5):
        
        self.pending_paths = list(all_paths)
        self.w1 = w_coverage
        self.w2 = w_risk
        self.w3 = w_novelty
        self.w4 = w_length
        self.attempt_counts: Dict[tuple, int] = {tuple(p.nodes): 0 for p in all_paths}
        self.realized_nodes: set = set()
        
        self.sensitive_sinks = sensitive_sinks if sensitive_sinks else set()
    
    def score(self, path: AttackPath) -> float:
        """
        Calculates the Priority Score (Energy) for a given path based on the paper's heuristic.
        """
        # 1. CoverageGain: How many nodes in this path are completely unexplored globally?
        unexplored_nodes = sum(1 for node in path.nodes if node not in self.realized_nodes)
        coverage_gain = unexplored_nodes / path.length if path.length > 0 else 0

        # 2. RiskScore: Higher score if the sink is highly sensitive
        risk_score = 1.0 if path.sink in self.sensitive_sinks else 0.0

        # 3. Novelty: Penalize paths we have already attempted multiple times
        attempts = self.attempt_counts.get(tuple(path.nodes), 0)
        novelty = 1.0 / (attempts + 1) # Approaches 0 as attempts increase

        # 4. ShortPathBonus: Prefer shorter paths (less chance of LLM hallucination/drift)
        short_path_bonus = 1.0 / path.length if path.length > 0 else 0

        # Calculate final weighted score
        total_score = (self.w1 * coverage_gain) + \
                      (self.w2 * risk_score) + \
                      (self.w3 * novelty) + \
                      (self.w4 * short_path_bonus)
                      
        # Ensure a minimal non-zero weight for probabilistic sampling
        return max(total_score, 0.01)

    def next_path(self) -> Optional[AttackPath]:
        """
        Samples a target path with probability proportional to its heuristic score (energy).
        Aligns with the paper's probabilistic energy-assignment strategy.
        """
        if not self.pending_paths:
            return None
        
        # Deterministic highest-energy selection makes campaigns reproducible.
        # Ties prefer shorter paths, then the original queue order.
        target = max(
            enumerate(self.pending_paths),
            key=lambda item: (self.score(item[1]), -item[1].length, -item[0]),
        )[1]
        
        # Record the attempt to decrease its novelty score for future rounds
        self.attempt_counts[tuple(target.nodes)] += 1
        
        return target

    def mark_realized(self, path: AttackPath) -> None:
        """Remove successfully compromised paths from the queue."""
        path_tuple = tuple(path.nodes)
        self.pending_paths = [p for p in self.pending_paths if tuple(p.nodes) != path_tuple]
        
    def update(self, realized_path: AttackPath) -> None:
        """
        Updates the scheduler's internal knowledge base when a path succeeds.
        Used to dynamically adjust the CoverageGain of remaining paths.
        """
        self.mark_realized(realized_path)
        for node in realized_path.nodes:
            self.realized_nodes.add(node)

    def remaining(self) -> int:
        """Returns the number of uncompromised paths."""
        return len(self.pending_paths)
        
    def statistics(self) -> dict:
        """Returns internal metrics for the Evaluation module."""
        return {
            "remaining_paths": self.remaining(),
            "nodes_realized": len(self.realized_nodes),
            "highest_score_in_queue": max([self.score(p) for p in self.pending_paths]) if self.pending_paths else 0.0
        }

# =========================================================================
# SELF-TEST BLOCK
# =========================================================================
if __name__ == "__main__":
    from xFlowFuzz.graph.path_enum import AttackPath
    
    p1 = AttackPath(["read_user_document", "send_email"])                     
    p2 = AttackPath(["fetch_web_page", "extract_api_keys", "send_email"])     
    p3 = AttackPath(["read_inbox_emails", "summarize_text", "write_local_file"]) 
    
    scheduler = Scheduler([p1, p2, p3], sensitive_sinks={"send_email", "write_local_file"})
    
    print(f"=== TEST PROBABILISTIC SCHEDULER ===")
    print(f"Initial state: {scheduler.remaining()} pending paths.")
    
    print("\n[+] Initial Scores:")
    for p in scheduler.pending_paths:
        print(f" - Path: {p} | Score: {scheduler.score(p):.2f}")
        
    print("\n[+] Sampling 5 iterations (Check probabilistic distribution & Novelty penalty):")
    for i in range(5):
        target = scheduler.next_path()
        print(f"Iteration {i+1} picked: {target} (Score when picked: {scheduler.score(target):.2f})")
        
    print(f"\n[+] Simulating successful compromise of '{p1}'...")
    scheduler.update(p1)
    
    print("\n[+] Internal statistics after compromise:")
    stats = scheduler.statistics()
    for k, v in stats.items():
        print(f" - {k}: {v:.2f}" if isinstance(v, float) else f" - {k}: {v}")
        
    print("\n[+] Updated scores for remaining paths (due to shared discovered nodes):")
    for p in scheduler.pending_paths:
        print(f" - Path: {p} | Updated Score: {scheduler.score(p):.2f}")