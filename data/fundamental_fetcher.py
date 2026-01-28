"""
基本面和财务数据获取模块
"""
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional
from .utils import get_analysis_date


class FundamentalFetcher:
    """基本面和财务数据获取器"""
    
    def __init__(self, base):
        """
        初始化基本面和财务数据获取器
        Args:
            base: FetcherBase实例，提供基础功能
        """
        self.base = base
    
    def get_stock_fundamental(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票基本面数据（带缓存）
        优化：使用日期范围参数获取数据，更稳定；保留None值，不转换为0
        """
        stock_code = str(stock_code)
        clean_code = self.base._format_stock_code(stock_code)
        
        # 检查缓存数据的更新时间，如果超过一周未更新，自动强制刷新
        force_refresh_fundamental = self.base.force_refresh
        if not force_refresh_fundamental:
            # 检查缓存数据的更新时间
            try:
                with sqlite3.connect(self.base.cache_manager.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT update_time FROM fundamental_data
                        WHERE code = ?
                        ORDER BY update_time DESC LIMIT 1
                    ''', (clean_code,))
                    result = cursor.fetchone()
                    if result and result[0]:
                        update_time_str = result[0]
                        try:
                            update_time = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            try:
                                update_time = datetime.strptime(update_time_str, '%Y-%m-%d')
                            except:
                                update_time = None
                        
                        if update_time:
                            days_diff = (datetime.now() - update_time).days
                            # 如果超过7天未更新，自动强制刷新
                            if days_diff > 7:
                                force_refresh_fundamental = True
            except Exception:
                pass  # 如果检查失败，使用默认的 force_refresh
        
        # 先尝试从缓存读取
        cached_data = self.base.cache_manager.get_fundamental(clean_code, force_refresh_fundamental)
        if cached_data is not None:
            cached_data.pop('code', None)
            cached_data.pop('update_time', None)
            return cached_data
        
        # 从网络获取
        try:
            ts_code = self.base._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            def fetch_fundamental():
                # 使用日期范围参数获取数据（参考 get_stock_kline 的实现）
                # 获取最近5个交易日的数据，确保能获取到有效数据
                analysis_date = get_analysis_date()
                end_date = analysis_date.strftime('%Y%m%d')
                start_date = (analysis_date - timedelta(days=7)).strftime('%Y%m%d')  # 往前推7天，确保覆盖5个交易日
                
                # 使用 start_date 和 end_date 参数，更稳定
                df = self.base.pro.daily_basic(ts_code=ts_code, 
                                             start_date=start_date, 
                                             end_date=end_date,
                                             fields='ts_code,trade_date,pe,pb,ps,turnover_rate')
                
                if df is not None and not df.empty:
                    # 按日期排序，取最新的数据
                    df = df.sort_values('trade_date', ascending=False)
                    latest = df.iloc[0]
                    
                    # 改进 None/NaN 值处理：保留 None，不转换为 0
                    # 区分"值为0"（可能是正常值）和"值为None/NaN"（数据缺失）
                    def safe_float_or_none(value):
                        """安全转换为float，保留None/NaN"""
                        if value is None:
                            return None
                        if isinstance(value, float) and pd.isna(value):
                            return None
                        try:
                            if isinstance(value, str):
                                value = value.replace(',', '').replace('--', '').replace('-', '')
                                if not value or value == '':
                                    return None
                            result = float(value)
                            # 如果转换后为0，但原始值不是0，可能是转换错误
                            return result
                        except (ValueError, TypeError):
                            return None
                    
                    return {
                        'pe_ratio': safe_float_or_none(latest.get('pe')),
                        'pb_ratio': safe_float_or_none(latest.get('pb')),
                        'ps_ratio': safe_float_or_none(latest.get('ps')),
                        'turnover_rate': safe_float_or_none(latest.get('turnover_rate')),
                    }
                return None
            
            result = self.base._retry_request(fetch_fundamental, max_retries=3, timeout=15)
            
            if result:
                # 保存到缓存
                if self.base.batch_mode:
                    with self.base._batch_lock:
                        self.base.fundamental_batch[clean_code] = result
                else:
                    self.base.cache_manager.save_fundamental(clean_code, result)
                return result
        except Exception as e:
            print(f"获取 {stock_code} 基本面数据失败: {e}")
        return None
    
    def get_stock_financial(self, stock_code: str, force_refresh: bool = None) -> Optional[Dict]:
        """
        获取股票财务数据（带缓存）
        """
        stock_code = str(stock_code)
        clean_code = self.base._format_stock_code(stock_code)
        
        if force_refresh is None:
            force_refresh = self.base.force_refresh
        
        # 先尝试从缓存读取
        cached_data = self.base.cache_manager.get_financial(clean_code, force_refresh)
        if cached_data is not None:
            cached_data.pop('code', None)
            cached_data.pop('update_time', None)
            return cached_data
        
        # 从网络获取
        try:
            ts_code = self.base._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            def fetch_financial():
                # 获取财务指标数据
                # 获取最近一个报告期的数据
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
                
                df = self.base.pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date,
                                                fields='ts_code,end_date,roe,roa,netprofit_margin,current_ratio')
                
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    
                    # 获取利润表数据计算增长率
                    # 改进：获取更长周期的数据，确保有足够的历史数据进行比较
                    income_df = self.base.pro.income(ts_code=ts_code,
                                                   start_date=(datetime.now() - timedelta(days=730)).strftime('%Y%m%d'),  # 2年数据
                                                   end_date=end_date,
                                                   fields='ts_code,end_date,revenue,n_income')

                    revenue_growth = 0
                    profit_growth = 0

                    if income_df is not None and not income_df.empty:
                        income_df = income_df.sort_values('end_date')
                        if len(income_df) >= 4:  # 确保至少有4个季度的数据
                            # 改进：计算最近一年（4个季度）的同比增长率
                            # 获取最近4个季度的数据
                            recent_data = income_df.tail(4)
                            if len(recent_data) >= 4:
                                # 计算最近两个完整年度的数据（如果有）
                                yearly_data = self.base._extract_yearly_data(income_df)
                                if len(yearly_data) >= 2:
                                    # 使用年度数据计算增长率更准确
                                    latest_year = yearly_data.iloc[-1]
                                    prev_year = yearly_data.iloc[-2]
                                    if prev_year['revenue'] and prev_year['revenue'] != 0:
                                        revenue_growth = ((latest_year['revenue'] - prev_year['revenue']) / prev_year['revenue']) * 100
                                    if prev_year['n_income'] and prev_year['n_income'] != 0:
                                        profit_growth = ((latest_year['n_income'] - prev_year['n_income']) / prev_year['n_income']) * 100
                                else:
                                    # 如果年度数据不足，使用季度环比增长率（近似值）
                                    # 取最近两个季度的环比数据作为近似增长率
                                    latest_revenue = recent_data.iloc[-1]['revenue']
                                    prev_revenue = recent_data.iloc[-2]['revenue']
                                    if prev_revenue and prev_revenue != 0:
                                        # 季度环比增长率需要调整为年度化
                                        quarterly_growth = ((latest_revenue - prev_revenue) / prev_revenue) * 100
                                        # 粗略年度化（乘以4，但这只是近似）
                                        revenue_growth = quarterly_growth * 4
                                    else:
                                        revenue_growth = 0

                                    latest_profit = recent_data.iloc[-1]['n_income']
                                    prev_profit = recent_data.iloc[-2]['n_income']
                                    if prev_profit and prev_profit != 0:
                                        quarterly_profit_growth = ((latest_profit - prev_profit) / prev_profit) * 100
                                        profit_growth = quarterly_profit_growth * 4
                                    else:
                                        profit_growth = 0
                        elif len(income_df) >= 2:
                            # 降级方案：至少有两个数据点时计算简单增长率
                            latest_revenue = income_df.iloc[-1]['revenue']
                            prev_revenue = income_df.iloc[-2]['revenue']
                            if prev_revenue and prev_revenue != 0:
                                revenue_growth = ((latest_revenue - prev_revenue) / prev_revenue) * 100

                            latest_profit = income_df.iloc[-1]['n_income']
                            prev_profit = income_df.iloc[-2]['n_income']
                            if prev_profit and prev_profit != 0:
                                profit_growth = ((latest_profit - prev_profit) / prev_profit) * 100
                    
                    return {
                        'roe': self.base._safe_float(latest.get('roe', 0)),
                        'roa': self.base._safe_float(latest.get('roa', 0)),
                        'revenue_growth': revenue_growth,
                        'profit_growth': profit_growth,
                    }
                return None
            
            result = self.base._retry_request(fetch_financial, max_retries=3, timeout=20)
            
            if result:
                # 保存到缓存
                if self.base.batch_mode:
                    with self.base._batch_lock:
                        self.base.financial_batch[clean_code] = result
                else:
                    self.base.cache_manager.save_financial(clean_code, result)
                return result
        except Exception as e:
            print(f"获取 {stock_code} 财务数据失败: {e}")
        return None

