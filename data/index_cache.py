"""
指数权重数据缓存模块
"""
import pandas as pd
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import config


class IndexCache:
    """指数权重数据缓存管理器"""
    
    def __init__(self, base):
        """
        初始化指数权重数据缓存管理器
        Args:
            base: CacheBase实例，提供基础功能
        """
        self.base = base
    
    def get_index_weight(
        self,
        index_code: str,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        force_refresh: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        从缓存获取指数权重数据
        Args:
            index_code: 指数代码，如 '000300.SH'
            trade_date: 交易日期，格式：YYYYMMDD，如果指定则只获取该日期的数据
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            force_refresh: 是否强制刷新
        Returns:
            DataFrame包含以下列：index_code, trade_date, con_code, weight
        """
        if force_refresh:
            return None
        
        try:
            # 标准化日期格式
            if trade_date:
                trade_date = trade_date.replace('-', '')
            if start_date:
                start_date = start_date.replace('-', '')
            if end_date:
                end_date = end_date.replace('-', '')
            
            with sqlite3.connect(self.base.db_path) as conn:
                if trade_date:
                    # 查询指定日期的数据
                    df = pd.read_sql_query('''
                        SELECT index_code, trade_date, con_code, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND trade_date = ?
                        ORDER BY weight DESC
                    ''', conn, params=(index_code, trade_date))
                elif start_date and end_date:
                    # 查询日期范围的数据
                    df = pd.read_sql_query('''
                        SELECT index_code, trade_date, con_code, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND trade_date >= ? AND trade_date <= ?
                        ORDER BY trade_date DESC, weight DESC
                    ''', conn, params=(index_code, start_date, end_date))
                elif start_date:
                    # 查询从开始日期到现在的数据
                    df = pd.read_sql_query('''
                        SELECT index_code, trade_date, con_code, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND trade_date >= ?
                        ORDER BY trade_date DESC, weight DESC
                    ''', conn, params=(index_code, start_date))
                else:
                    # 查询所有数据（不限制update_time，只查询该指数的所有权重数据）
                    df = pd.read_sql_query('''
                        SELECT index_code, trade_date, con_code, weight
                        FROM index_weight_data
                        WHERE index_code = ?
                        ORDER BY trade_date DESC, weight DESC
                    ''', conn, params=(index_code,))
                
                if not df.empty:
                    # 确保con_code是6位字符串
                    if 'con_code' in df.columns:
                        df['con_code'] = df['con_code'].apply(self.base._normalize_stock_code)
                    return df
                
        except Exception as e:
            print(f"读取指数权重缓存失败 ({index_code}): {e}")
        
        return None
    
    def has_latest_trading_day_data(self, index_code: str) -> bool:
        """
        检查是否有最新交易日的数据（用于智能跳过下载，类似K线数据的处理方式）
        Args:
            index_code: 指数代码，如 '000300.SH'
        Returns:
            是否有最新交易日数据
        """
        try:
            from data.utils import get_analysis_date
            analysis_date = get_analysis_date()
            analysis_date_str = analysis_date.strftime('%Y%m%d')
            
            with sqlite3.connect(self.base.db_path) as conn:
                cursor = conn.cursor()
                
                # 查询最新的数据日期
                cursor.execute('''
                    SELECT MAX(trade_date) FROM index_weight_data
                    WHERE index_code = ?
                ''', (index_code,))
                
                result = cursor.fetchone()
                if not result or not result[0]:
                    return False
                
                latest_date_str = result[0]
                latest_date = datetime.strptime(latest_date_str, '%Y%m%d').date()
                analysis_date_obj = analysis_date.date()
                
                # 计算日期差
                days_diff = (analysis_date_obj - latest_date).days
                
                # 如果最新数据日期在最近7天内，认为有效（考虑假期）
                if days_diff <= 7:
                    return True
                
                # 超过7天，认为缓存过期
                return False
                
        except Exception as e:
            print(f"检查指数权重数据有效性失败 ({index_code}): {e}")
            return False
    
    def save_index_weight(
        self,
        index_code: str,
        weight_data: pd.DataFrame
    ):
        """
        保存指数权重数据到缓存（带重试机制）
        Args:
            index_code: 指数代码
            weight_data: 权重数据DataFrame，必须包含 trade_date, con_code, weight 列
        """
        if weight_data is None or weight_data.empty:
            return
        
        # 使用数据库锁防止并发写入
        with self.base._db_locks['index_weight']:
            # 重试机制：最多重试3次，每次间隔递增
            max_retries = 3
            retry_delay = 0.1  # 初始延迟0.1秒
            
            for attempt in range(max_retries):
                try:
                    # 确保数据格式正确
                    weight_data = weight_data.copy()
                    
                    # 确保必要的列存在
                    required_cols = ['trade_date', 'con_code', 'weight']
                    for col in required_cols:
                        if col not in weight_data.columns:
                            print(f"保存指数权重失败：缺少必要列 {col}")
                            return
                    
                    # 标准化日期格式和股票代码
                    weight_data['trade_date'] = weight_data['trade_date'].astype(str).str.replace('-', '')
                    weight_data['con_code'] = weight_data['con_code'].apply(self.base._normalize_stock_code)
                    
                    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 使用带超时的连接
                    with self.base._get_db_connection(timeout=30.0) as conn:
                        cursor = conn.cursor()
                        
                        # 准备插入数据
                        data_to_insert = []
                        for _, row in weight_data.iterrows():
                            data_to_insert.append((
                                index_code,
                                str(row['trade_date']),
                                str(row['con_code']),
                                float(row['weight']) if pd.notna(row['weight']) else None,
                                update_time
                            ))
                        
                        # 批量插入（INSERT OR REPLACE处理重复数据）
                        cursor.executemany('''
                            INSERT OR REPLACE INTO index_weight_data
                            (index_code, trade_date, con_code, weight, update_time)
                            VALUES (?, ?, ?, ?, ?)
                        ''', data_to_insert)
                        
                        # 数据清理：只保留最近250个交易日的数据
                        retention_days = getattr(config, 'KLINE_CACHE_RETENTION_DAYS', 250)
                        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime('%Y%m%d')
                        cursor.execute('''
                            DELETE FROM index_weight_data
                            WHERE index_code = ? AND trade_date < ?
                        ''', (index_code, cutoff_date))
                        
                        conn.commit()
                    
                    # 成功保存，退出重试循环
                    return
                    
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower():
                        if attempt < max_retries - 1:
                            # 等待后重试
                            time.sleep(retry_delay * (attempt + 1))  # 递增延迟
                            continue
                        else:
                            # 最后一次重试也失败
                            print(f"保存指数权重缓存失败 ({index_code}): 数据库锁定，已重试{max_retries}次")
                            import traceback
                            traceback.print_exc()
                            return
                    else:
                        # 其他OperationalError，直接抛出
                        print(f"保存指数权重缓存失败 ({index_code}): {e}")
                        import traceback
                        traceback.print_exc()
                        return
                except Exception as e:
                    print(f"保存指数权重缓存失败 ({index_code}): {e}")
                    import traceback
                    traceback.print_exc()
                    return
    
    def get_index_weight_history(
        self,
        index_code: str,
        con_code: str,
        start_date: str = None,
        end_date: str = None,
        days: int = 60
    ) -> Optional[pd.DataFrame]:
        """
        获取历史权重数据（用于趋势分析）
        Args:
            index_code: 指数代码
            con_code: 成分股代码
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            days: 回看天数（如果未指定start_date和end_date）
        Returns:
            DataFrame包含 trade_date 和 weight 列，按日期升序排列
        """
        try:
            # 标准化股票代码
            con_code = self.base._normalize_stock_code(con_code)
            
            # 标准化日期格式
            if start_date:
                start_date = start_date.replace('-', '')
            if end_date:
                end_date = end_date.replace('-', '')
            
            with sqlite3.connect(self.base.db_path) as conn:
                if start_date and end_date:
                    # 查询指定日期范围的数据
                    df = pd.read_sql_query('''
                        SELECT trade_date, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND con_code = ? 
                        AND trade_date >= ? AND trade_date <= ?
                        ORDER BY trade_date ASC
                    ''', conn, params=(index_code, con_code, start_date, end_date))
                elif start_date:
                    # 查询从开始日期到现在的数据
                    df = pd.read_sql_query('''
                        SELECT trade_date, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND con_code = ? 
                        AND trade_date >= ?
                        ORDER BY trade_date ASC
                    ''', conn, params=(index_code, con_code, start_date))
                elif end_date:
                    # 查询最近N天到结束日期的数据
                    # 需要先计算开始日期
                    end_date_obj = datetime.strptime(end_date, '%Y%m%d')
                    start_date_obj = end_date_obj - timedelta(days=days)
                    start_date = start_date_obj.strftime('%Y%m%d')
                    df = pd.read_sql_query('''
                        SELECT trade_date, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND con_code = ? 
                        AND trade_date >= ? AND trade_date <= ?
                        ORDER BY trade_date ASC
                    ''', conn, params=(index_code, con_code, start_date, end_date))
                else:
                    # 查询最近N天的数据
                    # 注意：days是自然天数，但需要考虑到非交易日，所以扩大查询范围
                    # 通常60个自然天约等于40-45个交易日，所以查询90天确保有足够数据
                    expanded_days = int(days * 1.5)  # 扩大1.5倍，确保覆盖足够的交易日
                    cutoff_date = (datetime.now() - timedelta(days=expanded_days)).strftime('%Y%m%d')
                    df = pd.read_sql_query('''
                        SELECT trade_date, weight
                        FROM index_weight_data
                        WHERE index_code = ? AND con_code = ?
                        AND trade_date >= ?
                        ORDER BY trade_date ASC
                    ''', conn, params=(index_code, con_code, cutoff_date))
                    
                    # 如果查询到的数据点少于要求，尝试查询所有可用数据
                    if df.empty or len(df) < 3:
                        # 查询该股票的所有历史数据
                        df = pd.read_sql_query('''
                            SELECT trade_date, weight
                            FROM index_weight_data
                            WHERE index_code = ? AND con_code = ?
                            ORDER BY trade_date ASC
                        ''', conn, params=(index_code, con_code))
                
                if not df.empty:
                    return df
                
        except Exception as e:
            print(f"获取指数权重历史数据失败 ({index_code}, {con_code}): {e}")
        
        return None
    
    def calculate_index_weight_factors(
        self,
        index_code: str,
        con_code: str,
        lookback_days: int = 60
    ) -> Optional[Dict]:
        """
        计算指数权重因子（权重变化率、趋势斜率、权重绝对值等）
        Args:
            index_code: 指数代码
            con_code: 成分股代码
            lookback_days: 回看天数
        Returns:
            包含因子值的字典，如果数据不足返回None
        """
        import numpy as np
        
        try:
            # 标准化股票代码
            con_code = self.base._normalize_stock_code(con_code)
            
            # 获取历史权重数据
            history = self.get_index_weight_history(
                index_code=index_code,
                con_code=con_code,
                days=lookback_days
            )
            
            if history is None or history.empty:
                return None
            
            if len(history) < 3:
                # 数据点不足，无法计算趋势（至少需要3个数据点）
                return None
            
            # 确保数据按日期排序
            history = history.sort_values('trade_date')
            
            # 提取权重数据
            weights = history['weight'].values
            
            # 计算权重变化率
            oldest_weight = weights[0]
            latest_weight = weights[-1]
            
            if oldest_weight <= 0:
                # 如果初始权重为0或负数，无法计算变化率
                return None
            
            weight_change_rate = (latest_weight - oldest_weight) / oldest_weight
            
            # 计算趋势斜率（使用线性回归）
            try:
                from scipy import stats
                x = np.arange(len(weights))
                slope, intercept, r_value, p_value, std_err = stats.linregress(x, weights)
                trend_slope = slope
            except ImportError:
                # 如果没有scipy，使用简单的线性拟合
                n = len(weights)
                x_mean = (n - 1) / 2
                y_mean = np.mean(weights)
                numerator = sum((i - x_mean) * (weights[i] - y_mean) for i in range(n))
                denominator = sum((i - x_mean) ** 2 for i in range(n))
                trend_slope = numerator / denominator if denominator > 0 else 0
            
            # 权重绝对值（当前权重）
            weight_absolute = latest_weight
            
            return {
                'weight_change_rate': weight_change_rate,
                'trend_slope': trend_slope,
                'weight_absolute': weight_absolute,
                'oldest_weight': oldest_weight,
                'latest_weight': latest_weight,
                'data_points': len(history)
            }
            
        except Exception as e:
            print(f"[错误] 计算指数权重因子失败 ({index_code}, {con_code}): {e}")
            return None

