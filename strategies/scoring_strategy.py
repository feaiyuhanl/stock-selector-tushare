"""
打分策略：多维度打分选股策略
"""
import pandas as pd
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from tqdm import tqdm
import config
from .base_strategy import BaseStrategy
from scorers import (
    FundamentalScorer,
    VolumeScorer,
    PriceScorer,
)


class ScoringStrategy(BaseStrategy):
    """打分策略类"""
    
    def __init__(self, data_fetcher=None, force_refresh: bool = False, test_sources: bool = True):
        """
        初始化打分策略
        Args:
            data_fetcher: 数据获取器
            force_refresh: 是否强制刷新缓存
            test_sources: 是否测试数据源可用性（默认True）
        """
        super().__init__(data_fetcher, force_refresh, test_sources)
        self.fundamental_scorer = FundamentalScorer()
        self.volume_scorer = VolumeScorer()
        self.price_scorer = PriceScorer()
        self.weights = config.WEIGHT_CONFIG
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "", 
                      progress_callback=None) -> Optional[Dict]:
        """
        评估单只股票
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            progress_callback: 进度回调函数，接收(status, message)参数
        Returns:
            评估结果字典
        """
        try:
            if progress_callback:
                progress_callback('loading', f"加载 {stock_code} {stock_name} 的数据...")
            
            # 1. 获取K线数据
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取K线数据...")
            kline_data = self.data_fetcher.get_stock_kline(stock_code)
            if kline_data is None or kline_data.empty:
                if progress_callback:
                    progress_callback('failed', f"{stock_code} {stock_name}: K线数据获取失败")
                return None
            
            # 2. 获取基本面数据（带缓存）
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取基本面数据...")
            fundamental_data = self.data_fetcher.get_stock_fundamental(stock_code)
            if fundamental_data is None:
                fundamental_data = {}
            
            # 3. 获取财务数据（带缓存）
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取财务数据...")
            financial_data = self.data_fetcher.get_stock_financial(stock_code)
            if financial_data is None:
                financial_data = {}
            
            # 4. 计算各维度得分
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 计算评分...")
            fundamental_result = self.fundamental_scorer.score(fundamental_data, financial_data)
            volume_result = self.volume_scorer.score(kline_data)
            price_result = self.price_scorer.score(kline_data)

            # 提取综合得分
            fundamental_score = fundamental_result['score']
            volume_score = volume_result['score']
            price_score = price_result['score']
            
            # 5. 计算综合得分
            total_score = (
                fundamental_score * self.weights['fundamental'] +
                volume_score * self.weights['volume'] +
                price_score * self.weights['price']
            )
            
            # 6. 获取当前价格信息
            current_price = kline_data['close'].iloc[-1] if not kline_data.empty else 0
            current_volume = kline_data['volume'].iloc[-1] if not kline_data.empty else 0
            
            result = {
                'code': stock_code,
                'name': stock_name,
                'score': round(total_score, 2),  # 策略基类要求的字段
                'total_score': round(total_score, 2),  # 保持兼容性
                'fundamental_score': round(fundamental_score, 2),
                'volume_score': round(volume_score, 2),
                'price_score': round(price_score, 2),
                'current_price': round(current_price, 2),
                'current_volume': current_volume,
                # 基本面详细指标
                'pe_ratio': fundamental_result.get('pe_ratio'),
                'pb_ratio': fundamental_result.get('pb_ratio'),
                'roe': fundamental_result.get('roe'),
                'revenue_growth': fundamental_result.get('revenue_growth'),
                'profit_growth': fundamental_result.get('profit_growth'),
                # 成交量详细指标
                'volume_ratio': volume_result.get('volume_ratio'),
                'turnover_rate': volume_result.get('turnover_rate'),
                'volume_trend': volume_result.get('volume_trend'),
                # 价格详细指标
                'price_trend': price_result.get('price_trend'),
                'price_position': price_result.get('price_position'),
                'volatility': price_result.get('volatility'),
                # 子维度得分（用于详细展示）
                'pe_ratio_score': fundamental_result.get('pe_ratio_score', 50),
                'pb_ratio_score': fundamental_result.get('pb_ratio_score', 50),
                'roe_score': fundamental_result.get('roe_score', 50),
                'revenue_growth_score': fundamental_result.get('revenue_growth_score', 50),
                'profit_growth_score': fundamental_result.get('profit_growth_score', 50),
                'volume_ratio_score': volume_result.get('volume_ratio_score', 50),
                'turnover_rate_score': volume_result.get('turnover_rate_score', 50),
                'volume_trend_score': volume_result.get('volume_trend_score', 50),
                'price_trend_score': price_result.get('price_trend_score', 50),
                'price_position_score': price_result.get('price_position_score', 50),
                'volatility_score': price_result.get('volatility_score', 50),
            }
            
            if progress_callback:
                progress_callback('success', f"{stock_code} {stock_name}: 评估完成，得分 {result['score']:.2f}")
            
            return result
            
        except Exception as e:
            error_msg = f"评估 {stock_code} {stock_name} 时出错: {e}"
            if progress_callback:
                progress_callback('failed', error_msg)
            else:
                print(error_msg)
            return None
    
    def preload_all_data(self, stock_codes: List[str], stock_name_map: Dict[str, str],
                        max_workers: int = 5) -> Dict[str, Dict]:
        """
        预加载所有股票的数据（数据获取阶段）
        Args:
            stock_codes: 股票代码列表
            stock_name_map: 股票名称映射字典
            max_workers: 最大线程数
        Returns:
            预加载的数据字典，格式为 {stock_code: {kline_data, fundamental_data, financial_data}}
        """
        preloaded_data = {}
        total = len(stock_codes)
        
        batch_kline_data = {}
        
        # 阶段1：数据准备
        print("\n【阶段1】数据准备")
        print(f"  股票总数: {total} 只")
        
        if total >= 50:  # 超过50只股票时使用优化方案
            try:
                # 批量检查缓存状态
                print("  检查缓存状态...", end="", flush=True)
                cache_status = self.data_fetcher.batch_check_kline_cache_status(
                    stock_codes, 
                    show_progress=False  # 不显示进度条，只显示结果
                )
                
                # 分类股票
                latest_stocks = [code for code, status in cache_status.items() if status == 'latest']
                outdated_stocks = [code for code, status in cache_status.items() if status == 'outdated']
                missing_stocks = [code for code, status in cache_status.items() if status == 'missing']
                
                latest_count = len(latest_stocks)
                outdated_count = len(outdated_stocks)
                missing_count = len(missing_stocks)
                
                print(f" ✓ 完成")
                print(f"  缓存状态: 最新 {latest_count} 只 | 需更新 {outdated_count} 只 | 缺失 {missing_count} 只")
                
                # 批量加载已有最新缓存的股票数据
                if latest_stocks:
                    print(f"  加载最新缓存数据 ({latest_count} 只)...")
                    cached_kline_data = self.data_fetcher.batch_load_cached_kline(
                        latest_stocks,
                        show_progress=True  # 显示进度
                    )
                    batch_kline_data.update(cached_kline_data)
                    print(f"  ✓ 完成: 成功加载 {len(cached_kline_data)} 只股票的缓存数据")
                
                # 批量获取需要更新的股票（旧缓存+无缓存）
                stocks_to_fetch = outdated_stocks + missing_stocks
                if stocks_to_fetch:
                    try:
                        print(f"  获取K线数据 ({len(stocks_to_fetch)} 只)...")
                        fetched_kline_data = self.data_fetcher.batch_get_stock_kline(
                            stocks_to_fetch,
                            show_progress=True
                        )
                        
                        # 对于有旧缓存的股票，需要合并新旧数据（增量更新）
                        # 注意：batch_get_stock_kline 返回的字典键是 clean_code（已格式化的6位代码）
                        for stock_code in outdated_stocks:
                            clean_code = self.data_fetcher._format_stock_code(stock_code)
                            # 注意：fetched_kline_data 的键是 clean_code，不是原始的 stock_code
                            if clean_code in fetched_kline_data:
                                new_data = fetched_kline_data[clean_code]
                                # 获取旧缓存数据
                                old_data = self.data_fetcher.cache_manager.get_kline(
                                    clean_code, 'stock', 'daily', False
                                )
                                if old_data is not None and not old_data.empty:
                                    # 合并新旧数据
                                    old_data = old_data.copy()
                                    old_data['date'] = pd.to_datetime(old_data['date'])
                                    new_data = new_data.copy()
                                    new_data['date'] = pd.to_datetime(new_data['date'])
                                    # 合并：旧数据 + 新数据，按日期去重（保留新数据）
                                    combined = pd.concat([old_data, new_data], ignore_index=True)
                                    combined = combined.sort_values('date').drop_duplicates(subset=['date'], keep='last')
                                    fetched_kline_data[clean_code] = combined
                        
                        # 将 fetched_kline_data 的键转换为原始 stock_code，以便后续使用
                        # 但保存时需要使用 clean_code
                        for clean_code, kline_df in fetched_kline_data.items():
                            # 找到对应的原始 stock_code（用于 batch_kline_data）
                            original_code = None
                            for sc in stocks_to_fetch:
                                if self.data_fetcher._format_stock_code(sc) == clean_code:
                                    original_code = sc
                                    break
                            if original_code:
                                batch_kline_data[original_code] = kline_df
                        
                        # 批量保存新获取的K线缓存
                        saved_count = 0
                        for clean_code, kline_df in fetched_kline_data.items():
                            if kline_df is not None and not kline_df.empty:
                                # clean_code 已经是格式化后的6位代码，直接使用
                                self.data_fetcher.cache_manager.save_kline(
                                    clean_code, kline_df, 'stock', 'daily', incremental=True
                                )
                                saved_count += 1
                        
                        # 统计批量获取的结果
                        fetched_count = len(fetched_kline_data)
                        print(f"  ✓ 获取完成: 成功 {fetched_count} 只")
                    except Exception as e:
                        print(f"  ✗ 批量获取失败: {e}")
                        print("  将回退到单股票查询模式")
                        fetched_count = 0  # 标记为已处理，避免重复处理
            except Exception as e:
                print(f"  ✗ 批量加载流程失败: {e}")
                print("  将回退到单股票查询模式")
                batch_kline_data = {}
        
        def preload_single_stock(stock_code: str) -> tuple:
            """预加载单只股票的数据（用于多线程）"""
            stock_name = stock_name_map.get(stock_code, "")
            try:
                # 1. 获取K线数据（优先使用批量加载的数据）
                kline_data = None
                if stock_code in batch_kline_data:
                    # 使用批量加载的K线数据
                    kline_data = batch_kline_data[stock_code]
                else:
                    # 批量加载中不存在，使用单股票查询（可能已缓存）
                    kline_data = self.data_fetcher.get_stock_kline(stock_code)
                
                if kline_data is None or kline_data.empty:
                    return (stock_code, None)
                
                # 2. 获取基本面数据（带缓存）
                fundamental_data = self.data_fetcher.get_stock_fundamental(stock_code)
                if fundamental_data is None:
                    fundamental_data = {}
                
                # 3. 获取财务数据（带缓存）
                financial_data = self.data_fetcher.get_stock_financial(stock_code)
                if financial_data is None:
                    financial_data = {}
                
                data = {
                    'kline_data': kline_data,
                    'fundamental_data': fundamental_data,
                    'financial_data': financial_data,
                    'stock_name': stock_name
                }
                
                return (stock_code, data)
            except Exception as e:
                return (stock_code, None)
        
        # 启用批量缓存模式
        self.data_fetcher.batch_mode = True
        batch_cache_size = 10
        
        # 中断标志（用于跨平台中断处理）
        import threading
        interrupt_flag = threading.Event()
        
        # 添加信号处理，捕获中断信号（Ctrl+C）时保存缓存
        import signal
        import sys
        
        def signal_handler(signum, frame):
            """处理中断信号，设置中断标志"""
            if not interrupt_flag.is_set():
                interrupt_flag.set()
                print("\n\n[中断] 检测到程序中断（Ctrl+C），正在保存已获取的缓存数据...")
        
        # 注册信号处理器（Windows 和 Linux 都支持）
        try:
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, signal_handler)
        except (ValueError, OSError):
            # Windows 上可能不支持某些信号，忽略错误
            pass
        
        # 统计信息
        stats = {
            'success': 0,
            'failed': 0,
            'total': total
        }
        
        # 阶段2：数据加载
        print("\n【阶段2】数据加载")
        print(f"  加载股票数据 ({total} 只)...")
        
        # 使用线程池并行处理，带详细进度显示
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(preload_single_stock, code): code 
                          for code in stock_codes}
                
                # 使用tqdm显示进度
                pbar = tqdm(total=total, desc="  进度", 
                           bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] 成功:{postfix[0]} 失败:{postfix[1]}',
                           postfix=[0, 0], leave=False)
                
                completed = 0
                
                for future in as_completed(futures):
                    # 检查中断标志
                    if interrupt_flag.is_set():
                        print("\n[中断] 检测到中断信号，正在取消剩余任务并保存数据...")
                        # 取消所有未完成的任务
                        for f in futures:
                            f.cancel()
                        break
                    
                    stock_code = futures[future]
                    stock_name = stock_name_map.get(stock_code, "")
                    
                    try:
                        result = future.result(timeout=30)
                        stock_code_result, data = result
                        
                        if data is not None:
                            preloaded_data[stock_code_result] = data
                            stats['success'] += 1
                            status_msg = f"✓ {stock_code_result} {stock_name}: 数据加载成功"
                        else:
                            stats['failed'] += 1
                            status_msg = f"✗ {stock_code_result} {stock_name}: 数据加载失败"
                        
                        # 更新进度条
                        pbar.postfix = [stats['success'], stats['failed']]
                        pbar.update(1)
                        
                        # 批量保存缓存（每10只股票保存一次，静默保存）
                        if completed > 0 and completed % batch_cache_size == 0:
                            try:
                                self.data_fetcher.flush_batch_cache()
                            except Exception as e:
                                pass  # 静默失败，不影响主流程
                        
                    except FutureTimeoutError:
                        stats['failed'] += 1
                        pbar.postfix = [stats['success'], stats['failed']]
                        pbar.update(1)
                    except KeyboardInterrupt:
                        # 设置中断标志
                        interrupt_flag.set()
                        print("\n[中断] 检测到键盘中断（Ctrl+C），正在保存数据...")
                        break
                    except Exception as e:
                        stats['failed'] += 1
                        pbar.postfix = [stats['success'], stats['failed']]
                        pbar.update(1)
                    
                    completed += 1
                
                pbar.close()
                
                # 如果被中断，抛出异常以便上层处理
                if interrupt_flag.is_set():
                    raise KeyboardInterrupt("程序被用户中断")
        except KeyboardInterrupt:
            # 中断时也要保存缓存
            interrupt_flag.set()
            raise
        finally:
            # 确保无论是否异常都会保存缓存并关闭批量模式
            try:
                self.data_fetcher.flush_batch_cache()
            except Exception as e:
                pass  # 静默失败，不影响主流程
            finally:
                # 关闭批量模式
                self.data_fetcher.batch_mode = False
        
        # 显示预加载统计（只有在未中断时显示）
        if not interrupt_flag.is_set():
            print(f"  ✓ 加载完成: 成功 {stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)")
        else:
            print(f"  ✗ 加载被中断: 已处理 {completed}/{stats['total']} (成功 {stats['success']}, 失败 {stats['failed']})")
        
        # 二次重试：对缺失基本面和财务数据的股票进行重试
        if not interrupt_flag.is_set() and len(preloaded_data) > 0:
            retry_stocks = []
            for stock_code, data in preloaded_data.items():
                if data is None:
                    continue
                fundamental_data = data.get('fundamental_data', {})
                financial_data = data.get('financial_data', {})
                
                # 检查基本面数据是否缺失
                pe_ratio = fundamental_data.get('pe_ratio')
                pb_ratio = fundamental_data.get('pb_ratio')
                fundamental_missing = (pe_ratio is None and pb_ratio is None)
                
                # 检查财务数据是否缺失
                roe = financial_data.get('roe')
                financial_missing = (roe is None)
                
                # 如果基本面和财务数据都缺失，加入重试列表
                if fundamental_missing or financial_missing:
                    retry_stocks.append((stock_code, fundamental_missing, financial_missing))
            
            if retry_stocks:
                retry_count = len(retry_stocks)
                print(f"\n【二次重试】对 {retry_count} 只缺失数据的股票进行重试...")
                retry_success = 0
                
                for stock_code, need_fundamental, need_financial in retry_stocks:
                    try:
                        stock_name = stock_name_map.get(stock_code, "")
                        data = preloaded_data.get(stock_code)
                        if data is None:
                            continue
                        
                        # 重试获取基本面数据
                        if need_fundamental:
                            retry_fundamental = self.data_fetcher.get_stock_fundamental(stock_code)
                            if retry_fundamental is not None:
                                data['fundamental_data'] = retry_fundamental
                                retry_success += 1
                        
                        # 重试获取财务数据
                        if need_financial:
                            retry_financial = self.data_fetcher.get_stock_financial(stock_code)
                            if retry_financial is not None:
                                data['financial_data'] = retry_financial
                                if not need_fundamental:  # 避免重复计数
                                    retry_success += 1
                        
                        # 短暂延迟，避免请求过快
                        time.sleep(0.1)
                    except Exception as e:
                        # 静默失败，继续处理下一个
                        pass
                
                if retry_success > 0:
                    print(f"  ✓ 二次重试完成: 成功获取 {retry_success} 只股票的数据")
                    # 保存重试获取的缓存
                    try:
                        self.data_fetcher.flush_batch_cache()
                    except:
                        pass
        
        return preloaded_data
    
    def calculate_scores_from_preloaded_data(self, preloaded_data: Dict[str, Dict], 
                                            stock_name_map: Dict[str, str]) -> List[Dict]:
        """
        基于预加载的数据计算评分（计算阶段）
        Args:
            preloaded_data: 预加载的数据字典
            stock_name_map: 股票名称映射字典
        Returns:
            评估结果列表
        """
        results = []
        total = len(preloaded_data)
        
        # 阶段3：评分计算
        print("\n【阶段3】评分计算")
        print(f"  计算股票评分 ({total} 只)...")
        
        try:
            for stock_code, data in tqdm(preloaded_data.items(), desc="  进度", total=total, leave=False):
                try:
                    stock_name = data.get('stock_name', stock_name_map.get(stock_code, ""))
                    kline_data = data['kline_data']
                    fundamental_data = data['fundamental_data']
                    financial_data = data['financial_data']
                    
                    # 计算各维度得分
                    fundamental_result = self.fundamental_scorer.score(fundamental_data, financial_data)
                    volume_result = self.volume_scorer.score(kline_data)
                    price_result = self.price_scorer.score(kline_data)

                    # 提取综合得分
                    fundamental_score = fundamental_result['score']
                    volume_score = volume_result['score']
                    price_score = price_result['score']

                    # 计算综合得分
                    total_score = (
                        fundamental_score * self.weights['fundamental'] +
                        volume_score * self.weights['volume'] +
                        price_score * self.weights['price']
                    )
                    
                    # 获取当前价格信息
                    current_price = kline_data['close'].iloc[-1] if not kline_data.empty else 0
                    current_volume = kline_data['volume'].iloc[-1] if not kline_data.empty else 0
                    
                    result = {
                        'code': stock_code,
                        'name': stock_name,
                        'score': round(total_score, 2),
                        'total_score': round(total_score, 2),
                        'fundamental_score': round(fundamental_score, 2),
                        'volume_score': round(volume_score, 2),
                        'price_score': round(price_score, 2),
                        'current_price': round(current_price, 2),
                        'current_volume': current_volume,
                        # 基本面详细指标
                        'pe_ratio': fundamental_result.get('pe_ratio'),
                        'pb_ratio': fundamental_result.get('pb_ratio'),
                        'roe': fundamental_result.get('roe'),
                        'revenue_growth': fundamental_result.get('revenue_growth'),
                        'profit_growth': fundamental_result.get('profit_growth'),
                        # 成交量详细指标
                        'volume_ratio': volume_result.get('volume_ratio'),
                        'turnover_rate': volume_result.get('turnover_rate'),
                        'volume_trend': volume_result.get('volume_trend'),
                        # 价格详细指标
                        'price_trend': price_result.get('price_trend'),
                        'price_position': price_result.get('price_position'),
                        'volatility': price_result.get('volatility'),
                        # 子维度得分（用于详细展示）
                        'pe_ratio_score': fundamental_result.get('pe_ratio_score', 50),
                        'pb_ratio_score': fundamental_result.get('pb_ratio_score', 50),
                        'roe_score': fundamental_result.get('roe_score', 50),
                        'revenue_growth_score': fundamental_result.get('revenue_growth_score', 50),
                        'profit_growth_score': fundamental_result.get('profit_growth_score', 50),
                        'volume_ratio_score': volume_result.get('volume_ratio_score', 50),
                        'turnover_rate_score': volume_result.get('turnover_rate_score', 50),
                        'volume_trend_score': volume_result.get('volume_trend_score', 50),
                        'price_trend_score': price_result.get('price_trend_score', 50),
                        'price_position_score': price_result.get('price_position_score', 50),
                        'volatility_score': price_result.get('volatility_score', 50),
                    }
                    
                    results.append(result)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"计算 {stock_code} {stock_name_map.get(stock_code, '')} 评分时出错: {e}")
                    continue
        except KeyboardInterrupt:
            print(f"\n  ✗ 计算被中断，已计算 {len(results)} 只股票的评分")
            raise
        
        print(f"  ✓ 计算完成: 共 {len(results)} 只股票")
        
        return results
    
    def select_top_stocks(self, stock_codes: List[str] = None, top_n: int = 20, 
                         board_types: List[str] = None, max_workers: int = 5) -> pd.DataFrame:
        """
        选择TOP股票（支持多线程）
        Args:
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票
            board_types: 板块类型列表，如 ['main', 'gem']，None表示所有板块
            max_workers: 最大线程数（默认5，避免请求过快）
        Returns:
            TOP股票DataFrame
        """
        if stock_codes is None:
            # 如果没有指定板块类型，默认使用主板
            if board_types is None:
                board_types = ['main']
            # 获取股票代码（支持板块筛选）
            stock_codes = self.data_fetcher.get_all_stock_codes(board_types)
            # 确保所有代码都是字符串类型
            stock_codes = [str(code) for code in stock_codes]
            print(f"\n【股票筛选】")
            print(f"  获取到 {len(stock_codes)} 只股票（板块: {board_types}）")
            if 'main' in board_types:
                # 统计主板股票分布
                shanghai_main = len([c for c in stock_codes if str(c).startswith('60')])
                shenzhen_main = len([c for c in stock_codes if str(c).startswith('00')])
                print(f"  其中：上证主板 {shanghai_main} 只，深圳主板 {shenzhen_main} 只")
        
        # 准备股票名称映射
        # 优化：确保股票列表已加载（延迟加载）
        if self.data_fetcher.stock_list is None or self.data_fetcher.stock_list.empty:
            self.data_fetcher._load_stock_list()
        stock_info = self.data_fetcher.stock_list
        stock_name_map = {}
        if stock_info is not None and not stock_info.empty:
            for _, row in stock_info.iterrows():
                # 确保代码格式一致（转换为字符串并去除前导零等）
                code = str(row['code']).zfill(6)  # 确保是6位数字
                name = str(row['name']).strip()  # 去除空格
                stock_name_map[code] = name
                # 也支持不带前导零的格式
                stock_name_map[str(int(code))] = name
        
        # 过滤ST股票
        def is_st_stock(stock_code: str) -> bool:
            """判断是否为ST股票"""
            stock_name = stock_name_map.get(stock_code, "")
            if not stock_name:
                return False
            # ST股票名称通常包含"ST"或"*ST"
            return 'ST' in stock_name or '*ST' in stock_name
        
        # 剔除ST股票
        filtered_stock_codes = [code for code in stock_codes if not is_st_stock(code)]
        st_count = len(stock_codes) - len(filtered_stock_codes)
        if st_count > 0:
            print(f"  已剔除 {st_count} 只ST股票")
        stock_codes = filtered_stock_codes
        total = len(stock_codes)
        
        # 预加载所有数据（数据获取阶段）
        preloaded_data = self.preload_all_data(stock_codes, stock_name_map, max_workers)
        
        if not preloaded_data:
            print("\n【错误】")
            print("  没有成功预加载任何数据，无法进行计算")
            return pd.DataFrame()
        
        # 基于预加载的数据计算评分（计算阶段）
        results = self.calculate_scores_from_preloaded_data(preloaded_data, stock_name_map)
        
        # 数据可用性统计（用于动态调整权重）
        data_availability = {
            'fundamental': {'available': 0, 'total': 0},
            'financial': {'available': 0, 'total': 0},
        }
        
        def collect_data_availability(results_list: List[Dict]):
            """收集数据可用性统计"""
            for result in results_list:
                # 统计基本面数据可用性
                data_availability['fundamental']['total'] += 1
                pe_ratio = result.get('pe_ratio')
                pb_ratio = result.get('pb_ratio')
                # 改进：区分None（数据缺失）和0（数据为0，如亏损股）
                # 如果至少有一个不是None（包括0），视为有数据
                if pe_ratio is not None or pb_ratio is not None:
                    data_availability['fundamental']['available'] += 1
                
                # 统计财务数据可用性
                data_availability['financial']['total'] += 1
                roe = result.get('roe')
                # 改进：区分None（数据缺失）和0（数据为0）
                # 如果roe不是None（包括0），视为有数据
                if roe is not None:
                    data_availability['financial']['available'] += 1
                
        
        def adjust_weights_by_availability(availability_stats: Dict) -> Dict:
            """
            根据数据可用性动态调整权重
            如果所有股票都缺失某个指标，则不赋予权重
            如果部分股票有、部分没有，等待所有股票获取完成后再决定
            """
            adjusted_weights = self.weights.copy()
            total_stocks = availability_stats['fundamental']['total']
            
            if total_stocks == 0:
                return adjusted_weights
            
            # 检查各维度数据可用性
            fundamental_ratio = availability_stats['fundamental']['available'] / total_stocks if total_stocks > 0 else 0
            financial_ratio = availability_stats['financial']['available'] / total_stocks if total_stocks > 0 else 0
            
            # 如果所有股票都缺失某个指标，权重设为0
            if fundamental_ratio == 0:
                adjusted_weights['fundamental'] = 0
                print(f"  ⚠ 警告: 所有股票都缺失基本面数据，已移除基本面权重")
            
            if financial_ratio == 0:
                adjusted_weights['financial'] = 0
                print(f"  ⚠ 警告: 所有股票都缺失财务数据，已移除财务权重")
            
            
            # 重新归一化权重（确保总和为1）
            total_weight = sum(adjusted_weights.values())
            if total_weight > 0:
                for key in adjusted_weights:
                    adjusted_weights[key] = adjusted_weights[key] / total_weight
            else:
                # 如果所有权重都为0，使用默认权重
                print("  ⚠ 警告: 所有权重都为0，使用默认权重")
                adjusted_weights = self.weights.copy()
            
            return adjusted_weights
        
        # 收集数据可用性统计
        if results:
            collect_data_availability(results)
            
            # 根据数据可用性动态调整权重
            fundamental_ratio = data_availability['fundamental']['available']/data_availability['fundamental']['total']*100 if data_availability['fundamental']['total'] > 0 else 0
            financial_ratio = data_availability['financial']['available']/data_availability['financial']['total']*100 if data_availability['financial']['total'] > 0 else 0
            print(f"\n【数据可用性】")
            print(f"  基本面: {data_availability['fundamental']['available']}/{data_availability['fundamental']['total']} ({fundamental_ratio:.1f}%)")
            print(f"  财务: {data_availability['financial']['available']}/{data_availability['financial']['total']} ({financial_ratio:.1f}%)")
            
            # 动态调整权重并重新计算得分
            adjusted_weights = adjust_weights_by_availability(data_availability)
            # 保存调整后的权重，供主程序访问
            self._last_adjusted_weights = adjusted_weights.copy()
            if adjusted_weights != self.weights:
                # 使用调整后的权重重新计算得分
                print("\n【权重调整】")
                print("  根据数据可用性调整权重并重新计算得分...")
                for result in results:
                    # 重新计算综合得分
                    total_score = (
                        (result.get('fundamental_score') or 0) * adjusted_weights['fundamental'] +
                        (result.get('volume_score') or 0) * adjusted_weights['volume'] +
                        (result.get('price_score') or 0) * adjusted_weights['price']
                    )
                    result['score'] = round(total_score, 2)
                    result['total_score'] = round(total_score, 2)
            else:
                # 即使没有调整，也保存当前权重
                self._last_adjusted_weights = self.weights.copy()
        
        if not results:
            print("\n【结果】")
            print("  未找到符合条件的股票")
            return pd.DataFrame()
        
        # 转换为DataFrame并排序
        df = pd.DataFrame(results)
        
        # 确保name列存在且不为空，如果为空则从stock_name_map补充
        if 'name' in df.columns:
            for idx, row in df.iterrows():
                if pd.isna(row['name']) or str(row['name']).strip() == '':
                    code = str(row['code']).zfill(6)
                    df.at[idx, 'name'] = stock_name_map.get(code, stock_name_map.get(str(int(code)), ''))
        
        # 使用score字段排序（策略基类要求）
        sort_column = 'score' if 'score' in df.columns else 'total_score'
        df = df.sort_values(sort_column, ascending=False)
        df = df.head(top_n)
        
        # 重置索引
        df.reset_index(drop=True, inplace=True)
        df.index = df.index + 1  # 从1开始编号
        
        # 确保列顺序：code, name在前
        if 'code' in df.columns and 'name' in df.columns:
            cols = ['code', 'name'] + [col for col in df.columns if col not in ['code', 'name']]
            df = df[cols]
        
        return df

