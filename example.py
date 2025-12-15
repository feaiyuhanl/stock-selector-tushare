"""
使用示例：演示如何使用股票选择器
"""
import fix_encoding
from stock_selector import StockSelector
import config

def main():
    """主函数"""
    print("=" * 60)
    print("A股选股程序 - Tushare版本 - 使用示例")
    print("=" * 60)
    
    # 创建选股器
    selector = StockSelector(force_refresh=False)
    
    # 示例1：评估单只股票
    print("\n示例1：评估单只股票")
    print("-" * 60)
    result = selector.evaluate_stock('000001', '平安银行')
    if result:
        print(f"股票代码: {result['code']}")
        print(f"股票名称: {result['name']}")
        print(f"综合得分: {result['score']:.2f}")
        print(f"  基本面得分: {result['fundamental_score']:.2f}")
        print(f"  成交量得分: {result['volume_score']:.2f}")
        print(f"  价格得分: {result['price_score']:.2f}")
        print(f"  板块得分: {result['sector_score']:.2f}")
        print(f"  概念得分: {result['concept_score']:.2f}")
    
    # 示例2：选择TOP股票
    print("\n示例2：选择主板TOP 10股票")
    print("-" * 60)
    results = selector.select_top_stocks(
        stock_codes=None,
        top_n=10,
        board_types=['main'],
        max_workers=10
    )
    
    if not results.empty:
        print(f"\n找到 {len(results)} 只股票:")
        print(results.to_string(index=False))
        
        # 保存结果
        selector.save_results(results, 'example_results.xlsx')
        print("\n结果已保存到: example_results.xlsx")
    else:
        print("未找到符合条件的股票")
    
    # 示例3：评估指定股票列表
    print("\n示例3：评估指定股票列表")
    print("-" * 60)
    test_stocks = ['000001', '000002', '600000', '600036']
    results = selector.select_top_stocks(
        stock_codes=test_stocks,
        top_n=5,
        board_types=None,
        max_workers=5
    )
    
    if not results.empty:
        print(f"\n评估结果:")
        print(results.to_string(index=False))

if __name__ == '__main__':
    # 注意：运行前请确保已配置Tushare Token
    # 方式1：设置环境变量
    # import os
    # os.environ['TUSHARE_TOKEN'] = 'your_token_here'
    
    # 方式2：在config.py中设置
    # TUSHARE_TOKEN = 'your_token_here'
    
    try:
        main()
    except Exception as e:
        print(f"\n错误: {e}")
        print("\n请检查：")
        print("1. 是否已配置Tushare Token")
        print("2. Token是否有效")
        print("3. 网络连接是否正常")

