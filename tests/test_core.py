import unittest
from xFlowFuzz.graph.path_enum import AttackPath
from xFlowFuzz.fuzz.coverage import CoverageManager
from xFlowFuzz.fuzz.scheduler import Scheduler

class TestXFlowFuzzCore(unittest.TestCase):
    def setUp(self):
        # Thiết lập dữ liệu giả lập (Mock Data)
        self.p1 = AttackPath(["read_email", "send_email"])
        self.p2 = AttackPath(["fetch_web_page", "summarize", "write_local_file"])
        self.p3 = AttackPath(["read_document", "translate", "summarize", "send_email"])
        self.all_paths = [self.p1, self.p2, self.p3]

    def test_coverage_manager(self):
        """Kiểm tra công thức tính Độ phủ (Coverage)"""
        manager = CoverageManager()
        manager.register_paths(self.all_paths)
        
        # Ban đầu độ phủ phải bằng 0%
        self.assertEqual(manager.coverage(), 0.0)
        
        # Đánh thủng 1 đường
        is_new = manager.mark_realized(self.p1)
        self.assertTrue(is_new)
        self.assertAlmostEqual(manager.coverage(), 33.33, places=2)
        
        # Đánh thủng lại đường cũ (Không được tính là mới)
        is_new = manager.mark_realized(self.p1)
        self.assertFalse(is_new)
        self.assertAlmostEqual(manager.coverage(), 33.33, places=2)

    def test_scheduler_priority(self):
        """Kiểm tra Bộ điều phối (Scheduler) ưu tiên đường ngắn và xoay vòng"""
        scheduler = Scheduler(self.all_paths)
        
        # Đường ngắn nhất p1 (độ dài 2) phải được bốc đầu tiên
        first_pick = scheduler.next_path()
        self.assertEqual(first_pick.nodes, self.p1.nodes)
        
        # Đường dài tiếp theo p2 (độ dài 3) phải được bốc thứ hai
        second_pick = scheduler.next_path()
        self.assertEqual(second_pick.nodes, self.p2.nodes)
        
        # Khi p1 bị đánh thủng, nó phải bị loại khỏi hàng đợi
        scheduler.mark_realized(self.p1)
        # Số lượng còn lại phải là 2 (vì có 3 đường, 1 đường bị xóa)
        self.assertEqual(scheduler.remaining(), 2)

if __name__ == "__main__":
    unittest.main()