"""
策略推荐结果缓存模块
"""
import pandas as pd
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional


class RecommendationCache:
    """策略推荐结果缓存管理器"""
    
    def __init__(self, base):
        """
        初始化推荐结果缓存管理器
        Args:
            base: CacheBase实例，提供基础功能
        """
        self.base = base
    
    def save_recommendations(
        self,
        trade_date: str,
        strategy_name: str,
        strategy_type: str,
        results: pd.DataFrame
    ):
        """
        保存策略推荐结果到缓存
        Args:
            trade_date: 推荐日期，格式：YYYYMMDD
            strategy_name: 策略名称
            strategy_type: 策略类型
            results: 推荐结果DataFrame，必须包含 code, name, score 列，可能包含其他策略特定字段
        """
        if results is None or results.empty:
            return
        
        # 标准化日期格式
        trade_date = trade_date.replace('-', '')
        
        try:
            with self.base._get_db_connection(timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # 删除该日期该策略的旧记录（如果存在）
                cursor.execute('''
                    DELETE FROM strategy_recommendations
                    WHERE trade_date = ? AND strategy_name = ?
                ''', (trade_date, strategy_name))
                
                # 准备插入数据
                data_to_insert = []
                for idx, row in results.iterrows():
                    stock_code = str(row.get('code', '')).strip()
                    stock_name = str(row.get('name', '')).strip() if pd.notna(row.get('name')) else ''
                    score = float(row.get('score', 0)) if pd.notna(row.get('score')) else 0
                    rank = idx + 1 if isinstance(idx, int) else len(data_to_insert) + 1
                    
                    # 提取策略特定指标（排除基本字段）
                    basic_fields = {'code', 'name', 'score', 'category'}
                    metrics = {}
                    for col in row.index:
                        if col not in basic_fields and pd.notna(row[col]):
                            try:
                                # 尝试转换为数值
                                value = row[col]
                                if isinstance(value, (int, float)):
                                    metrics[col] = value
                                elif isinstance(value, str):
                                    # 尝试转换为数值，如果失败则保留字符串
                                    try:
                                        metrics[col] = float(value)
                                    except ValueError:
                                        metrics[col] = value
                                else:
                                    metrics[col] = str(value)
                            except Exception:
                                pass
                    
                    category = str(row.get('category', '')) if pd.notna(row.get('category')) else None
                    
                    data_to_insert.append((
                        trade_date,
                        strategy_name,
                        strategy_type,
                        self.base._normalize_stock_code(stock_code),
                        stock_name,
                        rank,
                        score,
                        json.dumps(metrics, ensure_ascii=False) if metrics else None,
                        category,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ))
                
                # 批量插入
                cursor.executemany('''
                    INSERT INTO strategy_recommendations
                    (trade_date, strategy_name, strategy_type, stock_code, stock_name, 
                     rank, score, metrics_json, category, created_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', data_to_insert)
                
                conn.commit()
                
        except Exception as e:
            print(f"保存策略推荐结果失败 ({trade_date}, {strategy_name}): {e}")
            import traceback
            traceback.print_exc()
    
    def get_recommendations(
        self,
        trade_date: str,
        strategy_name: str = None,
        strategy_type: str = None
    ) -> Optional[pd.DataFrame]:
        """
        获取策略推荐结果
        Args:
            trade_date: 推荐日期，格式：YYYYMMDD
            strategy_name: 策略名称，如果为None则返回所有策略
            strategy_type: 策略类型，如果为None则返回所有类型
        Returns:
            推荐结果DataFrame
        """
        # 标准化日期格式
        trade_date = trade_date.replace('-', '')
        
        try:
            with sqlite3.connect(self.base.db_path) as conn:
                query = '''
                    SELECT trade_date, strategy_name, strategy_type, stock_code, stock_name,
                           rank, score, metrics_json, category, created_time
                    FROM strategy_recommendations
                    WHERE trade_date = ?
                '''
                params = [trade_date]
                
                if strategy_name:
                    query += ' AND strategy_name = ?'
                    params.append(strategy_name)
                
                if strategy_type:
                    query += ' AND strategy_type = ?'
                    params.append(strategy_type)
                
                query += ' ORDER BY strategy_name, rank'
                
                df = pd.read_sql_query(query, conn, params=params)
                
                if not df.empty:
                    # 解析metrics_json
                    for idx, row in df.iterrows():
                        if pd.notna(row['metrics_json']) and row['metrics_json']:
                            try:
                                metrics = json.loads(row['metrics_json'])
                                for key, value in metrics.items():
                                    df.at[idx, key] = value
                            except Exception:
                                pass
                    
                    # 删除metrics_json列（已经展开）
                    if 'metrics_json' in df.columns:
                        df = df.drop(columns=['metrics_json'])
                    
                    return df
                
        except Exception as e:
            print(f"读取策略推荐结果失败 ({trade_date}): {e}")
        
        return None
    
    def get_stock_recommendations(
        self,
        stock_code: str,
        start_date: str = None,
        end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """
        获取某股票的历史推荐记录
        Args:
            stock_code: 股票代码
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
        Returns:
            推荐记录DataFrame
        """
        stock_code = self.base._normalize_stock_code(stock_code)
        
        # 标准化日期格式
        if start_date:
            start_date = start_date.replace('-', '')
        if end_date:
            end_date = end_date.replace('-', '')
        
        try:
            with sqlite3.connect(self.base.db_path) as conn:
                query = '''
                    SELECT trade_date, strategy_name, strategy_type, stock_code, stock_name,
                           rank, score, metrics_json, category, created_time
                    FROM strategy_recommendations
                    WHERE stock_code = ?
                '''
                params = [stock_code]
                
                if start_date:
                    query += ' AND trade_date >= ?'
                    params.append(start_date)
                
                if end_date:
                    query += ' AND trade_date <= ?'
                    params.append(end_date)
                
                query += ' ORDER BY trade_date DESC, strategy_name, rank'
                
                df = pd.read_sql_query(query, conn, params=params)
                
                if not df.empty:
                    # 解析metrics_json
                    for idx, row in df.iterrows():
                        if pd.notna(row['metrics_json']) and row['metrics_json']:
                            try:
                                metrics = json.loads(row['metrics_json'])
                                for key, value in metrics.items():
                                    df.at[idx, key] = value
                            except Exception:
                                pass
                    
                    # 删除metrics_json列
                    if 'metrics_json' in df.columns:
                        df = df.drop(columns=['metrics_json'])
                    
                    return df
                
        except Exception as e:
            print(f"读取股票推荐记录失败 ({stock_code}): {e}")
        
        return None

