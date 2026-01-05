"""
通知防骚扰管理器
"""
import os
import sqlite3
import threading
from datetime import datetime, timedelta


class NotificationThrottleManager:
    """通知防骚扰管理器 - 使用SQLite记录当天已发送的邮件地址"""
    
    def __init__(self, cache_dir: str = "cache"):
        """
        初始化通知防骚扰管理器
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        self._ensure_cache_dir()
        
        # SQLite数据库文件路径
        self.db_path = os.path.join(cache_dir, "notification_throttle.db")
        self._db_lock = threading.Lock()
        
        # 初始化数据库
        self._init_database()
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _init_database(self):
        """初始化SQLite数据库和表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建通知记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_records (
                    email TEXT NOT NULL,
                    send_date TEXT NOT NULL,
                    send_time TEXT NOT NULL,
                    PRIMARY KEY (email, send_date)
                )
            ''')
            
            # 创建索引以提高查询性能
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_email_date 
                ON notification_records(email, send_date)
            ''')
            
            conn.commit()
    
    def is_sent_today(self, email: str) -> bool:
        """
        检查指定邮箱地址今天是否已经发送过通知
        Args:
            email: 邮箱地址
        Returns:
            如果今天已发送过则返回True，否则返回False
        """
        today = datetime.now().strftime('%Y-%m-%d')
        
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT COUNT(*) FROM notification_records
                        WHERE email = ? AND send_date = ?
                    ''', (email, today))
                    count = cursor.fetchone()[0]
                    return count > 0
            except Exception as e:
                print(f"[通知防骚扰] 查询发送记录失败: {e}")
                return False
    
    def mark_as_sent(self, email: str):
        """
        标记指定邮箱地址今天已发送通知
        Args:
            email: 邮箱地址
        """
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO notification_records
                        (email, send_date, send_time)
                        VALUES (?, ?, ?)
                    ''', (email, today, now))
                    conn.commit()
            except Exception as e:
                print(f"[通知防骚扰] 记录发送状态失败: {e}")

