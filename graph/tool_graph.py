import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Tuple
from pathlib import Path

# Import class SchemaParser từ file bạn vừa viết
from xFlowFuzz.graph.schema_parser import SchemaParser, SubjectSchema, ParsedTool

class ToolDependencyGraph:
    """
    Xây dựng và quản lý Đồ thị Phụ thuộc Công cụ tĩnh (Static TDG).
    """
    def __init__(self, schema: SubjectSchema):
        self.schema = schema
        self.graph = nx.DiGraph() # Khởi tạo đồ thị có hướng (Directed Graph)
        
        self._build_nodes()
        self._build_edges()

    def _build_nodes(self):
        """Thêm tất cả các công cụ làm các Đỉnh (Nodes) trên đồ thị."""
        for tool in self.schema.tools:
            self.graph.add_node(
                tool.name, 
                type=tool.type, 
                description=tool.description
            )

    def _build_edges(self):
        """
        Nối các Cạnh (Edges) dựa trên sự tương thích kiểu dữ liệu (Type Compatibility).
        O(|T|^2) - Duyệt qua tất cả các cặp công cụ.
        """
        for tool_a in self.schema.tools:
            for tool_b in self.schema.tools:
                # Không tự nối vòng lặp vào chính nó
                if tool_a.name == tool_b.name:
                    continue
                
                # Bỏ qua nếu Tool A là Sink (không xuất dữ liệu đi đâu nữa)
                if tool_a.is_sink():
                    continue
                    
                # Bỏ qua nếu Tool B là Source (không nhận dữ liệu từ tool khác)
                if tool_b.is_source():
                    continue

                # Kiểm tra tính tương thích: 
                # Output của Tool A có khớp với bất kỳ Input nào của Tool B không?
                target_input_types = list(tool_b.inputs.values())
                
                if tool_a.output_type in target_input_types:
                    # Nếu tương thích -> Thêm một cạnh hướng từ A sang B
                    self.graph.add_edge(tool_a.name, tool_b.name)

    def print_summary(self):
        """In báo cáo thống kê của đồ thị tĩnh."""
        print(f"=== ĐỒ THỊ TĨNH (TDG): {self.schema.subject_name} ===")
        print(f"• Số lượng đỉnh (Tools): {self.graph.number_of_nodes()}")
        print(f"• Số lượng cạnh (Edges): {self.graph.number_of_edges()}")
        print("• Danh sách các liên kết dữ liệu khả thi:")
        for source, target in self.graph.edges():
            print(f"   [Flow] {source} ---> {target}")
        print("===================================================\n")

    def visualize(self, output_path: str = "results/tdg/static_map.png"):
        """Vẽ đồ thị phân tầng (Layered Layout) từ Trái sang Phải."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(14, 8)) # Tăng chiều ngang cho khung hình
        
        # 1. PHÂN TẦNG: Gán thuộc tính 'layer' (cột) cho từng node
        for node in self.graph.nodes():
            node_type = self.graph.nodes[node]['type']
            if node_type == 'source':
                self.graph.nodes[node]['layer'] = 0     # Cột 1 (Trái)
            elif node_type == 'transform':
                self.graph.nodes[node]['layer'] = 1     # Cột 2 (Giữa)
            elif node_type == 'sink':
                self.graph.nodes[node]['layer'] = 2     # Cột 3 (Phải)
                
        # 2. XẾP VỊ TRÍ: Dùng multipartite_layout xếp các node theo các layer vừa tạo
        # align='vertical' nghĩa là các node trong cùng 1 cột sẽ xếp dọc xuống
        pos = nx.multipartite_layout(self.graph, subset_key='layer', align='vertical')
        
        # 3. TÔ MÀU
        color_map = []
        for node in self.graph.nodes():
            layer = self.graph.nodes[node]['layer']
            if layer == 0: color_map.append('lightgreen')
            elif layer == 2: color_map.append('lightcoral')
            else: color_map.append('lightblue')
                
        # 4. VẼ CÁC THÀNH PHẦN
        nx.draw_networkx_nodes(self.graph, pos, node_color=color_map, node_size=3000, edgecolors='black')
        
        nx.draw_networkx_edges(
            self.graph, 
            pos, 
            arrows=True, 
            arrowstyle='-|>', 
            arrowsize=25, 
            node_size=3000, 
            edge_color='gray', 
            width=1.5,
            connectionstyle="arc3,rad=0.1" # Bẻ cong nhẹ các mũi tên để không bị đè lên nhau
        )
        
        # Vẽ Text với hộp nền trắng mờ để chữ không bị lấp bởi các đường kẻ
        nx.draw_networkx_labels(
            self.graph, 
            pos, 
            font_size=9, 
            font_weight="bold",
            bbox=dict(facecolor="white", alpha=0.6, edgecolor="none", pad=1)
        )
        
        plt.title(f"Static Tool Dependency Graph - {self.schema.subject_name}", fontsize=16, fontweight='bold')
        plt.axis('off')
        plt.tight_layout()
        
        plt.savefig(output_path, dpi=300)
        print(f"[*] Đã xuất bản đồ trực quan tại: {output_path}")


# =========================================================================
# KỊCH BẢN KIỂM THỬ ĐỘC LẬP (Self-Test Block)
# =========================================================================
if __name__ == "__main__":
    # 1. Gọi Parser để lấy dữ liệu (Bước vừa làm xong)
    schema_path = "D:/C1-xtool-flow-fuzzer/xFlowFuzz/configs/subjects/injecagent_tools.yaml"
    parser = SchemaParser(schema_path)
    schema = parser.parse()
    
    # 2. Xây dựng đồ thị (TDG)
    tdg = ToolDependencyGraph(schema)
    
    # 3. In kết quả và vẽ hình
    tdg.print_summary()
    tdg.visualize("results/tdg/injecagent_static_map.png")