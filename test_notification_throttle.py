"""
单元测试：验证通知防骚扰功能

测试覆盖：
1. NotificationThrottleManager 类的基本功能：
   - 数据库初始化
   - 邮箱发送状态检查（is_sent_today）
   - 标记邮箱为已发送（mark_as_sent）
   - 多个邮箱地址管理
   - 过期记录清理
   
2. is_trading_day_after_15_00() 函数：
   - 时间判断（15:00之前/之后）
   - 交易日判断（使用交易日历）
   - 缓存命中/未命中场景
   - API调用场景
   - 异常回退逻辑

3. 集成测试：
   - 完整的防骚扰工作流程

运行方式：
    python test_notification_throttle.py
"""
import unittest
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import pandas as pd

# 导入要测试的模块
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_selector import NotificationThrottleManager, is_trading_day_after_15_00


class TestNotificationThrottleManager(unittest.TestCase):
    """测试 NotificationThrottleManager 类"""
    
    def setUp(self):
        """测试前准备：创建临时缓存目录"""
        self.test_cache_dir = tempfile.mkdtemp(prefix="test_throttle_")
        self.manager = NotificationThrottleManager(cache_dir=self.test_cache_dir)
    
    def tearDown(self):
        """测试后清理：删除临时缓存目录"""
        # 确保数据库连接关闭（Windows上SQLite文件可能需要时间释放）
        if hasattr(self, 'manager') and hasattr(self.manager, '_db_lock'):
            time.sleep(0.1)  # 短暂等待，确保连接释放
        
        if os.path.exists(self.test_cache_dir):
            # Windows上可能需要重试删除
            max_retries = 3
            for i in range(max_retries):
                try:
                    # 先尝试删除数据库文件
                    db_path = os.path.join(self.test_cache_dir, "notification_throttle.db")
                    if os.path.exists(db_path):
                        os.remove(db_path)
                    # 然后删除目录
                    os.rmdir(self.test_cache_dir)
                    break
                except (PermissionError, OSError):
                    if i < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    else:
                        # 最后一次尝试使用shutil.rmtree（忽略错误）
                        try:
                            shutil.rmtree(self.test_cache_dir, ignore_errors=True)
                        except:
                            pass
    
    def test_init_database(self):
        """测试数据库初始化"""
        # 检查数据库文件是否存在
        db_path = os.path.join(self.test_cache_dir, "notification_throttle.db")
        self.assertTrue(os.path.exists(db_path), "数据库文件应该被创建")
        
        # 检查表是否存在
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='notification_records'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result, "notification_records 表应该存在")
    
    def test_is_sent_today_initial_state(self):
        """测试初始状态下邮箱未发送"""
        email = "test@example.com"
        result = self.manager.is_sent_today(email)
        self.assertFalse(result, "初始状态下邮箱应该未发送")
    
    def test_mark_as_sent_and_check(self):
        """测试标记为已发送并检查"""
        email = "test@example.com"
        
        # 标记为已发送
        self.manager.mark_as_sent(email)
        
        # 检查是否已发送
        result = self.manager.is_sent_today(email)
        self.assertTrue(result, "标记后应该返回已发送")
    
    def test_multiple_emails(self):
        """测试多个邮箱地址"""
        email1 = "test1@example.com"
        email2 = "test2@example.com"
        
        # 只标记第一个邮箱
        self.manager.mark_as_sent(email1)
        
        # 检查两个邮箱
        self.assertTrue(self.manager.is_sent_today(email1), "email1 应该已发送")
        self.assertFalse(self.manager.is_sent_today(email2), "email2 应该未发送")
    
    def test_same_email_multiple_mark(self):
        """测试同一邮箱多次标记（应该只记录一次）"""
        email = "test@example.com"
        
        # 多次标记
        self.manager.mark_as_sent(email)
        self.manager.mark_as_sent(email)
        self.manager.mark_as_sent(email)
        
        # 应该只记录一次
        result = self.manager.is_sent_today(email)
        self.assertTrue(result, "多次标记后应该仍然显示已发送")
        
        # 验证数据库中的记录数
        db_path = os.path.join(self.test_cache_dir, "notification_throttle.db")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*) FROM notification_records
                WHERE email = ? AND send_date = ?
            """, (email, today))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1, "同一邮箱同一天应该只有一条记录")
    
    def test_cleanup_old_records(self):
        """测试清理过期记录"""
        email = "test@example.com"
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        
        # 手动插入一条过期记录
        db_path = os.path.join(self.test_cache_dir, "notification_throttle.db")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notification_records (email, send_date, send_time)
                VALUES (?, ?, ?)
            """, (email, old_date, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        
        # 执行清理（保留7天）
        self.manager.cleanup_old_records(days=7)
        
        # 验证记录已被删除
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM notification_records
                WHERE email = ? AND send_date = ?
            """, (email, old_date))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0, "过期记录应该被清理")


class TestTradingDayAfter1500(unittest.TestCase):
    """测试 is_trading_day_after_15_00() 函数"""
    
    @patch('stock_selector.datetime')
    def test_not_after_1500(self, mock_datetime):
        """测试15:00之前的时间"""
        # Mock当前时间为14:00，周一
        mock_now = datetime(2025, 1, 6, 14, 0, 0)  # 2025-01-06是周一
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 和交易日历
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = True  # 是交易日
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        self.assertFalse(result, "14:00 应该返回 False")
    
    @patch('stock_selector.datetime')
    def test_after_1500_trading_day(self, mock_datetime):
        """测试15:00之后且是交易日"""
        # Mock当前时间为16:00，周一
        mock_now = datetime(2025, 1, 6, 16, 0, 0)  # 2025-01-06是周一
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 和交易日历
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = True  # 是交易日
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        self.assertTrue(result, "16:00且是交易日应该返回 True")
    
    @patch('stock_selector.datetime')
    def test_after_1500_non_trading_day(self, mock_datetime):
        """测试15:00之后但不是交易日"""
        # Mock当前时间为16:00，周一
        mock_now = datetime(2025, 1, 6, 16, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 和交易日历
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = False  # 不是交易日（比如节假日）
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        self.assertFalse(result, "16:00但不是交易日应该返回 False")
    
    @patch('stock_selector.datetime')
    def test_weekend_fallback(self, mock_datetime):
        """测试周末回退逻辑"""
        # Mock当前时间为周日16:00
        mock_now = datetime(2025, 1, 5, 16, 0, 0)  # 2025-01-05是周日
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 获取交易日历失败
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = None  # 缓存中没有
        mock_data_fetcher.get_trade_calendar.return_value = None  # API获取失败
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        self.assertFalse(result, "周末应该返回 False")
    
    @patch('stock_selector.datetime')
    def test_cache_hit(self, mock_datetime):
        """测试缓存命中情况"""
        # Mock当前时间为16:00，周一
        mock_now = datetime(2025, 1, 6, 16, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 缓存中有数据
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = True  # 缓存中有，是交易日
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        
        # 验证调用了缓存方法
        mock_cache_manager.is_trading_day.assert_called_once_with('20250106')
        # 不应该调用 get_trade_calendar
        mock_data_fetcher.get_trade_calendar.assert_not_called()
        self.assertTrue(result)
    
    @patch('stock_selector.datetime')
    def test_cache_miss_api_call(self, mock_datetime):
        """测试缓存未命中时调用API"""
        # Mock当前时间为16:00，周一
        mock_now = datetime(2025, 1, 6, 16, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        mock_datetime.strftime = datetime.strftime
        
        # Mock DataFetcher 缓存中没有，需要调用API
        mock_data_fetcher = Mock()
        mock_cache_manager = Mock()
        mock_data_fetcher.cache_manager = mock_cache_manager
        mock_cache_manager.is_trading_day.return_value = None  # 缓存中没有
        
        # Mock API返回的交易日历
        mock_trade_cal = pd.DataFrame({
            'cal_date': ['20250106'],
            'is_open': [1]  # 是交易日
        })
        mock_data_fetcher.get_trade_calendar.return_value = mock_trade_cal
        
        result = is_trading_day_after_15_00(mock_data_fetcher)
        
        # 验证调用了API
        mock_cache_manager.is_trading_day.assert_called_once_with('20250106')
        mock_data_fetcher.get_trade_calendar.assert_called_once()
        self.assertTrue(result)


class TestIntegrationThrottle(unittest.TestCase):
    """集成测试：测试完整的防骚扰流程"""
    
    def setUp(self):
        """测试前准备"""
        self.test_cache_dir = tempfile.mkdtemp(prefix="test_integration_")
        self.manager = NotificationThrottleManager(cache_dir=self.test_cache_dir)
    
    def tearDown(self):
        """测试后清理"""
        # 确保数据库连接关闭（Windows上SQLite文件可能需要时间释放）
        if hasattr(self, 'manager') and hasattr(self.manager, '_db_lock'):
            time.sleep(0.1)  # 短暂等待，确保连接释放
        
        if os.path.exists(self.test_cache_dir):
            # Windows上可能需要重试删除
            max_retries = 3
            for i in range(max_retries):
                try:
                    # 先尝试删除数据库文件
                    db_path = os.path.join(self.test_cache_dir, "notification_throttle.db")
                    if os.path.exists(db_path):
                        os.remove(db_path)
                    # 然后删除目录
                    os.rmdir(self.test_cache_dir)
                    break
                except (PermissionError, OSError):
                    if i < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    else:
                        # 最后一次尝试使用shutil.rmtree（忽略错误）
                        try:
                            shutil.rmtree(self.test_cache_dir, ignore_errors=True)
                        except:
                            pass
    
    @patch('stock_selector.is_trading_day_after_15_00')
    def test_throttle_workflow(self, mock_trading_day_check):
        """测试完整的防骚扰工作流程"""
        # 模拟是交易日15:00之后
        mock_trading_day_check.return_value = True
        
        email = "test@example.com"
        
        # 第一次检查：应该未发送
        self.assertFalse(self.manager.is_sent_today(email), "第一次应该未发送")
        
        # 标记为已发送
        self.manager.mark_as_sent(email)
        
        # 第二次检查：应该已发送
        self.assertTrue(self.manager.is_sent_today(email), "标记后应该已发送")
        
        # 模拟另一个邮箱
        email2 = "test2@example.com"
        self.assertFalse(self.manager.is_sent_today(email2), "其他邮箱应该未发送")


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试用例
    suite.addTests(loader.loadTestsFromTestCase(TestNotificationThrottleManager))
    suite.addTests(loader.loadTestsFromTestCase(TestTradingDayAfter1500))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationThrottle))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回测试结果
    return result.wasSuccessful()


if __name__ == '__main__':
    print("=" * 60)
    print("通知防骚扰功能单元测试")
    print("=" * 60)
    print()
    
    success = run_tests()
    
    print()
    print("=" * 60)
    if success:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败，请检查输出")
    print("=" * 60)
    
    sys.exit(0 if success else 1)

