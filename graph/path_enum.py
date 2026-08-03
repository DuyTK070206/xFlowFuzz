import networkx as nx
from dataclasses import dataclass
from typing import List, Dict, Iterator
from xFlowFuzz.graph.tool_graph import ToolDependencyGraph

# [NEW] Đối tượng lưu trữ luồng tấn công như bài báo yêu cầu
@dataclass
class AttackPath:
    """Đối tượng nhẹ đại diện cho một con đường tấn công trọn vẹn."""
    nodes: List[str]
    
    @property
    def source(self) -> str:
        return self.nodes[0] if self.nodes else ""
        
    @property
    def sink(self) -> str:
        return self.nodes[-1] if self.nodes else ""
        
    @property
    def length(self) -> int:
        return len(self.nodes)
        
    def __iter__(self) -> Iterator[str]:
        """Cho phép vòng lặp for (như for tool in path) hoạt động tự nhiên."""
        return iter(self.nodes)
        
    def __str__(self) -> str:
        """Giúp in ra màn hình đẹp hơn."""
        return " -> ".join(self.nodes)


class PathEnumerator:
    """
    Thuật toán tìm kiếm và liệt kê các đường dẫn tấn công.
    Hỗ trợ cấu trúc Tiền tố (Prefix Trie) để tối ưu hóa việc phân bổ năng lượng.
    """
    def __init__(self, tdg: ToolDependencyGraph):
        self.tdg = tdg
        self.graph = tdg.graph

    def get_sources(self) -> List[str]:
        return [node for node, attr in self.graph.nodes(data=True) if attr.get('type') == 'source']

    def get_sinks(self) -> List[str]:
        return [node for node, attr in self.graph.nodes(data=True) if attr.get('type') == 'sink']

    # [UPDATED] Trả về List[AttackPath] thay vì List[List[str]]
    def enumerate_all_paths(self, max_length: int = 6) -> List[AttackPath]:
        sources = self.get_sources()
        sinks = self.get_sinks()
        all_attack_paths: List[AttackPath] = []

        for source in sources:
            for sink in sinks:
                if source not in self.graph or sink not in self.graph:
                    continue
                try:
                    paths = nx.all_simple_paths(self.graph, source=source, target=sink, cutoff=max_length)
                    # Đóng gói List[str] của networkx thành đối tượng AttackPath
                    all_attack_paths.extend([AttackPath(nodes=p) for p in paths])
                except nx.NetworkXNoPath:
                    continue
        return all_attack_paths

    def build_prefix_trie(self, paths: List[AttackPath]) -> Dict:
        """
        Biến danh sách phẳng thành Cây tiền tố (Trie).
        """
        trie = {}
        for path in paths:
            current_node = trie
            for tool in path: # __iter__ của AttackPath sẽ lo vòng lặp này
                if tool not in current_node:
                    current_node[tool] = {}
                current_node = current_node[tool]
        return trie

    def print_paths(self, paths: List[AttackPath]):
        print(f"=== TÌM THẤY {len(paths)} KỊCH BẢN TẤN CÔNG (ATTACK PATHS) ===")
        for i, path in enumerate(paths, 1):
            print(f"Kịch bản {i:02d}: [ {path} ]") # Sử dụng __str__ của AttackPath
        print("==============================================================\n")

if __name__ == "__main__":
    from xFlowFuzz.graph.schema_parser import SchemaParser
    import json
    
    parser = SchemaParser("D:/C1-xtool-flow-fuzzer/xFlowFuzz/configs/subjects/injecagent_tools.yaml")
    schema = parser.parse()
    tdg = ToolDependencyGraph(schema)
    enumerator = PathEnumerator(tdg)
    
    attack_paths = enumerator.enumerate_all_paths(max_length=6)
    enumerator.print_paths(attack_paths)
    
    print("\n--- TEST CẤU TRÚC PREFIX TRIE ---")
    prefix_trie = enumerator.build_prefix_trie(attack_paths[:3]) # Test thử 3 đường đầu tiên
    print(json.dumps(prefix_trie, indent=2))