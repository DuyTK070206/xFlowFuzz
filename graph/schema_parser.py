import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class ParsedTool:
    """
    Class đại diện cho một công cụ đã được bóc tách dữ liệu từ schema.
    """
    name: str
    type: str  # 'source', 'transform', hoặc 'sink'
    description: str
    inputs: Dict[str, str] = field(default_factory=dict)  # {tên_tham_số: kiểu_dữ_liệu}
    required_inputs: List[str] = field(default_factory=list)
    output_type: str = "string"
    output_description: str = ""
    # [NEW] Thêm trường effects để hỗ trợ khai báo tác động (dùng cho Taint Policy)
    effects: List[str] = field(default_factory=list)

    def is_source(self) -> bool:
        return self.type.lower() == "source"

    def is_transform(self) -> bool:
        return self.type.lower() == "transform"

    def is_sink(self) -> bool:
        return self.type.lower() == "sink"


@dataclass
class SubjectSchema:
    """
    Class chứa toàn bộ danh sách công cụ và metadata của một Subject.
    """
    subject_name: str
    version: str
    tools: List[ParsedTool] = field(default_factory=list)

    def get_tool_by_name(self, name: str) -> Optional[ParsedTool]:
        """Tìm công cụ theo tên."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_sources(self) -> List[ParsedTool]:
        """Lấy danh sách các công cụ thuộc nhóm Source."""
        return [t for t in self.tools if t.is_source()]

    def get_sinks(self) -> List[ParsedTool]:
        """Lấy danh sách các công cụ thuộc nhóm Sink."""
        return [t for t in self.tools if t.is_sink()]


class SchemaParser:
    """
    Bộ đọc và bóc tách dữ liệu từ file YAML cấu hình công cụ.
    """

    def __init__(self, schema_path: str):
        self.schema_path = Path(schema_path)

    def parse(self) -> SubjectSchema:
        """
        Đọc file YAML và bóc tách thành đối tượng SubjectSchema.
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file schema tại: {self.schema_path}")

        with open(self.schema_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        subject_name = data.get("subject_name", "unknown_subject")
        version = data.get("version", "1.0")

        parsed_tools: List[ParsedTool] = []
        raw_tools = data.get("tools", [])

        for tool_data in raw_tools:
            tool = self._parse_single_tool(tool_data)
            parsed_tools.append(tool)

        return SubjectSchema(
            subject_name=subject_name,
            version=version,
            tools=parsed_tools
        )

    def _parse_single_tool(self, tool_data: Dict[str, Any]) -> ParsedTool:
        """
        Bóc tách chi tiết từng công cụ đơn lẻ.
        """
        name = tool_data.get("name", "")
        tool_type = tool_data.get("type", "transform")
        description = tool_data.get("description", "")

        # Bóc tách Parameters (Inputs)
        params_data = tool_data.get("parameters", {})
        properties = params_data.get("properties", {})
        required_inputs = params_data.get("required", [])

        inputs = {}
        for param_name, param_info in properties.items():
            # Mặc định là 'string' nếu không khai báo kiểu
            inputs[param_name] = param_info.get("type", "string")

        # Bóc tách Returns (Output)
        returns_data = tool_data.get("returns", {})
        output_type = returns_data.get("type", "string")
        output_description = returns_data.get("description", "")
        
        # [NEW] Bóc tách danh sách effects
        effects = tool_data.get("effects", [])

        return ParsedTool(
            name=name,
            type=tool_type,
            description=description,
            inputs=inputs,
            required_inputs=required_inputs,
            output_type=output_type,
            output_description=output_description,
            effects=effects
        )


# =========================================================================
# KỊCH BẢN KIỂM THỬ ĐỘC LẬP (Self-Test Block)
# =========================================================================
if __name__ == "__main__":
    sample_path = "D:/C1-xtool-flow-fuzzer/xFlowFuzz/configs/subjects/injecagent_tools.yaml"

    try:
        parser = SchemaParser(sample_path)
        schema = parser.parse()

        print(f"=== ĐÃ PARSE THÀNH CÔNG SUBJECT: {schema.subject_name} (v{schema.version}) ===")
        print(f"Tổng số công cụ: {len(schema.tools)}")
        print(f"Số lượng Sources: {len(schema.get_sources())}")
        print(f"Số lượng Sinks  : {len(schema.get_sinks())}\n")

        print("--- Chi tiết danh sách Tools ---")
        for tool in schema.tools:
            inputs_str = ", ".join([f"{k}: {v}" for k, v in tool.inputs.items()])
            print(f"[{tool.type.upper():<9}] {tool.name}")
            print(f"            Inputs : ({inputs_str})")
            print(f"            Output : {tool.output_type}")
            if tool.effects:
                print(f"            Effects: {tool.effects}")
            print()

    except Exception as e:
        print(f"Lỗi khi chạy schema_parser: {e}")