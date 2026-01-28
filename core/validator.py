"""
配置验证器：统一管理配置检查逻辑
"""
import os
from typing import List, Tuple, Optional


class ConfigValidator:
    """配置验证器，统一管理配置检查逻辑"""
    
    @staticmethod
    def validate_feishu_config(cfg: dict) -> Tuple[List[Tuple[str, str]], str, str, str]:
        """
        验证飞书配置
        Args:
            cfg: 飞书配置字典
        Returns:
            tuple: (missing_items, folder, app_id, app_secret)
            - missing_items: 缺失的配置项列表，格式为 [(配置项名称, 配置说明), ...]
            - folder: 有效的 folder_token（可能来自配置或环境变量）
            - app_id: 有效的 app_id（可能来自配置或环境变量）
            - app_secret: 有效的 app_secret（可能来自配置或环境变量）
        """
        folder = (cfg.get("folder_token") or "").strip() or (os.environ.get("FEISHU_FOLDER_TOKEN") or "")
        app_id = (cfg.get("app_id") or "").strip() or (os.environ.get("FEISHU_APP_ID") or "")
        app_secret = (cfg.get("app_secret") or "").strip() or (os.environ.get("FEISHU_APP_SECRET") or "")
        
        missing = []
        if not folder:
            missing.append(("folder_token", "config.FEISHU_SHEETS_CONFIG['folder_token'] 或环境变量 FEISHU_FOLDER_TOKEN"))
        if not app_id:
            missing.append(("app_id", "config.FEISHU_SHEETS_CONFIG['app_id'] 或环境变量 FEISHU_APP_ID"))
        if not app_secret:
            missing.append(("app_secret", "config.FEISHU_SHEETS_CONFIG['app_secret'] 或环境变量 FEISHU_APP_SECRET"))
        
        return (missing, folder, app_id, app_secret)
    
    @staticmethod
    def is_feishu_config_valid(cfg: dict) -> bool:
        """
        检查飞书配置是否有效
        Args:
            cfg: 飞书配置字典
        Returns:
            如果配置有效返回 True，否则返回 False
        """
        missing, _, _, _ = ConfigValidator.validate_feishu_config(cfg)
        return len(missing) == 0
