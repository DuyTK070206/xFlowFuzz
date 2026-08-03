from typing import List, Set, Tuple, Iterable, Union
from xFlowFuzz.graph.path_enum import AttackPath

# Sử dụng Tuple để biểu diễn Path bên trong Manager nhằm đảm bảo tính Hashable (có thể dùng trong Set)
PathTuple = Tuple[str, ...]

class CoverageManager:
    """
    Bộ Quản lý Độ phủ (Path-Sensitive Coverage Manager).
    Chịu trách nhiệm theo dõi tiến độ của chiến dịch Fuzzing.
    Hoàn toàn độc lập với Runtime và Taint Engine.
    """
    def __init__(self):
        self._all_paths: Set[PathTuple] = set()
        self._visited_paths: Set[PathTuple] = set()     # Những đường Fuzzer đã thử nghiệm (Attempted)
        self._realized_paths: Set[PathTuple] = set()    # Những đường đã chọc thủng thành công (Taint reached Sink)
        self._new_realized_paths: Set[PathTuple] = set()# Hàng đợi các đường mới chọc thủng (Dành cho Scheduler)

    def _to_tuple(self, path: Union[AttackPath, Iterable[str]]) -> PathTuple:
        """Hàm nội bộ: Chuẩn hóa mọi định dạng path về Tuple[str, ...]"""
        if isinstance(path, AttackPath):
            return tuple(path.nodes)
        return tuple(path)

    def register_paths(self, paths: List[AttackPath]) -> None:
        """
        Nạp toàn bộ không gian tấn công (Total Search Space) vào hệ thống.
        Được gọi 1 lần duy nhất lúc khởi động Fuzzer.
        """
        for p in paths:
            self._all_paths.add(self._to_tuple(p))

    def mark_visited(self, path: Union[AttackPath, Iterable[str]]) -> None:
        """Ghi nhận một đường đã được Fuzzer bốc ra để thử (Dù thành công hay thất bại)."""
        self._visited_paths.add(self._to_tuple(path))

    def mark_realized(self, path: Union[AttackPath, Iterable[str]]) -> bool:
        """
        Ghi nhận một đường đã bị chọc thủng thành công (Được xác nhận bởi Taint Engine).
        Trả về True nếu đây là một phát hiện mới (Marginal Gain).
        """
        p_tuple = self._to_tuple(path)
        
        # Chỉ ghi nhận nếu đường này hợp lệ (nằm trong không gian tấn công)
        if p_tuple in self._all_paths and p_tuple not in self._realized_paths:
            self._realized_paths.add(p_tuple)
            self._new_realized_paths.add(p_tuple)
            return True
            
        return False

    def coverage(self) -> float:
        """
        Tính toán công thức Coverage theo bài báo:
        Coverage = Realized Paths / All Attack Paths
        """
        if not self._all_paths:
            return 0.0
        return (len(self._realized_paths) / len(self._all_paths)) * 100.0

    def new_paths(self) -> List[PathTuple]:
        """
        Lấy ra danh sách các đường VỪA ĐƯỢC CHỌC THỦNG và dọn dẹp hàng đợi.
        Scheduler sẽ gọi hàm này để cập nhật trọng số.
        """
        newly_realized = list(self._new_realized_paths)
        self._new_realized_paths.clear()
        return newly_realized

    def is_realized(self, path: Union[AttackPath, Iterable[str]]) -> bool:
        """Kiểm tra xem một đường cụ thể đã bị chọc thủng chưa."""
        return self._to_tuple(path) in self._realized_paths

    def summary(self) -> str:
        """Xuất báo cáo thống kê tiến độ."""
        total = len(self._all_paths)
        visited = len(self._visited_paths)
        realized = len(self._realized_paths)
        cov_percent = self.coverage()
        
        return (
            f"=== BÁO CÁO ĐỘ PHỦ (COVERAGE SUMMARY) ===\n"
            f"- Không gian tấn công (Total Paths) : {total}\n"
            f"- Đã thử nghiệm (Visited Paths)     : {visited}\n"
            f"- Chọc thủng (Realized Paths)       : {realized}\n"
            f"- Tỉ lệ bao phủ (Coverage)          : {cov_percent:.2f}%\n"
            f"========================================="
        )

# =========================================================================
# KỊCH BẢN KIỂM THỬ ĐỘC LẬP (Self-Test Block)
# =========================================================================
if __name__ == "__main__":
    # Test thử độc lập module này
    from xFlowFuzz.graph.path_enum import AttackPath
    
    # 1. Giả lập 3 đường tấn công
    p1 = AttackPath(["read_email", "summarize", "send_email"])
    p2 = AttackPath(["fetch_web", "translate", "write_file"])
    p3 = AttackPath(["read_doc", "send_email"])
    
    manager = CoverageManager()
    
    # 2. Đăng ký vào hệ thống
    manager.register_paths([p1, p2, p3])
    print(manager.summary())
    
    # 3. Giả lập Fuzzer đánh thủng p1
    print("\n[+] Đánh thủng p1...")
    is_new = manager.mark_realized(p1)
    print(f"Có phải phát hiện mới không? {is_new}")
    
    # 4. Giả lập Fuzzer đánh p1 lần nữa (Đi lại đường cũ)
    print("\n[+] Đánh thủng p1 (Lần 2)...")
    is_new = manager.mark_realized(p1)
    print(f"Có phải phát hiện mới không? {is_new}")
    
    print(f"\n{manager.summary()}")