"""
数据获取模块：使用tushare获取股票相关数据，集成缓存机制
重构版本：使用组合模式，将功能拆分为多个模块
"""
import pandas as pd
from typing import Dict, List, Optional
from .fetcher_base import FetcherBase
from .kline_fetcher import KlineFetcher
from .fundamental_fetcher import FundamentalFetcher
from .index_fetcher import IndexFetcher


def filter_stocks_by_board(stock_list: pd.DataFrame, board_types: List[str]) -> pd.DataFrame:
    """
    根据板块类型筛选股票
    Args:
        stock_list: 股票列表DataFrame，包含'code'列
        board_types: 板块类型列表，如 ['main', 'gem']
    Returns:
        筛选后的股票列表DataFrame
    """
    if stock_list is None or stock_list.empty:
        return pd.DataFrame()
    
    if not board_types:
        return stock_list
    
    # 将代码列转换为字符串，并格式化为6位（补零）
    stock_list = stock_list.copy()
    stock_list['code'] = stock_list['code'].astype(str).str.zfill(6)
    codes = stock_list['code']
    
    # 定义板块代码规则
    board_rules = {
        # 主板：包括上证主板(60开头)和深圳主板(00开头，但排除002中小板)
        'main': lambda code: code.startswith('60') or (code.startswith('00') and not code.startswith('002')),
        # 中小板：002xxx
        'sme': lambda code: code.startswith('002'),
        # 创业板：300xxx
        'gem': lambda code: code.startswith('300'),
        # 科创板：688xxx
        'star': lambda code: code.startswith('688'),
        # 北交所：8xxxx 或 43xxxx
        'bse': lambda code: code.startswith('8') or code.startswith('43'),
        # B股：900xxx(上证B股) 或 200xxx(深圳B股)
        'b': lambda code: code.startswith('900') or code.startswith('200'),
    }
    
    # 创建筛选条件
    mask = pd.Series([False] * len(stock_list), index=stock_list.index)
    for board_type in board_types:
        if board_type in board_rules:
            mask |= codes.apply(board_rules[board_type])
    
    return stock_list[mask].copy()


