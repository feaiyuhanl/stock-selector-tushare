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
    SectorScorer,
    ConceptScorer
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
        self.sector_scorer = SectorScorer()
        self.concept_scorer = ConceptScorer()
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
            
            # 4. 获取板块和概念信息（带缓存）
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取板块概念信息...")
            sectors = self.data_fetcher.get_stock_sectors(stock_code)
            concepts = self.data_fetcher.get_stock_concepts(stock_code)
            
            # 5. 获取板块K线数据（实时数据，不缓存）
            # 优化：减少板块K线获取，只取1个最重要的板块，避免过多请求
            sector_kline_list = []
            if sectors:
                try:
                    sector_kline = self.data_fetcher.get_sector_kline(sectors[0])  # 只取第一个板块
                    if sector_kline is not None:
                        sector_kline_list.append(sector_kline)
                except:
                    pass  # 板块K线获取失败不影响评分
            
            # 6. 获取概念K线数据（实时数据，不缓存）
            # 优化：减少概念K线获取，只取1个最重要的概念，避免过多请求
            concept_kline_list = []
            if concepts:
                try:
                    concept_kline = self.data_fetcher.get_concept_kline(concepts[0])  # 只取第一个概念
                    if concept_kline is not None:
                        concept_kline_list.append(concept_kline)
                except:
                    pass  # 概念K线获取失败不影响评分
            
            # 7. 计算各维度得分
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 计算评分...")
            fundamental_score = self.fundamental_scorer.score(fundamental_data, financial_data)
            volume_score = self.volume_scorer.score(kline_data)
            price_score = self.price_scorer.score(kline_data)
            sector_score = self.sector_scorer.score(sector_kline_list, kline_data)
            concept_score = self.concept_scorer.score(concept_kline_list, kline_data)
            
            # 8. 计算综合得分
            total_score = (
                fundamental_score * self.weights['fundamental'] +
                volume_score * self.weights['volume'] +
                price_score * self.weights['price'] +
                sector_score * self.weights['sector'] +
                concept_score * self.weights['concept']
            )
            
            # 9. 获取当前价格信息
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
                'sector_score': round(sector_score, 2),
                'concept_score': round(concept_score, 2),
                'current_price': round(current_price, 2),
                'current_volume': current_volume,
                'pe_ratio': fundamental_data.get('pe_ratio', 0),
                'pb_ratio': fundamental_data.get('pb_ratio', 0),
                'roe': financial_data.get('roe', 0),
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
            预加载的数据字典，格式为 {stock_code: {kline_data, fundamental_data, financial_data, sectors, concepts, sector_kline_list, concept_kline_list}}
        """
        preloaded_data = {}
        total = len(stock_codes)
        
        print(f"\n开始预加载 {total} 只股票的数据（使用 {max_workers} 个线程）...")
        print("=" * 60)
        
        def preload_single_stock(stock_code: str) -> tuple:
            """预加载单只股票的数据（用于多线程）"""
            stock_name = stock_name_map.get(stock_code, "")
            try:
                # 1. 获取K线数据
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
                
                # 4. 获取板块和概念信息（带缓存）
                sectors = self.data_fetcher.get_stock_sectors(stock_code)
                concepts = self.data_fetcher.get_stock_concepts(stock_code)
                
                # 5. 获取板块K线数据（实时数据，不缓存）
                sector_kline_list = []
                if sectors:
                    try:
                        sector_kline = self.data_fetcher.get_sector_kline(sectors[0])
                        if sector_kline is not None:
                            sector_kline_list.append(sector_kline)
                    except:
                        pass
                
                # 6. 获取概念K线数据（实时数据，不缓存）
                concept_kline_list = []
                if concepts:
                    try:
                        concept_kline = self.data_fetcher.get_concept_kline(concepts[0])
                        if concept_kline is not None:
                            concept_kline_list.append(concept_kline)
                    except:
                        pass
                
                data = {
                    'kline_data': kline_data,
                    'fundamental_data': fundamental_data,
                    'financial_data': financial_data,
                    'sectors': sectors,
                    'concepts': concepts,
                    'sector_kline_list': sector_kline_list,
                    'concept_kline_list': concept_kline_list,
                    'stock_name': stock_name
                }
                
                return (stock_code, data)
            except Exception as e:
                return (stock_code, None)
        
        # 启用批量缓存模式
        self.data_fetcher.batch_mode = True
        batch_cache_size = 10
        
        # 添加信号处理，捕获中断信号（Ctrl+C）时保存缓存
        import signal
        import sys
        
        def signal_handler(signum, frame):
            """处理中断信号，保存缓存后退出"""
            print("\n\n[中断] 检测到程序中断，正在保存已获取的缓存数据...")
            try:
                saved_count = self.data_fetcher.flush_batch_cache()
                if saved_count > 0:
                    print(f"[缓存更新] 已保存 {saved_count} 只股票的缓存数据")
                print("[中断] 缓存已保存，程序退出")
            except Exception as e:
                print(f"[警告] 保存缓存失败: {e}")
            finally:
                self.data_fetcher.batch_mode = False
                sys.exit(0)
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        # 统计信息
        stats = {
            'success': 0,
            'failed': 0,
            'total': total
        }
        
        # 使用线程池并行处理，带详细进度显示
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(preload_single_stock, code): code 
                          for code in stock_codes}
                
                # 使用tqdm显示进度
                pbar = tqdm(total=total, desc="数据预加载进度", 
                           bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] 成功:{postfix[0]} 失败:{postfix[1]}',
                           postfix=[0, 0])
                
                completed = 0
                
                for future in as_completed(futures):
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
                        pbar.set_description(f"数据预加载进度 - 当前: {stock_code_result} {stock_name[:10]}")
                        pbar.update(1)
                        
                        # 每10个显示一次详细信息
                        if completed % 10 == 0:
                            print(f"\n进度: {completed+1}/{total} | 成功: {stats['success']} | 失败: {stats['failed']} | {status_msg}")
                        
                        # 批量保存缓存（每10只股票保存一次）
                        if completed > 0 and completed % batch_cache_size == 0:
                            try:
                                saved_count = self.data_fetcher.flush_batch_cache()
                                if saved_count > 0:
                                    print(f"\n[缓存更新] 已批量保存 {saved_count} 只股票的缓存数据")
                            except Exception as e:
                                print(f"\n[警告] 批量保存缓存失败: {e}")
                        
                    except FutureTimeoutError:
                        stats['failed'] += 1
                        error_msg = f"✗ {stock_code} {stock_name}: 超时（>30秒）"
                        pbar.postfix = [stats['success'], stats['failed']]
                        pbar.update(1)
                        if completed % 10 == 0:
                            print(f"\n进度: {completed+1}/{total} | 成功: {stats['success']} | 失败: {stats['failed']} | {error_msg}")
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        stats['failed'] += 1
                        error_msg = f"✗ {stock_code} {stock_name}: 异常 - {str(e)[:50]}"
                        pbar.postfix = [stats['success'], stats['failed']]
                        pbar.update(1)
                        if completed % 10 == 0:
                            print(f"\n进度: {completed+1}/{total} | 成功: {stats['success']} | 失败: {stats['failed']} | {error_msg}")
                    
                    completed += 1
                
                pbar.close()
        finally:
            # 确保无论是否异常都会保存缓存并关闭批量模式
            try:
                saved_count = self.data_fetcher.flush_batch_cache()
                if saved_count > 0:
                    print(f"\n[缓存更新] 已保存剩余 {saved_count} 只股票的缓存数据")
            except Exception as e:
                print(f"\n[警告] 保存剩余缓存失败: {e}")
            finally:
                # 关闭批量模式
                self.data_fetcher.batch_mode = False
        
        # 显示预加载统计
        print("\n" + "=" * 60)
        print(f"数据预加载完成！")
        print(f"总计: {stats['total']} 只股票")
        print(f"成功: {stats['success']} 只 ({stats['success']/stats['total']*100:.1f}%)")
        print(f"失败: {stats['failed']} 只 ({stats['failed']/stats['total']*100:.1f}%)")
        print("=" * 60)
        
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
        
        print(f"\n开始计算 {total} 只股票的评分...")
        print("=" * 60)
        
        for stock_code, data in tqdm(preloaded_data.items(), desc="计算评分进度", total=total):
            try:
                stock_name = data.get('stock_name', stock_name_map.get(stock_code, ""))
                kline_data = data['kline_data']
                fundamental_data = data['fundamental_data']
                financial_data = data['financial_data']
                sector_kline_list = data['sector_kline_list']
                concept_kline_list = data['concept_kline_list']
                
                # 计算各维度得分
                fundamental_score = self.fundamental_scorer.score(fundamental_data, financial_data)
                volume_score = self.volume_scorer.score(kline_data)
                price_score = self.price_scorer.score(kline_data)
                sector_score = self.sector_scorer.score(sector_kline_list, kline_data)
                concept_score = self.concept_scorer.score(concept_kline_list, kline_data)
                
                # 计算综合得分
                total_score = (
                    fundamental_score * self.weights['fundamental'] +
                    volume_score * self.weights['volume'] +
                    price_score * self.weights['price'] +
                    sector_score * self.weights['sector'] +
                    concept_score * self.weights['concept']
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
                    'sector_score': round(sector_score, 2),
                    'concept_score': round(concept_score, 2),
                    'current_price': round(current_price, 2),
                    'current_volume': current_volume,
                    'pe_ratio': fundamental_data.get('pe_ratio', 0),
                    'pb_ratio': fundamental_data.get('pb_ratio', 0),
                    'roe': financial_data.get('roe', 0),
                }
                
                results.append(result)
            except Exception as e:
                print(f"计算 {stock_code} {stock_name_map.get(stock_code, '')} 评分时出错: {e}")
                continue
        
        print(f"\n评分计算完成！共计算 {len(results)} 只股票的评分")
        print("=" * 60)
        
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
            print(f"\n获取到 {len(stock_codes)} 只股票（板块: {board_types}）")
            if 'main' in board_types:
                # 统计主板股票分布
                shanghai_main = len([c for c in stock_codes if str(c).startswith('60')])
                shenzhen_main = len([c for c in stock_codes if str(c).startswith('00')])
                print(f"  其中：上证主板 {shanghai_main} 只，深圳主板 {shenzhen_main} 只")
        
        # 准备股票名称映射
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
            print(f"已剔除 {st_count} 只ST股票")
        stock_codes = filtered_stock_codes
        total = len(stock_codes)
        
        # 步骤1: 预加载所有数据（数据获取阶段）
        print("\n" + "=" * 60)
        print("步骤1: 数据预加载阶段")
        print("=" * 60)
        preloaded_data = self.preload_all_data(stock_codes, stock_name_map, max_workers)
        
        if not preloaded_data:
            print("没有成功预加载任何数据，无法进行计算")
            return pd.DataFrame()
        
        # 步骤2: 基于预加载的数据计算评分（计算阶段）
        print("\n" + "=" * 60)
        print("步骤2: 评分计算阶段")
        print("=" * 60)
        results = self.calculate_scores_from_preloaded_data(preloaded_data, stock_name_map)
        
        # 数据可用性统计（用于动态调整权重）
        data_availability = {
            'fundamental': {'available': 0, 'total': 0},
            'financial': {'available': 0, 'total': 0},
            'sector': {'available': 0, 'total': 0},
            'concept': {'available': 0, 'total': 0},
        }
        
        def collect_data_availability(results_list: List[Dict]):
            """收集数据可用性统计"""
            for result in results_list:
                # 统计基本面数据可用性
                data_availability['fundamental']['total'] += 1
                if result.get('pe_ratio', 0) > 0 or result.get('pb_ratio', 0) > 0:
                    data_availability['fundamental']['available'] += 1
                
                # 统计财务数据可用性
                data_availability['financial']['total'] += 1
                if result.get('roe', 0) != 0:
                    data_availability['financial']['available'] += 1
                
                # 统计板块数据可用性（检查是否有板块K线数据）
                data_availability['sector']['total'] += 1
                if result.get('sector_score', 0) != 0 and result.get('sector_score', 0) != 50:  # 50是默认分
                    data_availability['sector']['available'] += 1
                
                # 统计概念数据可用性（检查是否有概念K线数据）
                data_availability['concept']['total'] += 1
                if result.get('concept_score', 0) != 0 and result.get('concept_score', 0) != 50:  # 50是默认分
                    data_availability['concept']['available'] += 1
        
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
            sector_ratio = availability_stats['sector']['available'] / total_stocks if total_stocks > 0 else 0
            concept_ratio = availability_stats['concept']['available'] / total_stocks if total_stocks > 0 else 0
            
            # 如果所有股票都缺失某个指标，权重设为0
            if fundamental_ratio == 0:
                adjusted_weights['fundamental'] = 0
                print(f"  警告: 所有股票都缺失基本面数据，已移除基本面权重")
            
            if financial_ratio == 0:
                adjusted_weights['financial'] = 0
                print(f"  警告: 所有股票都缺失财务数据，已移除财务权重")
            
            if sector_ratio == 0:
                adjusted_weights['sector'] = 0
                print(f"  警告: 所有股票都缺失板块数据，已移除板块权重")
            
            if concept_ratio == 0:
                adjusted_weights['concept'] = 0
                print(f"  警告: 所有股票都缺失概念数据，已移除概念权重")
            
            # 重新归一化权重（确保总和为1）
            total_weight = sum(adjusted_weights.values())
            if total_weight > 0:
                for key in adjusted_weights:
                    adjusted_weights[key] = adjusted_weights[key] / total_weight
            else:
                # 如果所有权重都为0，使用默认权重
                print("  警告: 所有权重都为0，使用默认权重")
                adjusted_weights = self.weights.copy()
            
            return adjusted_weights
        
        # 收集数据可用性统计
        if results:
            collect_data_availability(results)
            
            # 根据数据可用性动态调整权重
            print("\n" + "=" * 60)
            print("数据可用性统计:")
            print(f"  基本面数据: {data_availability['fundamental']['available']}/{data_availability['fundamental']['total']} ({data_availability['fundamental']['available']/data_availability['fundamental']['total']*100:.1f}%)")
            print(f"  财务数据: {data_availability['financial']['available']}/{data_availability['financial']['total']} ({data_availability['financial']['available']/data_availability['financial']['total']*100:.1f}%)")
            print(f"  板块数据: {data_availability['sector']['available']}/{data_availability['sector']['total']} ({data_availability['sector']['available']/data_availability['sector']['total']*100:.1f}%)")
            print(f"  概念数据: {data_availability['concept']['available']}/{data_availability['concept']['total']} ({data_availability['concept']['available']/data_availability['concept']['total']*100:.1f}%)")
            print("=" * 60)
            
            # 动态调整权重并重新计算得分
            adjusted_weights = adjust_weights_by_availability(data_availability)
            # 保存调整后的权重，供主程序访问
            self._last_adjusted_weights = adjusted_weights.copy()
            if adjusted_weights != self.weights:
                print("\n根据数据可用性动态调整权重:")
                for key in self.weights:
                    if self.weights[key] != adjusted_weights[key]:
                        print(f"  {key}: {self.weights[key]:.3f} -> {adjusted_weights[key]:.3f}")
                
                # 使用调整后的权重重新计算得分
                print("\n使用调整后的权重重新计算得分...")
                for result in results:
                    # 重新计算综合得分
                    total_score = (
                        result.get('fundamental_score', 0) * adjusted_weights['fundamental'] +
                        result.get('volume_score', 0) * adjusted_weights['volume'] +
                        result.get('price_score', 0) * adjusted_weights['price'] +
                        result.get('sector_score', 0) * adjusted_weights['sector'] +
                        result.get('concept_score', 0) * adjusted_weights['concept']
                    )
                    result['score'] = round(total_score, 2)
                    result['total_score'] = round(total_score, 2)
            else:
                # 即使没有调整，也保存当前权重
                self._last_adjusted_weights = self.weights.copy()
        
        if not results:
            print("未找到符合条件的股票")
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

