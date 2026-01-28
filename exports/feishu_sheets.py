"""
飞书电子表格同步：复盘结果通过 Sheets API 写入飞书，仅使用 sheets/v3 创建与 values 写入。
values 写入使用 sheet/v2 或 sheets/v2 的 PUT /values（range 仅放 body，且使用 sheet_id 非 Sheet1）。
"""
import os
import logging
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_BASE = "https://open.feishu.cn/open-apis"


def _col_letter(n: int) -> str:
    """列数转 A-Z, AA-AZ, ... 1->A, 26->Z, 27->AA"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s or "A"


def _get_effective_config(cfg: dict) -> dict:
    """合并 config 与环境变量，env 优先。"""
    return {
        "enabled": cfg.get("enabled", False),
        "folder_token": cfg.get("folder_token") or os.environ.get("FEISHU_FOLDER_TOKEN"),
        "app_id": cfg.get("app_id") or os.environ.get("FEISHU_APP_ID"),
        "app_secret": cfg.get("app_secret") or os.environ.get("FEISHU_APP_SECRET"),
    }


def get_tenant_access_token(app_id: str, app_secret: str) -> Optional[str]:
    """获取 tenant_access_token。"""
    try:
        r = requests.post(
            f"{_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("tenant_access_token")
    except Exception as e:
        logger.warning("飞书获取 tenant_access_token 失败: %s", e)
        return None


def create_spreadsheet(access_token: str, title: str, folder_token: str) -> Optional[str]:
    """创建电子表格，POST /open-apis/sheets/v3/spreadsheets，返回 spreadsheet_token。"""
    try:
        r = requests.post(
            f"{_BASE}/sheets/v3/spreadsheets",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"title": title, "folder_token": folder_token},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("spreadsheet", {}).get("spreadsheet_token")
    except Exception as e:
        logger.warning("飞书创建电子表格失败 title=%s: %s", title, e)
        return None


def find_spreadsheet_by_title(access_token: str, folder_token: str, title: str) -> Optional[str]:
    """在文件夹下按标题查找电子表格，返回 spreadsheet_token；未找到返回 None。"""
    try:
        r = requests.get(
            f"{_BASE}/drive/v1/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"folder_token": folder_token, "page_size": 200},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data") or {}
        for f in data.get("files") or []:
            if f.get("name") == title:
                return f.get("token")
        return None
    except Exception as e:
        logger.warning("飞书查找文件夹下文件失败: %s", e)
        return None


def get_first_sheet_id(access_token: str, spreadsheet_token: str) -> Optional[str]:
    """
    获取电子表格第一个工作表的 sheet_id，用于 values 接口的 range（须为 sheet_id 而非 Sheet1）。
    先试 sheet/v2 metainfo，再试 sheets/v3 的 sheets/query。
    """
    # 1) sheet/v2 获取电子表格元数据（与 lark 一致）
    for path in (
        f"{_BASE}/sheet/v2/spreadsheets/{spreadsheet_token}/metainfo",
        f"{_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo",
    ):
        try:
            r = requests.get(
                path,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            r.raise_for_status()
            data = (r.json().get("data") or {})
            sheets = data.get("sheets") or data.get("blocks") or []
            if isinstance(sheets, list) and sheets:
                s = sheets[0]
                sid = s.get("sheet_id") or s.get("sheetId")
                if sid:
                    return str(sid)
        except Exception as e:
            logger.debug("飞书 metainfo %s: %s", path, e)
            continue
    # 2) sheets/v3 获取工作表
    try:
        r = requests.get(
            f"{_BASE}/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data") or {}
        sheets = data.get("sheets") or data.get("items") or []
        if isinstance(sheets, list) and sheets:
            s = sheets[0]
            sid = s.get("sheet_id") or s.get("sheetId")
            if sid:
                return str(sid)
    except Exception as e:
        logger.debug("飞书 sheets/query: %s", e)
    return None


def _format_review_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    格式化复盘 DataFrame：
    1. 将 day1_price/day1_score 等改为涨幅百分比（基于 recommendation_price 计算）
    2. 正数百分比标记为红色，负数百分比标记为绿色（通过特殊格式文本实现）
    """
    if df is None or df.empty:
        return df
    
    df = df.copy()
    
    # 获取 recommendation_price 列
    if 'recommendation_price' not in df.columns:
        return df
    
    # 处理 day1-day10 的 price 和 score 列
    for i in range(1, 11):
        price_col = f'day{i}_price'
        score_col = f'day{i}_score'
        
        # 如果存在 price 列，计算涨幅百分比
        if price_col in df.columns:
            # 计算涨幅百分比
            def calc_change_pct(row):
                if pd.isna(row.get('recommendation_price')) or pd.isna(row.get(price_col)):
                    return None
                if row['recommendation_price'] == 0:
                    return None
                change_pct = ((row[price_col] - row['recommendation_price']) / row['recommendation_price']) * 100
                return change_pct
            
            # 创建新的涨幅百分比列
            change_pct_col = f'day{i}_涨幅百分比'
            df[change_pct_col] = df.apply(calc_change_pct, axis=1)
            
            # 格式化：正数红色标记，负数绿色标记
            def format_change_pct(val):
                if pd.isna(val):
                    return ""
                val_float = float(val)
                if val_float > 0:
                    # 正数：红色标记（使用特殊格式，飞书可能不支持直接颜色，但至少标记）
                    return f"+{val_float:.2f}%"
                elif val_float < 0:
                    # 负数：绿色标记
                    return f"{val_float:.2f}%"
                else:
                    return "0.00%"
            
            df[change_pct_col] = df[change_pct_col].apply(format_change_pct)
            
            # 删除原来的 price 和 score 列
            df = df.drop(columns=[price_col], errors='ignore')
            df = df.drop(columns=[score_col], errors='ignore')
    
    return df