class DataFetcher(FetcherBase):
    """数据获取类（基于tushare，集成缓存）- 重构版本，使用组合模式"""
    
    def __init__(self, force_refresh: bool = False, progress_callback=None, test_sources: bool = True):
        """
        初始化数据获取器
        Args:
            force_refresh: 是否强制刷新缓存
            progress_callback: 进度回调函数，接收(status, message)参数
            test_sources: 是否测试数据源可用性（默认True）
        """
        # 初始化基础功能
        super().__init__(force_refresh, progress_callback, test_sources)
        
        # 组合功能模块
        self.kline_fetcher = KlineFetcher(self)
        self.fundamental_fetcher = FundamentalFetcher(self)
        self.index_fetcher = IndexFetcher(self)
    
    # ========== K线数据相关方法 ==========
    
    def get_stock_kline(self, stock_code: str, period: str = "daily", 
                       start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """获取股票K线数据（支持缓存检查）"""
        return self.kline_fetcher.get_stock_kline(stock_code, period, start_date, end_date)
    
    def batch_check_kline_cache_status(self, stock_codes: List[str], 
                                       show_progress: bool = False) -> Dict[str, str]:
        """批量检查股票K线缓存状态"""
        return self.kline_fetcher.batch_check_kline_cache_status(stock_codes, show_progress)
    
    def batch_load_cached_kline(self, stock_codes: List[str], 
                                show_progress: bool = False) -> Dict[str, pd.DataFrame]:
        """批量加载已缓存的K线数据到内存"""
        return self.kline_fetcher.batch_load_cached_kline(stock_codes, show_progress)
    
    def batch_get_stock_kline(self, stock_codes: List[str], start_date: str = None, 
                             end_date: str = None, show_progress: bool = False) -> Dict[str, pd.DataFrame]:
        """批量获取股票K线数据（使用按日期批量查询方式，大幅提升效率）"""
        return self.kline_fetcher.batch_get_stock_kline(stock_codes, start_date, end_date, show_progress)
    
    def get_sector_kline(self, sector_name: str, period: str = "daily", 
                        check_cache_only: bool = False) -> Optional[pd.DataFrame]:
        """获取板块K线数据（支持内存缓存和磁盘缓存）"""
        return self.kline_fetcher.get_sector_kline(sector_name, period, check_cache_only)
    
    # ========== 基本面和财务数据相关方法 ==========
    
    def get_stock_fundamental(self, stock_code: str) -> Optional[Dict]:
        """获取股票基本面数据（带缓存）"""
        return self.fundamental_fetcher.get_stock_fundamental(stock_code)
    
    def get_stock_financial(self, stock_code: str, force_refresh: bool = None) -> Optional[Dict]:
        """获取股票财务数据（带缓存）"""
        return self.fundamental_fetcher.get_stock_financial(stock_code, force_refresh)
    
    # ========== 指数权重数据相关方法 ==========
    
    def get_index_weight(
        self,
        index_code: str,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        force_refresh: bool = False
    ) -> Optional[pd.DataFrame]:
        """获取指数权重数据"""
        return self.index_fetcher.get_index_weight(
            index_code, trade_date, start_date, end_date, force_refresh
        )
    
    def batch_get_index_weight(
        self,
        index_codes: List[str],
        start_date: str = None,
        end_date: str = None,
        force_refresh: bool = False,
        show_progress: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """批量获取多个指数的权重数据"""
        return self.index_fetcher.batch_get_index_weight(
            index_codes, start_date, end_date, force_refresh, show_progress
        )
    
    # ========== 预加载方法（需要访问多个模块） ==========
    
    def preload_stock_data(self, stock_codes: List[str], data_types: List[str] = None,
                          max_workers: int = 5, show_progress: bool = True) -> Dict[str, Dict]:
        """
        预加载股票数据（支持显示详细进度）
        Args:
            stock_codes: 股票代码列表
            data_types: 要加载的数据类型列表，如 ['kline', 'fundamental', 'financial']，None表示加载所有
            max_workers: 最大线程数
            show_progress: 是否显示进度
        Returns:
            加载结果统计字典
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        if data_types is None:
            data_types = ['kline', 'fundamental', 'financial']
        
        # 启用批量模式
        self.batch_mode = True
        
        stats = {
            'total': len(stock_codes),
            'kline': {'success': 0, 'cached': 0, 'failed': 0},
            'fundamental': {'success': 0, 'cached': 0, 'failed': 0},
            'financial': {'success': 0, 'cached': 0, 'failed': 0},
        }
        
        import threading
        stats_lock = threading.Lock()
        processed_count = 0
        
        def load_single_stock_data(stock_code: str):
            """加载单只股票的数据"""
            nonlocal processed_count
            result = {'code': stock_code, 'kline': None, 'fundamental': None, 'financial': None}
            
            # 加载K线数据
            if 'kline' in data_types:
                try:
                    kline = self.get_stock_kline(stock_code)
                    if kline is not None and not kline.empty:
                        result['kline'] = 'success'
                        with stats_lock:
                            stats['kline']['success'] += 1
                    else:
                        result['kline'] = 'failed'
                        with stats_lock:
                            stats['kline']['failed'] += 1
                except Exception as e:
                    result['kline'] = 'failed'
                    with stats_lock:
                        stats['kline']['failed'] += 1
            
            # 加载基本面数据
            if 'fundamental' in data_types:
                try:
                    cached = self.cache_manager.get_fundamental(stock_code, self.force_refresh)
                    if cached is not None:
                        result['fundamental'] = 'cached'
                        with stats_lock:
                            stats['fundamental']['cached'] += 1
                    else:
                        fund = self.get_stock_fundamental(stock_code)
                        if fund is not None:
                            result['fundamental'] = 'success'
                            with stats_lock:
                                stats['fundamental']['success'] += 1
                        else:
                            result['fundamental'] = 'failed'
                            with stats_lock:
                                stats['fundamental']['failed'] += 1
                except Exception as e:
                    result['fundamental'] = 'failed'
                    with stats_lock:
                        stats['fundamental']['failed'] += 1
            
            # 加载财务数据
            if 'financial' in data_types:
                try:
                    cached = self.cache_manager.get_financial(stock_code, self.force_refresh)
                    if cached is not None:
                        result['financial'] = 'cached'
                        with stats_lock:
                            stats['financial']['cached'] += 1
                    else:
                        fin = self.get_stock_financial(stock_code)
                        if fin is not None:
                            result['financial'] = 'success'
                            with stats_lock:
                                stats['financial']['success'] += 1
                        else:
                            result['financial'] = 'failed'
                            with stats_lock:
                                stats['financial']['failed'] += 1
                except Exception as e:
                    result['financial'] = 'failed'
                    with stats_lock:
                        stats['financial']['failed'] += 1
            
            # 定期批量保存
            with stats_lock:
                processed_count += 1
                if processed_count % 200 == 0:
                    self.flush_batch_cache()
            
            return result
        
        if show_progress:
            print(f"\n开始预加载 {len(stock_codes)} 只股票的数据...")
            print(f"数据类型: {', '.join(data_types)}")
            print("=" * 60)
        
        # 使用线程池并行加载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(load_single_stock_data, code): code 
                      for code in stock_codes}
            
            if show_progress:
                pbar = tqdm(total=len(stock_codes), desc="数据预加载进度",
                           bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
            
            for future in as_completed(futures):
                result = future.result()
                if show_progress:
                    pbar.update(1)
                    if pbar.n % 50 == 0:
                        pbar.set_postfix({
                            'K线': f"{stats['kline']['success']+stats['kline']['cached']}/{stats['total']}",
                            '基本面': f"{stats['fundamental']['success']+stats['fundamental']['cached']}/{stats['total']}",
                            '财务': f"{stats['financial']['success']+stats['financial']['cached']}/{stats['total']}"
                        })
            
            if show_progress:
                pbar.close()
        
        # 最后批量保存剩余数据
        self.flush_batch_cache()
        self.batch_mode = False
        
        if show_progress:
            print("\n" + "=" * 60)
            print("数据预加载完成！统计信息：")
            for data_type in data_types:
                type_stats = stats[data_type]
                total_loaded = type_stats['success'] + type_stats['cached']
                print(f"\n{data_type.upper()}:")
                print(f"  成功加载: {type_stats['success']} 只")
                print(f"  已缓存: {type_stats['cached']} 只")
                print(f"  失败: {type_stats['failed']} 只")
                print(f"  总计: {total_loaded}/{stats['total']} ({total_loaded/stats['total']*100:.1f}%)")
            print("=" * 60)
        
        return stats
