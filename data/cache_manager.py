"""
缓存管理模块：管理本地Excel缓存
"""
import pandas as pd
import os
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import config


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = "cache"):
        """
        初始化缓存管理器
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        self._ensure_cache_dir()
        
        # 统一的缓存目录结构
        # 主目录：按数据类型分类
        self.data_dirs = {
            'kline': os.path.join(cache_dir, "data", "kline"),           # K线数据
            'fundamental': os.path.join(cache_dir, "data", "fundamental"), # 基本面数据
            'financial': os.path.join(cache_dir, "data", "financial"),    # 财务数据
            'sectors': os.path.join(cache_dir, "data", "sectors"),        # 板块数据
            'concepts': os.path.join(cache_dir, "data", "concepts"),      # 概念数据
        }
        
        # 元数据目录：存储汇总信息和集中存储文件（用于快速查询和兼容性）
        self.meta_dir = os.path.join(cache_dir, "meta")
        
        # 集中存储文件路径（放在meta目录下，统一管理）
        # 这些文件用于快速批量查询，但主要使用独立文件存储
        self.fundamental_cache = os.path.join(self.meta_dir, "fundamental_data.xlsx")
        self.financial_cache = os.path.join(self.meta_dir, "financial_data.xlsx")
        self.sectors_cache = os.path.join(self.meta_dir, "stock_sectors.xlsx")
        self.concepts_cache = os.path.join(self.meta_dir, "stock_concepts.xlsx")
        self.stock_list_cache = os.path.join(self.meta_dir, "stock_list.xlsx")
        
        # 新版独立文件存储路径（优先使用）
        self.kline_cache_dir = self.data_dirs['kline']
        self.fundamental_cache_dir = self.data_dirs['fundamental']
        self.financial_cache_dir = self.data_dirs['financial']
        self.sectors_cache_dir = self.data_dirs['sectors']
        self.concepts_cache_dir = self.data_dirs['concepts']
        
        # 确保所有缓存目录存在
        for cache_dir_path in list(self.data_dirs.values()) + [self.meta_dir]:
            if not os.path.exists(cache_dir_path):
                os.makedirs(cache_dir_path)
        
        # 缓存有效期（天数）
        # 低频数据（财务、板块、概念）默认不刷新，只在首次加载时获取
        self.cache_valid_days = {
            'fundamental': 7,      # 基本面数据7天
            'financial': 7,        # 财务数据7天（低频，默认不刷新）
            'sectors': 7,          # 板块信息7天（低频，默认不刷新）
            'concepts': 7,         # 概念信息7天（低频，默认不刷新）
            'stock_list': 1,       # 股票列表1天
            'kline': 1,            # K线数据1天（当日缓存）
        }
        
        # 定义哪些数据类型是低频的（默认不刷新）
        self.low_frequency_types = ['financial', 'sectors', 'concepts']
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _is_cache_valid(self, cache_file: str, cache_type: str) -> bool:
        """
        检查缓存是否有效
        Args:
            cache_file: 缓存文件路径
            cache_type: 缓存类型
        Returns:
            是否有效
        """
        if not os.path.exists(cache_file):
            return False
        
        # 检查文件修改时间
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        valid_days = self.cache_valid_days.get(cache_type, 7)
        
        # 对于当日缓存（K线数据），检查是否是同一天
        if cache_type == 'kline':
            return mtime.date() == datetime.now().date()
        
        return (datetime.now() - mtime).days < valid_days
    
    def _is_data_valid(self, data: Dict, data_type: str) -> bool:
        """
        检查数据是否有效（关键指标不为空）
        Args:
            data: 数据字典
            data_type: 数据类型 ('fundamental', 'financial')
        Returns:
            是否有效
        """
        if not data or not isinstance(data, dict):
            return False
        
        if data_type == 'fundamental':
            # 基本面数据：至少需要pe_ratio或pb_ratio之一有效
            pe = data.get('pe_ratio', 0)
            pb = data.get('pb_ratio', 0)
            # 如果两个都是0或None，视为无效
            if (pe == 0 or pe is None) and (pb == 0 or pb is None):
                return False
            return True
        elif data_type == 'financial':
            # 财务数据：至少需要roe有效
            roe = data.get('roe', 0)
            if roe == 0 or roe is None:
                return False
            return True
        
        return True
    
    def get_fundamental(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取基本面数据（优先从独立文件读取，支持断点续传）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            基本面数据字典
        """
        if force_refresh:
            return None
        
        # 方式1：优先从独立文件读取（支持断点续传）
        cache_file = os.path.join(self.fundamental_cache_dir, f"{stock_code}.xlsx")
        if os.path.exists(cache_file) and self._is_cache_valid(cache_file, 'fundamental'):
            try:
                df = pd.read_excel(cache_file, engine='openpyxl')
                if not df.empty:
                    data = df.iloc[0].to_dict()
                    # 验证数据有效性
                    if self._is_data_valid(data, 'fundamental'):
                        return data
                    else:
                        # 数据无效，删除缓存文件，强制重新获取
                        try:
                            os.remove(cache_file)
                        except:
                            pass
            except Exception as e:
                print(f"读取基本面独立缓存失败 ({stock_code}): {e}")
        
        # 方式2：从集中文件读取（兼容旧数据）
        if self._is_cache_valid(self.fundamental_cache, 'fundamental'):
            try:
                df = pd.read_excel(self.fundamental_cache, engine='openpyxl')
                stock_data = df[df['code'] == stock_code]
                if not stock_data.empty:
                    data = stock_data.iloc[0].to_dict()
                    # 验证数据有效性
                    if self._is_data_valid(data, 'fundamental'):
                        return data
            except Exception as e:
                print(f"读取基本面集中缓存失败: {e}")
        
        return None
    
    def save_fundamental(self, stock_code: str, data: Dict):
        """
        保存基本面数据到缓存（支持独立文件存储，便于断点续传）
        Args:
            stock_code: 股票代码
            data: 基本面数据
        """
        try:
            # 验证数据有效性
            if not self._is_data_valid(data, 'fundamental'):
                return  # 无效数据不保存
            
            # 保存为独立文件（支持断点续传）
            cache_file = os.path.join(self.fundamental_cache_dir, f"{stock_code}.xlsx")
            data_to_save = data.copy()
            data_to_save['code'] = stock_code
            data_to_save['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            pd.DataFrame([data_to_save]).to_excel(cache_file, index=False, engine='openpyxl')
            
            # 同时保存到集中文件（用于快速批量查询）
            if os.path.exists(self.fundamental_cache):
                df = pd.read_excel(self.fundamental_cache, engine='openpyxl')
                df = df[df['code'] != stock_code]
            else:
                df = pd.DataFrame()
            
            new_row = pd.DataFrame([data_to_save])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_excel(self.fundamental_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存基本面缓存失败: {e}")
    
    def batch_save_fundamental(self, data_dict: Dict[str, Dict]):
        """
        批量保存基本面数据（提高效率，减少IO操作）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        if not data_dict:
            return
        
        try:
            # 读取现有集中文件
            if os.path.exists(self.fundamental_cache):
                df = pd.read_excel(self.fundamental_cache, engine='openpyxl')
                # 移除要更新的股票旧数据
                existing_codes = set(data_dict.keys())
                df = df[~df['code'].isin(existing_codes)]
            else:
                df = pd.DataFrame()
            
            # 准备新数据
            new_rows = []
            for stock_code, data in data_dict.items():
                # 验证数据有效性
                if not self._is_data_valid(data, 'fundamental'):
                    continue
                
                # 保存独立文件
                cache_file = os.path.join(self.fundamental_cache_dir, f"{stock_code}.xlsx")
                data_to_save = data.copy()
                data_to_save['code'] = stock_code
                data_to_save['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                pd.DataFrame([data_to_save]).to_excel(cache_file, index=False, engine='openpyxl')
                
                new_rows.append(data_to_save)
            
            # 批量更新集中文件
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_excel(self.fundamental_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"批量保存基本面缓存失败: {e}")
    
    def get_financial(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取财务数据（优先从独立文件读取，支持断点续传）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            财务数据字典
        """
        if force_refresh:
            return None
        
        # 优先从独立文件读取（支持断点续传）
        cache_file = os.path.join(self.financial_cache_dir, f"{stock_code}.xlsx")
        if os.path.exists(cache_file) and self._is_cache_valid(cache_file, 'financial'):
            try:
                df = pd.read_excel(cache_file, engine='openpyxl')
                if not df.empty:
                    data = df.iloc[0].to_dict()
                    # 验证数据有效性
                    if self._is_data_valid(data, 'financial'):
                        return data
                    else:
                        # 数据无效，删除缓存文件，强制重新获取
                        try:
                            os.remove(cache_file)
                        except:
                            pass
            except Exception as e:
                print(f"读取财务独立缓存失败 ({stock_code}): {e}")
        
        # 从集中文件读取（用于快速批量查询）
        if self._is_cache_valid(self.financial_cache, 'financial'):
            try:
                df = pd.read_excel(self.financial_cache, engine='openpyxl')
                stock_data = df[df['code'] == stock_code]
                if not stock_data.empty:
                    data = stock_data.iloc[0].to_dict()
                    # 验证数据有效性
                    if self._is_data_valid(data, 'financial'):
                        return data
            except Exception as e:
                print(f"读取财务集中缓存失败: {e}")
        
        return None
    
    def save_financial(self, stock_code: str, data: Dict):
        """
        保存财务数据到缓存（支持独立文件存储，便于断点续传）
        Args:
            stock_code: 股票代码
            data: 财务数据
        """
        try:
            # 验证数据有效性
            if not self._is_data_valid(data, 'financial'):
                return  # 无效数据不保存
            
            # 保存为独立文件（支持断点续传）
            cache_file = os.path.join(self.financial_cache_dir, f"{stock_code}.xlsx")
            data_to_save = data.copy()
            data_to_save['code'] = stock_code
            data_to_save['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            pd.DataFrame([data_to_save]).to_excel(cache_file, index=False, engine='openpyxl')
            
            # 同时保存到集中文件（用于快速批量查询）
            if os.path.exists(self.financial_cache):
                df = pd.read_excel(self.financial_cache, engine='openpyxl')
                df = df[df['code'] != stock_code]
            else:
                df = pd.DataFrame()
            
            new_row = pd.DataFrame([data_to_save])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_excel(self.financial_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存财务缓存失败: {e}")
    
    def batch_save_financial(self, data_dict: Dict[str, Dict]):
        """
        批量保存财务数据（提高效率，减少IO操作）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        if not data_dict:
            return
        
        try:
            # 读取现有集中文件
            if os.path.exists(self.financial_cache):
                df = pd.read_excel(self.financial_cache, engine='openpyxl')
                # 移除要更新的股票旧数据
                existing_codes = set(data_dict.keys())
                df = df[~df['code'].isin(existing_codes)]
            else:
                df = pd.DataFrame()
            
            # 准备新数据
            new_rows = []
            for stock_code, data in data_dict.items():
                # 验证数据有效性
                if not self._is_data_valid(data, 'financial'):
                    continue
                
                # 保存独立文件
                cache_file = os.path.join(self.financial_cache_dir, f"{stock_code}.xlsx")
                data_to_save = data.copy()
                data_to_save['code'] = stock_code
                data_to_save['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                pd.DataFrame([data_to_save]).to_excel(cache_file, index=False, engine='openpyxl')
                
                new_rows.append(data_to_save)
            
            # 批量更新集中文件
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_excel(self.financial_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"批量保存财务缓存失败: {e}")
    
    def get_stock_sectors(self, stock_code: str, force_refresh: bool = False) -> List[str]:
        """
        从缓存获取股票板块
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            板块列表
        """
        if not force_refresh and self._is_cache_valid(self.sectors_cache, 'sectors'):
            try:
                df = pd.read_excel(self.sectors_cache, engine='openpyxl')
                stock_data = df[df['code'] == stock_code]
                if not stock_data.empty:
                    sectors_str = stock_data.iloc[0].get('sectors', '')
                    return sectors_str.split(',') if sectors_str else []
            except Exception as e:
                print(f"读取板块缓存失败: {e}")
        return []
    
    def save_stock_sectors(self, stock_code: str, sectors: List[str]):
        """
        保存股票板块到缓存
        Args:
            stock_code: 股票代码
            sectors: 板块列表
        """
        try:
            if os.path.exists(self.sectors_cache):
                df = pd.read_excel(self.sectors_cache, engine='openpyxl')
                df = df[df['code'] != stock_code]
            else:
                df = pd.DataFrame()
            
            new_row = pd.DataFrame([{
                'code': stock_code,
                'sectors': ','.join(sectors),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            
            df.to_excel(self.sectors_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存板块缓存失败: {e}")
    
    def get_stock_concepts(self, stock_code: str, force_refresh: bool = False) -> List[str]:
        """
        从缓存获取股票概念
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            概念列表
        """
        if not force_refresh and self._is_cache_valid(self.concepts_cache, 'concepts'):
            try:
                df = pd.read_excel(self.concepts_cache, engine='openpyxl')
                stock_data = df[df['code'] == stock_code]
                if not stock_data.empty:
                    concepts_str = stock_data.iloc[0].get('concepts', '')
                    return concepts_str.split(',') if concepts_str else []
            except Exception as e:
                print(f"读取概念缓存失败: {e}")
        return []
    
    def save_stock_concepts(self, stock_code: str, concepts: List[str]):
        """
        保存股票概念到缓存
        Args:
            stock_code: 股票代码
            concepts: 概念列表
        """
        try:
            if os.path.exists(self.concepts_cache):
                df = pd.read_excel(self.concepts_cache, engine='openpyxl')
                df = df[df['code'] != stock_code]
            else:
                df = pd.DataFrame()
            
            new_row = pd.DataFrame([{
                'code': stock_code,
                'concepts': ','.join(concepts),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            
            df.to_excel(self.concepts_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存概念缓存失败: {e}")
    
    def get_stock_list(self, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取股票列表
        Args:
            force_refresh: 是否强制刷新
        Returns:
            股票列表DataFrame
        """
        if not force_refresh and self._is_cache_valid(self.stock_list_cache, 'stock_list'):
            try:
                return pd.read_excel(self.stock_list_cache, engine='openpyxl')
            except Exception as e:
                print(f"读取股票列表缓存失败: {e}")
        return None
    
    def save_stock_list(self, stock_list: pd.DataFrame):
        """
        保存股票列表到缓存
        Args:
            stock_list: 股票列表DataFrame
        """
        try:
            stock_list.to_excel(self.stock_list_cache, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存股票列表缓存失败: {e}")
    
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
        
        cache_file = self._get_kline_cache_path(symbol, cache_type, period)
        if self._is_cache_valid(cache_file, 'kline'):
            try:
                df = pd.read_excel(cache_file, engine='openpyxl')
                # 确保date列是datetime类型
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    # 检查最新交易日数据是否存在
                    latest_date = df['date'].max()
                    today = datetime.now().date()
                    # 如果最新数据是今天或昨天（考虑交易日），则可以使用缓存
                    if latest_date.date() >= today - timedelta(days=1):
                        return df
                    # 否则返回None，需要重新下载
                else:
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
        cache_file = self._get_kline_cache_path(symbol, cache_type, period)
        if not os.path.exists(cache_file):
            return False
        
        try:
            df = pd.read_excel(cache_file, engine='openpyxl')
            if df.empty:
                return False
            
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                latest_date = df['date'].max()
                today = datetime.now().date()
                current_time = datetime.now().time()
                weekday = datetime.now().weekday()
                
                # 判断是否应该使用昨天的数据
                # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
                use_yesterday = False
                if weekday >= 5:  # 周末
                    use_yesterday = True
                elif current_time < datetime.strptime('09:30', '%H:%M').time():  # 还没开盘
                    use_yesterday = True
                elif (datetime.strptime('09:30', '%H:%M').time() <= current_time <= datetime.strptime('11:30', '%H:%M').time()) or \
                     (datetime.strptime('13:00', '%H:%M').time() <= current_time <= datetime.strptime('15:00', '%H:%M').time()):  # 交易中
                    use_yesterday = True
                elif datetime.strptime('11:30', '%H:%M').time() < current_time < datetime.strptime('13:00', '%H:%M').time():  # 午休
                    use_yesterday = True
                
                # 如果应该使用昨天的数据，检查是否有昨天的数据
                if use_yesterday:
                    # 需要昨天或更早的完整数据
                    yesterday = today - timedelta(days=1)
                    # 确保不是周末
                    while yesterday.weekday() >= 5:
                        yesterday = yesterday - timedelta(days=1)
                    return latest_date.date() >= yesterday
                else:
                    # 可以使用今天的数据（收盘后）
                    return latest_date.date() >= today - timedelta(days=1)
            else:
                # 如果没有date列，检查文件修改时间
                return self._is_cache_valid(cache_file, 'kline')
        except:
            return False
    
    def save_kline(self, symbol: str, data: pd.DataFrame, 
                   cache_type: str = 'stock', period: str = 'daily', 
                   incremental: bool = True):
        """
        保存K线数据到缓存（支持增量更新）
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
            
            cache_file = self._get_kline_cache_path(symbol, cache_type, period)
            
            # 确保date列存在
            if 'date' in data.columns:
                data_to_save = data.copy()
            else:
                data_to_save = data.copy()
                if '日期' in data.columns:
                    data_to_save['date'] = pd.to_datetime(data['日期'])
            
            # 增量更新：合并现有缓存数据
            if incremental and os.path.exists(cache_file):
                try:
                    existing_df = pd.read_excel(cache_file, engine='openpyxl')
                    if not existing_df.empty and 'date' in existing_df.columns:
                        # 确保date列是datetime类型
                        existing_df['date'] = pd.to_datetime(existing_df['date'])
                        data_to_save['date'] = pd.to_datetime(data_to_save['date'])
                        
                        # 合并数据：保留旧数据，用新数据更新或追加
                        # 移除旧数据中与新数据日期重复的记录
                        existing_df = existing_df[~existing_df['date'].isin(data_to_save['date'])]
                        
                        # 合并新旧数据
                        data_to_save = pd.concat([existing_df, data_to_save], ignore_index=True)
                        
                        # 按日期排序并去重（保留最新的）
                        data_to_save = data_to_save.sort_values('date').drop_duplicates(subset=['date'], keep='last')
                except Exception as e:
                    # 如果读取现有缓存失败，直接使用新数据
                    print(f"读取现有K线缓存失败，使用新数据覆盖 ({symbol}): {e}")
            
            # 保存到缓存
            data_to_save.to_excel(cache_file, index=False, engine='openpyxl')
        except Exception as e:
            print(f"保存K线缓存失败 ({symbol}): {e}")
    
    def _get_kline_cache_path(self, symbol: str, cache_type: str, period: str) -> str:
        """
        获取K线缓存文件路径
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
        Returns:
            缓存文件路径
        """
        # 清理symbol中的特殊字符，用于文件名
        safe_symbol = str(symbol).replace('/', '_').replace('\\', '_').replace(':', '_')
        filename = f"{cache_type}_{safe_symbol}_{period}.xlsx"
        return os.path.join(self.kline_cache_dir, filename)
    
    def check_cache_completeness(self, stock_codes: List[str], 
                                data_types: List[str] = None) -> Dict[str, Dict]:
        """
        检查缓存完整性，判断是否需要预加载
        Args:
            stock_codes: 股票代码列表
            data_types: 要检查的数据类型列表，如 ['fundamental', 'financial']，None表示检查所有
        Returns:
            缓存完整性统计字典，包含每个类型的覆盖率
        """
        if data_types is None:
            data_types = ['fundamental', 'financial']
        
        if not stock_codes:
            return {dt: {'total': 0, 'cached': 0, 'coverage': 0.0, 'needs_preload': False} for dt in data_types}
        
        # 抽样检查（最多检查前1000只，避免太慢）
        sample_size = min(1000, len(stock_codes))
        sample_codes = stock_codes[:sample_size]
        
        completeness = {}
        for data_type in data_types:
            cached_count = 0
            for code in sample_codes:
                if data_type == 'fundamental':
                    if self.get_fundamental(code, force_refresh=False) is not None:
                        cached_count += 1
                elif data_type == 'financial':
                    if self.get_financial(code, force_refresh=False) is not None:
                        cached_count += 1
            
            coverage = cached_count / sample_size if sample_size > 0 else 0.0
            completeness[data_type] = {
                'total': sample_size,
                'cached': cached_count,
                'coverage': coverage,
                'needs_preload': coverage < 0.5  # 覆盖率低于50%需要预加载
            }
        
        return completeness

