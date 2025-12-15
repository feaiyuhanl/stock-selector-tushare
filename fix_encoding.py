"""
编码修复工具 - 在Windows系统上设置UTF-8输出编码
在运行主程序前导入此模块即可
"""
import sys
import io
import os

def setup_utf8_encoding():
    """设置UTF-8编码输出"""
    if sys.platform == 'win32':
        # 设置环境变量
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        
        # 设置标准输出编码
        try:
            # 方法1: 重新包装stdout/stderr为UTF-8
            if hasattr(sys.stdout, 'buffer'):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'buffer'):
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception as e:
            # 如果失败，尝试GBK编码
            try:
                if hasattr(sys.stdout, 'buffer'):
                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='gbk', errors='replace')
                if hasattr(sys.stderr, 'buffer'):
                    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='gbk', errors='replace')
            except:
                pass

# 自动执行
setup_utf8_encoding()

