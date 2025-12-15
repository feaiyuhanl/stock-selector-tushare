"""
Tushare Token 配置测试脚本
用于验证Token是否正确配置
"""
# 修复Windows中文编码问题
import fix_encoding

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tushare as ts
except ImportError:
    print("[错误] 未安装tushare包")
    print("请运行: pip install tushare")
    sys.exit(1)

try:
    import config
except ImportError:
    print("[警告] 无法导入config模块")
    config = None

def test_token():
    """测试Token配置"""
    print("=" * 60)
    print("Tushare Token 配置测试")
    print("=" * 60)
    
    # 尝试从环境变量获取
    token = os.environ.get('TUSHARE_TOKEN')
    token_source = "环境变量"
    
    if not token:
        # 从config获取
        if config and hasattr(config, 'TUSHARE_TOKEN'):
            token = config.TUSHARE_TOKEN
            token_source = "config.py"
    
    if not token:
        print("\n[错误] 未找到Token配置")
        print("\n请使用以下方式之一配置Token：")
        print("\n方式1：设置环境变量（推荐）")
        print("  Windows PowerShell:")
        print("    $env:TUSHARE_TOKEN='your_token_here'")
        print("  Windows CMD:")
        print("    set TUSHARE_TOKEN=your_token_here")
        print("  Linux/Mac:")
        print("    export TUSHARE_TOKEN='your_token_here'")
        print("\n方式2：在config.py中设置")
        print("    TUSHARE_TOKEN = 'your_token_here'")
        print("\n方式3：在代码中设置")
        print("    import tushare as ts")
        print("    ts.set_token('your_token_here')")
        print("\n获取Token请访问: https://tushare.pro/register")
        return False
    
    print(f"\n[成功] 找到Token配置（来源：{token_source}）")
    print(f"Token前10位: {token[:10]}...")
    
    # 设置Token
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        print("[成功] Token设置成功")
    except Exception as e:
        print(f"[错误] Token设置失败: {e}")
        return False
    
    # 测试连接
    print("\n正在测试Token有效性...")
    try:
        # 使用一个固定的日期测试
        test_date = '20241215'
        df = pro.trade_cal(exchange='SSE', start_date=test_date, end_date=test_date)
        
        if df is not None and not df.empty:
            print("[成功] Token有效！连接成功！")
            print(f"\n测试结果：")
            print(f"  测试日期: {test_date}")
            is_open = df.iloc[0]['is_open']
            print(f"  是否交易日: {'是' if is_open == 1 else '否'}")
            
            # 尝试获取股票列表（简单测试）
            print("\n正在测试数据获取功能...")
            try:
                stock_df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name')
                if stock_df is not None and not stock_df.empty:
                    print(f"[成功] 数据获取测试成功！")
                    print(f"  成功获取 {len(stock_df)} 只股票信息")
                    print(f"  示例股票: {stock_df.iloc[0]['name']} ({stock_df.iloc[0]['symbol']})")
                else:
                    print("[警告] 数据获取返回空结果，可能是积分不足")
            except Exception as e:
                error_msg = str(e)
                if "权限" in error_msg or "积分" in error_msg:
                    print(f"[警告] {error_msg}")
                    print("  提示：Token有效，但可能积分不足，请登录tushare官网查看积分余额")
                else:
                    print(f"[警告] 数据获取测试失败: {e}")
            
            print("\n" + "=" * 60)
            print("[成功] Token配置验证通过！")
            print("=" * 60)
            return True
        else:
            print("[警告] Token可能无效，返回空结果")
            return False
            
    except Exception as e:
        error_msg = str(e)
        print(f"[错误] Token测试失败: {e}")
        
        if "权限" in error_msg or "积分" in error_msg or "token" in error_msg.lower():
            print("\n可能的原因：")
            print("1. Token无效或已过期")
            print("2. 积分不足")
            print("3. 权限不足")
            print("\n建议：")
            print("1. 登录 https://tushare.pro/ 检查Token和积分")
            print("2. 重新复制最新的Token")
            print("3. 如果积分不足，需要充值或等待积分恢复")
        else:
            print("\n可能的原因：")
            print("1. 网络连接问题")
            print("2. Tushare服务异常")
            print("3. Token格式错误")
        
        return False

if __name__ == '__main__':
    success = test_token()
    sys.exit(0 if success else 1)