def _apply_cell_colors(access_token: str, spreadsheet_token: str, sheet_id: str, 
                       df: pd.DataFrame, start_row: int = 1) -> bool:
    """
    为涨幅百分比列设置单元格颜色：正数红色，负数绿色。
    使用飞书 sheets/v2/spreadsheets/{spreadsheet_token}/sheets/{sheet_id}/styles 接口。
    注意：飞书 API 可能不支持直接设置文本颜色，此功能为可选，失败不影响主流程。
    """
    try:
        # 找到所有涨幅百分比列的索引
        change_pct_cols = [col for col in df.columns if col.endswith('_涨幅百分比')]
        if not change_pct_cols:
            return True  # 没有需要设置颜色的列
        
        # 获取列索引（从0开始）
        col_indices = {}
        for idx, col in enumerate(df.columns):
            if col in change_pct_cols:
                col_indices[col] = idx
        
        # 为每一行设置颜色
        # 飞书 API 可能需要使用不同的格式，这里尝试使用 sheets/v2 的样式接口
        # 如果 API 不支持，至少文本中已经用 + 和 - 标记了正负
        
        # 尝试使用 sheets/v3 的样式接口（如果可用）
        # 注意：飞书 API 文档可能更新，这里使用常见的格式
        # 注意：iterrows() 返回的 row_idx 是 DataFrame 的原始索引，需要转换为连续的行号
        for df_idx, (row_idx, row) in enumerate(df.iterrows()):
            for col_name, col_idx in col_indices.items():
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue
                
                # 判断正负
                is_positive = str(val).startswith('+')
                
                # 构建单元格范围（Excel 格式：A1, B2 等）
                # start_row 是表头行（通常是1），所以数据从 start_row + 1 开始
                # df_idx 从 0 开始，所以实际行号是 start_row + 1 + df_idx
                col_letter = _col_letter(col_idx + 1)
                row_num = start_row + 1 + df_idx  # start_row 是表头，数据从 start_row+1 开始
                cell_range = f"{col_letter}{row_num}"
                
                # 尝试使用飞书 v3 API 设置样式
                # 飞书可能使用不同的 API 端点，这里尝试常见的格式
                try:
                    # 方法1：尝试使用 sheets/v3 的样式接口
                    url = f"{_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/sheets/{sheet_id}/styles"
                    style_data = {
                        "range": f"{sheet_id}!{cell_range}",
                        "style": {
                            "foregroundColor": "#FF0000" if is_positive else "#00FF00",  # 红色或绿色（十六进制）
                        }
                    }
                    r = requests.put(
                        url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json=style_data,
                        timeout=5,
                    )
                    r.raise_for_status()
                except Exception:
                    # 如果样式设置失败，不影响主流程
                    # 文本中已经用 + 和 - 标记了正负，用户可以手动识别
                    pass
        
        return True
    except Exception as e:
        logger.debug("飞书设置单元格颜色失败（不影响主流程）: %s", e)
        # 样式设置失败不影响主流程，文本中已经标记了正负
        return True


