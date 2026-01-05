"""
Tushare Token检查工具
"""
import os
import config


def check_tushare_token():
    """
    检查Tushare Token配置（前置检查）
    Returns:
        bool: Token配置有效返回True，否则返回False
    """
    try:
        import tushare as ts
    except ImportError:
        print("\n" + "=" * 60)
        print("[错误] 未安装tushare包")
        print("=" * 60)
        print("请运行: pip install tushare")
        print("=" * 60)
        return False
    
    # 尝试从环境变量获取
    token = os.environ.get('TUSHARE_TOKEN')
    token_source = "环境变量"
    
    if not token:
        # 从config获取
        if hasattr(config, 'TUSHARE_TOKEN') and config.TUSHARE_TOKEN:
            token = config.TUSHARE_TOKEN
            token_source = "config.py"
    
    if not token:
        print("\n" + "=" * 60)
        print("[错误] 未找到Token配置")
        print("=" * 60)
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
        print("=" * 60)
        return False
    
    # 设置Token并测试有效性
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 测试连接
        test_date = '20241215'
        df = pro.trade_cal(exchange='SSE', start_date=test_date, end_date=test_date)
        
        if df is None or df.empty:
            print("\n" + "=" * 60)
            print("[错误] Token可能无效，返回空结果")
            print("=" * 60)
            print("\n建议：")
            print("1. 登录 https://tushare.pro/ 检查Token和积分")
            print("2. 重新复制最新的Token")
            print("=" * 60)
            return False
        
        # Token有效，继续执行
        return True
        
    except Exception as e:
        error_msg = str(e)
        print("\n" + "=" * 60)
        print(f"[错误] Token配置验证失败: {e}")
        print("=" * 60)
        
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
        print("=" * 60)
        return False

