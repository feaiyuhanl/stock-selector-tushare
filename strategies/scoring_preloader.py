"""
打分策略预加载器：批量数据预加载和评分计算
"""
import pandas as pd
import time
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from tqdm import tqdm
import signal
import sys
import threading
import config


class ScoringPreloader:
    """打分策略预加载器"""
    
    def __init__(self, data_fetcher, evaluator):
        """
        初始化预加载器
        Args:
            data_fetcher: 数据获取器
            evaluator: 评估器实例
        """
        self.data_fetcher = data_fetcher
        self.evaluator = evaluator
    
    def preload_all_data(self, stock_codes: List[str], stock_name_map: Dict[str, str],
                        max_workers: int = None) -> Dict[str, Dict]:
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
                
                # 收盘后强制刷新：即使缓存判断为"最新"，收盘后也应该重新获取最新价格
                # 这是一个兜底保障，确保获取收盘后的最新价格
                from datetime import datetime, time
                from data.utils import AFTERNOON_END
                current_time = datetime.now().time()
                weekday = datetime.now().weekday()
                is_after_market_close = (weekday < 5 and current_time >= AFTERNOON_END)
                
                if is_after_market_close and latest_stocks:
                    # 收盘后，将"最新"的股票也标记为需要更新，确保获取收盘后的最新价格
                    print(f"  [收盘后刷新] 收盘后检测到 {len(latest_stocks)} 只股票缓存为最新，强制刷新以确保获取收盘价")
                    outdated_stocks.extend(latest_stocks)
                    latest_stocks = []
                
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
        interrupt_flag = threading.Event()
        
        # 添加信号处理，捕获中断信号（Ctrl+C）时保存缓存
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
        
        # 如果max_workers为None，使用配置中的默认值
        if max_workers is None:
            max_workers = config.DEFAULT_MAX_WORKERS
        
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
                print(f"\n【二次重试】对 {retry_count} 只缺失数据的股票进行重试（并行 2 线程）...")
                retry_success = 0
                retry_workers = min(2, retry_count)  # 控制并发，避免 Tushare 限频

                def _retry_single(item):
                    stock_code, need_fundamental, need_financial = item
                    data = preloaded_data.get(stock_code)
                    if data is None:
                        return 0
                    got_any = False
                    try:
                        if need_fundamental:
                            retry_fundamental = self.data_fetcher.get_stock_fundamental(stock_code)
                            if retry_fundamental is not None:
                                data['fundamental_data'] = retry_fundamental
                                got_any = True
                        if need_financial:
                            retry_financial = self.data_fetcher.get_stock_financial(stock_code)
                            if retry_financial is not None:
                                data['financial_data'] = retry_financial
                                got_any = True
                        if got_any:
                            time.sleep(0.05)  # 轻量间隔，配合限频
                    except Exception:
                        pass
                    return 1 if got_any else 0

                with ThreadPoolExecutor(max_workers=retry_workers) as retry_executor:
                    for n in retry_executor.map(_retry_single, retry_stocks):
                        retry_success += n

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
                    
                    # 使用评估器计算得分
                    result = self.evaluator.calculate_score_from_data(
                        kline_data, fundamental_data, financial_data, stock_code, stock_name
                    )
                    
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