def write_review_to_sheet(access_token: str, spreadsheet_token: str, df: pd.DataFrame, apply_colors: bool = True) -> bool:
    """
    将 df（表头+行）写入电子表格，使用 values 接口。
    约定：PUT .../values 路径中不带 range；range 放 body，且使用 sheet_id（如 bbdC7f）而非 Sheet1。
    Args:
        access_token: 访问令牌
        spreadsheet_token: 电子表格 token
        df: 要写入的 DataFrame
        apply_colors: 是否应用单元格颜色（正数红色，负数绿色）
    """
    if df is None or df.empty:
        return True
    sheet_id = get_first_sheet_id(access_token, spreadsheet_token)
    if not sheet_id:
        logger.warning("飞书写入 values 失败：无法获取 sheet_id，spreadsheet=%s", spreadsheet_token[:20])
        return False
    df = df.fillna("")
    rows = [df.columns.tolist()] + df.astype(str).values.tolist()
    nrow, ncol = len(rows), len(df.columns)
    end_col = _col_letter(ncol)
    range_str = f"{sheet_id}!A1:{end_col}{nrow}"
    # 飞书 v2：range 只放在 body，路径为 /values（不再 /values/{range}）
    url = f"{_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values"
    try:
        r = requests.put(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"valueRange": {"range": range_str, "values": rows}},
            timeout=15,
        )
        r.raise_for_status()
        
        # 如果写入成功且需要设置颜色，尝试设置单元格颜色
        if apply_colors:
            _apply_cell_colors(access_token, spreadsheet_token, sheet_id, df, start_row=1)
        
        return True
    except Exception as e:
        # 若 /sheets/v2/.../values 仍 404，可尝试 /sheet/v2/.../values（与 metainfo 一致）
        if "404" in str(e) and "/sheets/v2/" in url:
            try:
                alt = f"{_BASE}/sheet/v2/spreadsheets/{spreadsheet_token}/values"
                r2 = requests.put(
                    alt,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"valueRange": {"range": range_str, "values": rows}},
                    timeout=15,
                )
                r2.raise_for_status()
                
                # 如果写入成功且需要设置颜色，尝试设置单元格颜色
                if apply_colors:
                    _apply_cell_colors(access_token, spreadsheet_token, sheet_id, df, start_row=1)
                
                return True
            except Exception as e2:
                logger.warning("飞书写入 values 失败 spreadsheet=%s: %s", spreadsheet_token[:20], e2)
                return False
        logger.warning("飞书写入 values 失败 spreadsheet=%s: %s", spreadsheet_token[:20], e)
        return False


