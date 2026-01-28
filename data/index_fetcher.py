"""
指数权重数据获取模块
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .utils import get_analysis_date


class IndexFetcher:
    """指数权重数据获取器"""
    
    def __init__(self, base):
        """
        初始化指数权重数据获取器
        Args:
            base: FetcherBase实例，提供基础功能
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
        获取指数权重数据
        Args:
            index_code: 指数代码，如 '000300.SH' (沪深300), '000905.SH' (中证500), '932000.CSI' (中证2000)
            trade_date: 交易日期，格式：YYYYMMDD，如果指定则只获取该日期的数据
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            force_refresh: 是否强制刷新缓存
        Returns:
            DataFrame包含以下列：
            - index_code: 指数代码
            - trade_date: 交易日期
            - con_code: 成分股代码
            - weight: 权重（百分比）
        """
        # 标准化日期格式
        if trade_date:
            trade_date = trade_date.replace('-', '')
        if start_date:
            start_date = start_date.replace('-', '')
        if end_date:
            end_date = end_date.replace('-', '')
        
        # 智能检查：如果最新交易日数据已存在，直接返回，无需下载（类似K线数据的处理方式）
        if not force_refresh and self.base.cache_manager.has_latest_trading_day_data_index_weight(index_code):
            cached_data = self.base.cache_manager.get_index_weight(
                index_code=index_code,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
                force_refresh=False
            )
            if cached_data is not None and not cached_data.empty:
                if self.base.progress_callback:
                    self.base.progress_callback('cached', f"{index_code}: 最新交易日数据已存在，跳过下载")
                return cached_data
        
        # 从API获取数据（支持分页）
        def fetch_index_weight():
            try:
                limit = 5000  # 每页最多5000条
                offset = 0
                all_data = []
                first_page = True
                
                while True:
                    # 构建API调用参数
                    api_params = {'index_code': index_code}
                    
                    if trade_date:
                        api_params['trade_date'] = trade_date
                    elif start_date and end_date:
                        api_params['start_date'] = start_date
                        api_params['end_date'] = end_date
                    elif start_date:
                        # 使用 get_analysis_date() 获取正确的分析日期作为结束日期
                        analysis_date = get_analysis_date()
                        end_date_str = analysis_date.strftime('%Y%m%d')
                        api_params['start_date'] = start_date
                        api_params['end_date'] = end_date_str
                    else:
                        # 获取最新的数据：使用 get_analysis_date() 获取正确的交易日期
                        analysis_date = get_analysis_date()
                        trade_date_str = analysis_date.strftime('%Y%m%d')
                        api_params['trade_date'] = trade_date_str
                    
                    # 添加limit和offset参数（支持分页）
                    api_params['limit'] = limit
                    api_params['offset'] = offset
                    
                    # 调用API
                    df_page = self.base.pro.index_weight(**api_params)
                    
                    # 如果返回空，说明已经获取完所有数据
                    if df_page is None or df_page.empty:
                        # 如果是第一页就返回空，可能是真的没有数据
                        if first_page:
                            # 尝试获取前一个交易日的数据（仅当使用trade_date时）
                            if not trade_date and not start_date:
                                # 使用 get_analysis_date() 获取分析日期，然后往前推一个交易日
                                analysis_date = get_analysis_date()
                                # 往前推1-3天，找到前一个交易日
                                for days_back in range(1, 4):
                                    prev_date = analysis_date - timedelta(days=days_back)
                                    # 简单判断：跳过周末
                                    if prev_date.weekday() < 5:  # 周一到周五
                                        prev_date_str = prev_date.strftime('%Y%m%d')
                                        df_prev = self.base.pro.index_weight(
                                            index_code=index_code,
                                            trade_date=prev_date_str,
                                            limit=limit,
                                            offset=0
                                        )
                                        if df_prev is not None and not df_prev.empty:
                                            all_data.append(df_prev)
                                            break
                                if all_data:  # 如果找到了数据，退出循环
                                    break
                        break
                    
                    all_data.append(df_page)
                    first_page = False
                    
                    # 如果返回的数据少于limit，说明已经是最后一页
                    if len(df_page) < limit:
                        break
                    
                    # 更新offset，准备获取下一页
                    offset += limit
                    
                    # 添加请求间隔，避免请求过快
                    self.base._wait_before_request()
                
                # 合并所有分页数据
                if not all_data:
                    return None
                
                # 合并所有数据
                df = pd.concat(all_data, ignore_index=True) if len(all_data) > 1 else all_data[0]
                
                if df is None or df.empty:
                    return None
                
                # 如果使用了分页，显示获取的页数
                if len(all_data) > 1:
                    print(f"[提示] {index_code} 分页获取完成: {len(all_data)} 页，共 {len(df)} 条数据")
                
                # 确保列名标准化（tushare可能返回不同的列名）
                # 可能的列名：con_code, code, ts_code等
                if 'con_code' not in df.columns:
                    if 'code' in df.columns:
                        df = df.rename(columns={'code': 'con_code'})
                    elif 'ts_code' in df.columns:
                        df = df.rename(columns={'ts_code': 'con_code'})
                    else:
                        print(f"[警告] {index_code} 数据中未找到成分股代码列，可用列: {df.columns.tolist()}")
                        return None
                
                # 确保trade_date列存在
                if 'trade_date' not in df.columns:
                    if 'date' in df.columns:
                        df = df.rename(columns={'date': 'trade_date'})
                    else:
                        print(f"[警告] {index_code} 数据中未找到交易日期列，可用列: {df.columns.tolist()}")
                        return None
                
                # 确保weight列存在
                if 'weight' not in df.columns:
                    print(f"[警告] {index_code} 数据中未找到权重列，可用列: {df.columns.tolist()}")
                    return None
                
                # 标准化股票代码格式（移除市场后缀，确保6位数字）
                if 'con_code' in df.columns:
                    # 移除市场后缀（如.SH, .SZ等）
                    df['con_code'] = df['con_code'].astype(str).str.replace(r'\.(SH|SZ|BJ)$', '', regex=True)
                    df['con_code'] = df['con_code'].astype(str).str.zfill(6)
                
                # 标准化日期格式
                if 'trade_date' in df.columns:
                    df['trade_date'] = df['trade_date'].astype(str).str.replace('-', '')
                
                # 如果指定了trade_date，只保留该日期的数据
                # 如果指定了start_date和end_date，保留整个日期范围的数据（用于历史趋势分析）
                # 只有在没有指定任何日期参数时，才只保留最新日期的数据
                if trade_date:
                    # 指定了具体日期，只保留该日期的数据
                    if 'trade_date' in df.columns and not df.empty:
                        df = df[df['trade_date'] == trade_date].copy()
                elif not start_date and not end_date:
                    # 没有指定日期范围，只保留最新日期的数据（避免重复）
                    if 'trade_date' in df.columns and not df.empty:
                        latest_date = df['trade_date'].max()
                        df = df[df['trade_date'] == latest_date].copy()
                        
                        # 验证返回的日期是否合理
                        analysis_date = get_analysis_date()
                        analysis_date_str = analysis_date.strftime('%Y%m%d')
                        if latest_date < analysis_date_str:
                            days_diff = (datetime.strptime(analysis_date_str, '%Y%m%d') - 
                                       datetime.strptime(latest_date, '%Y%m%d')).days
                            if days_diff > 5:  # 如果超过5天，发出警告
                                print(f"[警告] {index_code} API返回的交易日期 {latest_date} 比预期日期 {analysis_date_str} 早 {days_diff} 天")
                                print(f"      这可能是正常的（指数权重数据可能有更新延迟），但请确认数据是否满足需求")
                        else:
                            print(f"[提示] {index_code} 未指定日期范围，已筛选为最新日期 {latest_date} 的数据")
                # 如果指定了start_date和end_date，保留整个日期范围的数据，不做筛选
                
                # 去重：确保同一日期、同一股票只有一条记录
                if not df.empty and 'trade_date' in df.columns and 'con_code' in df.columns:
                    before_count = len(df)
                    df = df.drop_duplicates(subset=['trade_date', 'con_code'], keep='last')
                    after_count = len(df)
                    if before_count != after_count:
                        print(f"[提示] {index_code} 数据去重: {before_count} -> {after_count} 条")
                
                # 保存到缓存
                if not df.empty:
                    self.base.cache_manager.save_index_weight(index_code, df)
                    
                    # 统计信息
                    unique_stocks = df['con_code'].nunique() if 'con_code' in df.columns else 0
                    unique_dates = df['trade_date'].nunique() if 'trade_date' in df.columns else 0
                    
                    if self.base.progress_callback:
                        self.base.progress_callback('fetched', f"{index_code}: 已获取权重数据 ({len(df)} 条，{unique_dates} 个交易日，{unique_stocks} 只股票)")
                    else:
                        print(f"[提示] {index_code}: 已获取权重数据 ({len(df)} 条，{unique_dates} 个交易日，{unique_stocks} 只股票)")
                    
                    # 检查数据完整性
                    if 'con_code' in df.columns:
                        expected_counts = {
                            '000300.SH': 300,
                            '000905.SH': 500,
                            '932000.CSI': 2000  # 中证2000（跨市场指数）
                        }
                        if index_code in expected_counts:
                            expected = expected_counts[index_code]
                            if abs(unique_stocks - expected) > expected * 0.1:
                                if unique_stocks < expected * 0.5:
                                    print(f"[警告] {index_code} 成分股数量不足: 实际 {unique_stocks} 只，预期约 {expected} 只")
                                    print(f"      可能原因: 1) API返回数据不完整 2) 需要分页获取 3) 数据源限制")
                
                return df
                
            except Exception as e:
                error_msg = str(e)
                if "权限" in error_msg or "积分" in error_msg or "token" in error_msg.lower():
                    print(f"[警告] 获取指数权重数据失败 ({index_code}): {error_msg}")
                    print(f"[提示] 可能需要更高的积分权限才能调用 index_weight 接口")
                else:
                    print(f"[错误] 获取指数权重数据失败 ({index_code}): {error_msg}")
                return None
        
        # 使用重试机制获取数据
        weight_data = self.base._retry_request(fetch_index_weight, max_retries=3, timeout=30)
        
        if weight_data is None or weight_data.empty:
            # 如果获取失败，尝试从缓存读取（即使force_refresh=True，也尝试读取旧缓存）
            cached_data = self.base.cache_manager.get_index_weight(
                index_code=index_code,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
                force_refresh=False
            )
            if cached_data is not None and not cached_data.empty:
                if self.base.progress_callback:
                    self.base.progress_callback('cached', f"{index_code}: 使用缓存权重数据（网络获取失败）")
                return cached_data
            return None
        
        return weight_data
    
    def batch_get_index_weight(
        self,
        index_codes: List[str],
        start_date: str = None,
        end_date: str = None,
        force_refresh: bool = False,
        show_progress: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多个指数的权重数据
        Args:
            index_codes: 指数代码列表
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            force_refresh: 是否强制刷新
            show_progress: 是否显示进度
        Returns:
            {index_code: DataFrame} 字典
        """
        if not index_codes:
            return {}
        
        results = {}
        
        if show_progress:
            print(f"\n批量获取指数权重数据 ({len(index_codes)} 个指数)...")
            pbar = tqdm(total=len(index_codes), desc="获取指数权重")
        
        # 使用线程池并发获取
        with ThreadPoolExecutor(max_workers=min(5, len(index_codes))) as executor:
            futures = {
                executor.submit(
                    self.get_index_weight,
                    index_code=index_code,
                    start_date=start_date,
                    end_date=end_date,
                    force_refresh=force_refresh
                ): index_code
                for index_code in index_codes
            }
            
            for future in as_completed(futures):
                index_code = futures[future]
                try:
                    weight_data = future.result()
                    if weight_data is not None and not weight_data.empty:
                        results[index_code] = weight_data
                except Exception as e:
                    print(f"\n[错误] 获取指数权重失败 ({index_code}): {e}")
                finally:
                    if show_progress:
                        pbar.update(1)
        
        if show_progress:
            pbar.close()
            print(f"  成功获取 {len(results)}/{len(index_codes)} 个指数的权重数据")
        
        return results

