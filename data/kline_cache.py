"""
K线数据缓存模块
"""
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from .utils import AFTERNOON_END, MORNING_START, TRADING_HOURS
import config


class KlineCache:
    """K线数据缓存管理器"""
    
    def __init__(self, base):
        """
        初始化K线数据缓存管理器
        Args:
            base: CacheBase实例，提供基础功能
        """
        self.base = base
    
    def get_kline(self, symbol: str, cache_type: str = 'stock',
                  period: str = 'daily', force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取K线数据（智能检查最新交易日数据）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            force_refresh: 是否强制刷新
        Returns:
            K线数据DataFrame
        """
        if force_refresh:
            return None

        try:
            with sqlite3.connect(self.base.db_path) as conn:
                # 查询K线数据（移除update_time限制，只要有数据就返回）
                df = pd.read_sql_query('''
                    SELECT symbol, date, open, high, low, close, volume, amount
                    FROM kline_data
                    WHERE symbol = ? AND cache_type = ? AND period = ?
                    ORDER BY date
                ''', conn, params=(symbol, cache_type, period))

                if not df.empty:
                    # 只要有数据就返回，不检查日期（日期检查在has_latest_trading_day_data中进行）
                    return df

        except Exception as e:
            print(f"读取K线缓存失败 ({symbol}): {e}")

        return None
    
    def has_latest_trading_day_data(self, symbol: str, cache_type: str = 'stock',
                                    period: str = 'daily') -> bool:
        """
        检查是否有最新交易日的数据（用于智能跳过下载）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
        Returns:
            是否有最新交易日数据
        """
        try:
            with sqlite3.connect(self.base.db_path) as conn:
                cursor = conn.cursor()

                # 查询最新的数据日期（移除update_time限制，只检查数据日期）
                cursor.execute('''
                    SELECT MAX(date) FROM kline_data
                    WHERE symbol = ? AND cache_type = ? AND period = ?
                ''', (symbol, cache_type, period))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return False

                latest_date_str = result[0]
                latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
                today = datetime.now().date()
                current_time = datetime.now().time()
                weekday = datetime.now().weekday()

                # 判断是否应该使用昨天的数据
                # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
                use_yesterday = False
                if weekday >= 5:  # 周末
                    use_yesterday = True
                elif current_time < MORNING_START:  # 还没开盘
                    use_yesterday = True
                elif (MORNING_START <= current_time <= TRADING_HOURS['morning_end']) or \
                     (TRADING_HOURS.get('afternoon_start', 13) <= current_time <= AFTERNOON_END):  # 交易中
                    use_yesterday = True
                elif TRADING_HOURS['morning_end'] < current_time < TRADING_HOURS.get('afternoon_start', 13):  # 午休
                    use_yesterday = True

                # 如果应该使用昨天的数据，检查是否有昨天的数据
                if use_yesterday:
                    # 需要昨天或更早的完整数据（但最新数据日期应该是最新的交易日）
                    # 考虑到可能有假期，允许更大的日期范围（最多7天）
                    # 如果最新数据日期在最近7天内，就认为缓存有效
                    days_diff = (today - latest_date).days
                    # 如果是工作日且在7天内，或者最新日期 >= 昨天，认为有效
                    if days_diff <= 7:
                        return True
                    # 否则检查是否 >= 昨天（排除周末）
                    yesterday = today - timedelta(days=1)
                    while yesterday.weekday() >= 5:
                        yesterday = yesterday - timedelta(days=1)
                    return latest_date >= yesterday
                else:
                    # 可以使用今天的数据（收盘后）
                    # 同样允许7天的容差（考虑假期）
                    days_diff = (today - latest_date).days
                    if days_diff <= 1:
                        return True
                    # 如果超过1天但在7天内，可能是假期，仍然认为有效
                    return days_diff <= 7

        except Exception as e:
            print(f"检查K线数据有效性失败 ({symbol}): {e}")
            return False
    
    def save_kline(self, symbol: str, data: pd.DataFrame,
                   cache_type: str = 'stock', period: str = 'daily',
                   incremental: bool = True):
        """
        保存K线数据到缓存（支持增量更新和自动清理）
        Args:
            symbol: 股票代码/板块名称/概念名称
            data: K线数据DataFrame
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            incremental: 是否增量更新（默认True，会合并现有缓存数据）
        """
        try:
            if data is None or data.empty:
                return

            # 准备数据
            data_to_save = data.copy()

            # 确保date列存在并转换为日期字符串格式
            if 'date' in data_to_save.columns:
                data_to_save['date'] = pd.to_datetime(data_to_save['date']).dt.strftime('%Y-%m-%d')
            elif '日期' in data_to_save.columns:
                data_to_save['date'] = pd.to_datetime(data_to_save['日期']).dt.strftime('%Y-%m-%d')
                # 重命名列
                data_to_save = data_to_save.rename(columns={'日期': 'date'})

            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with self.base._db_locks['kline']:
                with sqlite3.connect(self.base.db_path) as conn:
                    cursor = conn.cursor()

                    # 如果不是增量更新，先删除现有数据
                    if not incremental:
                        cursor.execute('''
                            DELETE FROM kline_data
                            WHERE symbol = ? AND cache_type = ? AND period = ?
                        ''', (symbol, cache_type, period))

                    # 准备插入数据
                    data_to_insert = []
                    for _, row in data_to_save.iterrows():
                        data_to_insert.append((
                            symbol,
                            cache_type,
                            period,
                            row.get('date'),
                            row.get('open'),
                            row.get('high'),
                            row.get('low'),
                            row.get('close'),
                            row.get('volume'),
                            row.get('amount'),
                            update_time
                        ))

                    # 批量插入（INSERT OR REPLACE处理重复数据）
                    cursor.executemany('''
                        INSERT OR REPLACE INTO kline_data
                        (symbol, cache_type, period, date, open, high, low, close, volume, amount, update_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', data_to_insert)

                    # 数据清理：只保留最近N天的数据
                    retention_days = getattr(config, 'KLINE_CACHE_RETENTION_DAYS', 250)
                    cursor.execute('''
                        DELETE FROM kline_data
                        WHERE symbol = ? AND cache_type = ? AND period = ?
                        AND date < datetime('now', '-{} days')
                    '''.format(retention_days), (symbol, cache_type, period))

                    conn.commit()

        except Exception as e:
            print(f"保存K线缓存失败 ({symbol}): {e}")