def sync_review_to_feishu(
    strategy_name: str,
    review_df: pd.DataFrame,
    folder_token: str,
    feishu_config: dict,
) -> bool:
    """
    同步某策略的复盘 DataFrame 到飞书电子表格。
    命名：{YYYY}_{strategy_name}_复盘结果。先查找，不存在则创建，再写入。
    失败打日志，不抛错；内部重试 1 次。
    
    特殊处理：
    - 对于 IndexWeightStrategy，根据 category 字段拆分成两个 Excel：
      * 中小盘：{YYYY}_IndexWeightStrategy_复盘结果_中小盘
      * 沪深300权重股：{YYYY}_IndexWeightStrategy_复盘结果_沪深300权重股
    - 自动格式化数据：将 day1_price/day1_score 等改为涨幅百分比
    - 正数百分比标记为红色，负数百分比标记为绿色
    """
    cfg = _get_effective_config(feishu_config)
    app_id = cfg.get("app_id")
    app_secret = cfg.get("app_secret")
    if not app_id or not app_secret or not folder_token:
        logger.warning("飞书同步: app_id/app_secret/folder_token 未配置，跳过")
        return False

    from datetime import datetime

    # 格式化数据：将 price/score 转换为涨幅百分比
    formatted_df = _format_review_dataframe(review_df)
    
    # 对于 IndexWeightStrategy，根据 category 拆分
    if strategy_name == 'IndexWeightStrategy' and 'category' in formatted_df.columns:
        # 拆分数据
        small_mid_df = formatted_df[formatted_df['category'] == '中小盘'].copy()
        hs300_df = formatted_df[formatted_df['category'] == '沪深300权重股'].copy()
        
        # 删除 category 列（不再需要）
        if not small_mid_df.empty:
            small_mid_df = small_mid_df.drop(columns=['category'], errors='ignore')
        if not hs300_df.empty:
            hs300_df = hs300_df.drop(columns=['category'], errors='ignore')
        
        # 同步两个 Excel
        results = []
        
        # 同步中小盘
        if not small_mid_df.empty:
            title_small_mid = f"{datetime.now().year}_{strategy_name}_复盘结果_中小盘"
            result_small_mid = _sync_single_sheet(
                title_small_mid, small_mid_df, app_id, app_secret, folder_token
            )
            results.append(result_small_mid)
            if result_small_mid:
                logger.info(f"[飞书同步] {strategy_name} 中小盘已同步 {len(small_mid_df)} 条复盘结果")
        
        # 同步沪深300权重股
        if not hs300_df.empty:
            title_hs300 = f"{datetime.now().year}_{strategy_name}_复盘结果_沪深300权重股"
            result_hs300 = _sync_single_sheet(
                title_hs300, hs300_df, app_id, app_secret, folder_token
            )
            results.append(result_hs300)
            if result_hs300:
                logger.info(f"[飞书同步] {strategy_name} 沪深300权重股已同步 {len(hs300_df)} 条复盘结果")
        
        return all(results) if results else False
    else:
        # 普通策略：单个 Excel
        title = f"{datetime.now().year}_{strategy_name}_复盘结果"
        return _sync_single_sheet(title, formatted_df, app_id, app_secret, folder_token)


def _sync_single_sheet(
    title: str,
    df: pd.DataFrame,
    app_id: str,
    app_secret: str,
    folder_token: str,
) -> bool:
    """
    同步单个电子表格的辅助函数。
    """
    def _do() -> bool:
        token = get_tenant_access_token(app_id, app_secret)
        if not token:
            return False
        sid = find_spreadsheet_by_title(token, folder_token, title)
        if not sid:
            sid = create_spreadsheet(token, title, folder_token)
        if not sid:
            return False
        # 不推送以下字段到飞书：
        # - strategy_name, strategy_type: 策略相关字段
        # - average_score, total_score, valid_days, last_update_time: 统计和元数据字段
        columns_to_drop = [
            'strategy_name', 
            'strategy_type',
            'average_score',
            'total_score',
            'valid_days',
            'last_update_time'
        ]
        to_write = df.drop(columns=columns_to_drop, errors='ignore')
        return write_review_to_sheet(token, sid, to_write, apply_colors=True)

    if _do():
        return True
    if _do():  # 重试一次
        return True
    return False
