# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 核心分析流水线
===================================

职责：
1. 管理整个分析流程
2. 协调数据获取、存储、搜索、分析、通知等模块
3. 实现并发控制和异常处理
4. 提供股票分析的核心功能
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

from src.config import get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from src.analyzer import AnalysisResult
from src.notification import NotificationService, NotificationChannel
from src.enums import ReportType
from src.core.analysis_engine import StockAnalysisEngine
from bot.models import BotMessage


logger = logging.getLogger(__name__)


class StockAnalysisPipeline:
    """
    股票分析主流程调度器
    
    职责：
    1. 管理整个分析流程
    2. 协调数据获取、存储、分析引擎、通知等模块
    3. 实现并发控制和异常处理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        source_message: Optional[BotMessage] = None,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None
    ):
        """
        初始化调度器
        
        Args:
            config: 配置对象（可选，默认使用全局配置）
            max_workers: 最大并发线程数（可选，默认从配置读取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.source_message = source_message
        self.query_id = query_id
        self.query_source = self._resolve_query_source(query_source)
        
        # 初始化各模块
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        
        # 核心分析引擎
        self.analysis_engine = StockAnalysisEngine(self.config)
        
        self.notifier = NotificationService(source_message=source_message)
        
        logger.info(f"调度器初始化完成，最大并发数: {self.max_workers}")
        logger.info("已启用分析引擎 (Trend + Search + LLM)")
        
        # 打印实时行情/筹码配置状态
        if self.config.enable_realtime_quote:
            logger.info(f"实时行情已启用 (优先级: {self.config.realtime_source_priority})")
        else:
            logger.info("实时行情已禁用，将使用历史收盘价")
    
    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据
        
        断点续传逻辑：
        1. 检查数据库是否已有今日数据
        2. 如果有且不强制刷新，则跳过网络请求
        3. 否则从数据源获取并保存
        
        Args:
            code: 股票代码
            force_refresh: 是否强制刷新（忽略本地缓存）
            
        Returns:
            Tuple[是否成功, 错误信息]
        """
        try:
            today = date.today()
            
            # 断点续传检查：如果今日数据已存在，跳过
            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"[{code}] 今日数据已存在，跳过获取（断点续传）")
                return True, None
            
            # 增量更新逻辑
            fetch_days = 300  # 默认获取较长历史以确保指标计算准确（特别是MA20/60）
            if not force_refresh:
                latest_date = self.db.get_latest_date(code)
                if latest_date:
                    days_diff = (today - latest_date).days
                    # 如果是最新的（今天或未来），可能只需要很少，但为了覆盖修正，至少取5天
                    if days_diff <= 0:
                        fetch_days = 5
                    else:
                        # 获取缺失天数 + 缓冲
                        fetch_days = days_diff + 5
            
            # 从数据源获取数据
            logger.info(f"[{code}] 开始从数据源获取数据(days={fetch_days})...")
            df, source_name = self.fetcher_manager.get_daily_data(code, days=fetch_days)
            
            if df is None or df.empty:
                return False, "获取数据为空"
            
            # 保存到数据库
            filtered_df = df
            if not force_refresh and latest_date:
                 # 简单过滤：只保留新于数据库最新日期的数据（虽然 DB 有 UPSERT，但在 python 层过滤能减少 DB 压力）
                 # 注意 df['date'] 可能是 datetime 或 string，需要统一处理比较麻烦，
                 # 且 save_daily_data 已经做了 UPSERT，这里可以直接传
                 pass

            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(f"[{code}] 数据保存成功（来源: {source_name}，新增/更新 {saved_count} 条）")
            
            return True, None
            
        except Exception as e:
            error_msg = f"获取/保存数据失败: {str(e)}"
            logger.error(f"[{code}] {error_msg}")
            return False, error_msg
    
    
    
    def fetch_and_save_data_batch(
        self,
        stock_codes: List[str],
        force_refresh: bool = False
    ) -> Dict[str, bool]:
        """
        批量获取并保存股票数据（优化版）
        
        策略：
        1. 过滤掉不需要更新的股票（断点续传）
        2. 计算每只股票需要获取的天数（增量更新）
        3. 按所需天数分组，批量调用 fetcher_manager
        4. 批量保存到数据库
        
        Args:
            stock_codes: 股票代码列表
            force_refresh: 强制刷新
            
        Returns:
            Dict[code, success]: 每个股票是否成功
        """
        results = {code: False for code in stock_codes}
        today = date.today()
        
        # 1. 筛选需要更新的股票
        codes_to_fetch = []
        fetch_params = {}  # code -> days
        
        for code in stock_codes:
            # 断点续传检查
            if not force_refresh and self.db.has_today_data(code, today):
                logger.debug(f"[{code}] 今日数据已存在，跳过")
                results[code] = True
                continue
                
            # 增量更新计算
            fetch_days = 300
            if not force_refresh:
                latest_date = self.db.get_latest_date(code)
                if latest_date:
                    days_diff = (today - latest_date).days
                    if days_diff <= 0:
                        fetch_days = 5
                    else:
                        fetch_days = days_diff + 5
            
            codes_to_fetch.append(code)
            fetch_params[code] = fetch_days
            
        if not codes_to_fetch:
            return results
            
        logger.info(f"开始批量获取 {len(codes_to_fetch)} 只股票数据...")
        
        # 2. 分组获取（按 days 大致分组，或者直接取最大 days，这里简单起见统一处理）
        # 为了利用 efinance 的 batch 接口，我们需要统一参数。
        # 策略：取 fetch_params 中的最大 days，一次性获取。虽然有些股票多获取了，但比多次请求快。
        # 或者：只对 efinance 使用 batch，其他逐个。
        # DataFetcherManager.get_daily_data_batch 内部已经处理了 efinance 的 batch。
        # 我们传入 max_days。
        
        max_days = max(fetch_params.values()) if fetch_params else 300
        
        # 调用批量接口
        batch_data = self.fetcher_manager.get_daily_data_batch(
            codes_to_fetch, days=max_days
        )
        
        # 3. 保存数据
        for code, (df, source) in batch_data.items():
            try:
                if df is not None and not df.empty:
                    saved_count = self.db.save_daily_data(df, code, source)
                    logger.info(f"[{code}] 批量保存成功 ({source}): {saved_count} 条")
                    results[code] = True
                else:
                    logger.warning(f"[{code}] 获取数据为空")
            except Exception as e:
                logger.error(f"[{code}] 保存失败: {e}")
                
        # 4. 处理批量接口未返回的股票（DataFetcherManager 已做兜底，但防止意外）
        for code in codes_to_fetch:
            if code not in batch_data:
                # 标记为失败（或者由 manager 的兜底逻辑处理了）
                # 如果 manager 兜底成功，应该在 batch_data 里。
                # 如果不在，说明彻底失败。
                if not results[code]:
                    logger.warning(f"[{code}] 批量获取完全失败")
                    
        return results

    def _resolve_query_source(self, query_source: Optional[str]) -> str:
        """
        解析请求来源。

        优先级（从高到低）：
        1. 显式传入的 query_source：调用方明确指定时优先使用，便于覆盖推断结果或兼容未来 source_message 来自非 bot 的场景
        2. 存在 source_message 时推断为 "bot"：当前约定为机器人会话上下文
        3. 存在 query_id 时推断为 "web"：Web 触发的请求会带上 query_id
        4. 默认 "system"：定时任务或 CLI 等无上述上下文时

        Args:
            query_source: 调用方显式指定的来源，如 "bot" / "web" / "cli" / "system"

        Returns:
            归一化后的来源标识字符串，如 "bot" / "web" / "cli" / "system"
        """
        if query_source:
            return query_source
        if self.source_message:
            return "bot"
        if self.query_id:
            return "web"
        return "system"

    
    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程

        包括：
        1. 获取数据
        2. 保存数据
        3. AI 分析
        4. 单股推送（可选，#55）

        此方法会被线程池调用，需要处理好异常

        Args:
            code: 股票代码
            skip_analysis: 是否跳过 AI 分析
            single_stock_notify: 是否启用单股推送模式（每分析完一只立即推送）
            report_type: 报告类型枚举（从配置读取，Issue #119）

        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 开始处理 {code} ==========")
        
        try:
            # Step 1: 获取并保存数据
            success, error = self.fetch_and_save_stock_data(code)
            
            if not success:
                logger.warning(f"[{code}] 数据获取失败: {error}")
                # 即使获取失败，也尝试用已有数据分析
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{code}] 跳过 AI 分析（dry-run 模式）")
                return None
            
            result = self.analysis_engine.analyze_stock(
                code=code,
                report_type=report_type,
                query_id=self.query_id,
                query_source=self.query_source,
                source_message=self.source_message
            )
            
            if result:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )
                
                # 单股推送模式（#55）：每分析完一只股票立即推送
                if single_stock_notify and self.notifier.is_available():
                    try:
                        # 根据报告类型选择生成方法
                        if report_type == ReportType.FULL:
                            # 完整报告：使用决策仪表盘格式
                            report_content = self.notifier.generate_dashboard_report([result])
                            logger.info(f"[{code}] 使用完整报告格式")
                        else:
                            # 精简报告：使用单股报告格式（默认）
                            report_content = self.notifier.generate_single_stock_report(result)
                            logger.info(f"[{code}] 使用精简报告格式")
                        
                        if self.notifier.send(report_content):
                            logger.info(f"[{code}] 单股推送成功")
                        else:
                            logger.warning(f"[{code}] 单股推送失败")
                    except Exception as e:
                        logger.error(f"[{code}] 单股推送异常: {e}")
            
            return result
            
        except Exception as e:
            # 捕获所有异常，确保单股失败不影响整体
            logger.exception(f"[{code}] 处理过程发生未知异常: {e}")
            return None
            
    def process_batch(
        self,
        codes: List[str],
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE
    ) -> List[AnalysisResult]:
        """
        批量处理股票列表（仅分析，假设数据已通过 batch fetch 获取）
        
        Args:
            codes: 股票代码列表
            skip_analysis: 是否跳过分析
            single_stock_notify: 是否单股推送
            report_type: 报告类型
            
        Returns:
            结果列表
        """
        if skip_analysis or not codes:
            return []
            
        try:
            results = self.analysis_engine.analyze_stocks_batch(
                codes=codes,
                report_type=report_type,
                query_id=self.query_id,
                query_source=self.query_source,
                source_message=self.source_message
            )
            
            # 单股推送
            if single_stock_notify and self.notifier.is_available():
                for result in results:
                    try:
                        # 复用通知逻辑
                        if report_type == ReportType.FULL:
                             content = self.notifier.generate_dashboard_report([result])
                        else:
                             content = self.notifier.generate_single_stock_report(result)
                        
                        self.notifier.send(content)
                    except Exception as e:
                        logger.error(f"[{result.code}] 单股推送异常: {e}")
                        
            return results
            
        except Exception as e:
            logger.exception(f"批量处理失败: {codes} - {e}")
            return []
    
    def run(
        self, 
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程
        
        流程：
        1. 获取待分析的股票列表
        2. 批量预取并保存行情数据 (优化点)
        3. 使用线程池并发执行 AI 分析
        4. 收集分析结果
        5. 发送通知
        
        Args:
            stock_codes: 股票代码列表（可选，默认使用配置中的自选股）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            
        Returns:
            分析结果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list
        
        if not stock_codes:
            logger.error("未配置自选股列表，请在 .env 文件中设置 STOCK_LIST")
            return []
        
        logger.info(f"===== 开始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"并发数: {self.max_workers}, 模式: {'仅获取数据' if dry_run else '完整分析'}")
        
        # === Step 1: 批量获取并保存历史行情数据 (优化) ===
        # 相比于在 process_single_stock 中逐个获取，批量获取能显著减少 API 调用次数并利用 ef 的批量接口
        batch_results = self.fetch_and_save_data_batch(stock_codes, force_refresh=False)
        
        # === Step 2: 批量预取实时行情 ===
        # 只有股票数量 >= 5 时才进行预取，少量股票直接逐个查询更高效
        if len(stock_codes) >= 5:
            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(f"已启用批量预取架构：一次拉取全市场数据，{len(stock_codes)} 只股票共享缓存")
        
        # 单股推送模式（#55）：从配置读取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 从配置读取报告类型
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        report_type = ReportType.FULL if report_type_str == 'full' else ReportType.SIMPLE
        # Issue #128: 从配置读取分析间隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(f"已启用单股推送模式：每分析完一只股票立即推送（报告类型: {report_type_str}）")
        
        results: List[AnalysisResult] = []
        
        # === Step 3: 并发执行 AI 分析 ===
        # 根据 batch_size 分组
        batch_size = max(1, self.config.batch_size)
        stock_batches = [stock_codes[i:i + batch_size] for i in range(0, len(stock_codes), batch_size)]
        
        logger.info(f"启用批量分析: batch_size={batch_size}, 共 {len(stock_batches)} 批")
        
        # 注意：max_workers 设置较低以避免触发反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_batch = {
                executor.submit(
                    self.process_batch,
                    batch_codes,
                    skip_analysis=dry_run,
                    single_stock_notify=single_stock_notify and send_notification,
                    report_type=report_type
                ): idx
                for idx, batch_codes in enumerate(stock_batches)
            }
            
            # 收集结果
            completed_batches = 0
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    batch_analysis_results = future.result()
                    if batch_analysis_results:
                        results.extend(batch_analysis_results)

                    # Issue #128: 分析间隔 - 在批次之间添加延迟
                    completed_batches += 1
                    if completed_batches < len(stock_batches) and analysis_delay > 0:
                        # 简单的节流，避免日志刷屏太快
                        pass 

                except Exception as e:
                    logger.error(f"批次 {batch_idx} 执行失败: {e}")
        
        # 统计
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，数据获取成功即视为成功
        if dry_run:
            # 检查哪些股票的数据今天已存在（batch_results 记录了状态）
            success_count = sum(1 for code in stock_codes if batch_results.get(code, False) or self.db.has_today_data(code))
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info("===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 耗时: {elapsed_time:.2f} 秒")
        
        # 发送通知（单股推送模式下跳过汇总推送，避免重复）
        if results and send_notification and not dry_run:
            if single_stock_notify:
                # 单股推送模式：只保存汇总报告，不再重复推送
                logger.info("单股推送模式：跳过汇总推送，仅保存报告到本地")
                self._send_notifications(results, skip_push=True)
            else:
                self._send_notifications(results)
        
        return results
    
    def _send_notifications(self, results: List[AnalysisResult], skip_push: bool = False) -> None:
        """
        发送分析结果通知
        
        生成决策仪表盘格式的报告
        
        Args:
            results: 分析结果列表
            skip_push: 是否跳过推送（仅保存到本地，用于单股推送模式）
        """
        try:
            logger.info("生成决策仪表盘日报...")
            
            # 生成决策仪表盘格式的详细日报
            report = self.notifier.generate_dashboard_report(results)
            
            # 保存到本地
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"决策仪表盘日报已保存: {filepath}")
            
            # 跳过推送（单股推送模式）
            if skip_push:
                return
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()
                context_success = self.notifier.send_to_context(report)

                # 企业微信：只发精简版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企业微信仪表盘长度: {len(dashboard_content)} 字符")
                    logger.debug(f"企业微信推送内容:\n{dashboard_content}")
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他渠道：发完整报告（避免自定义 Webhook 被 wechat 截断逻辑污染）
                non_wechat_success = False
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        non_wechat_success = self.notifier.send_to_telegram(report) or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        non_wechat_success = self.notifier.send_to_email(report) or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        non_wechat_success = self.notifier.send_to_custom(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHPLUS:
                        non_wechat_success = self.notifier.send_to_pushplus(report) or non_wechat_success
                    elif channel == NotificationChannel.SERVERCHAN3:
                        non_wechat_success = self.notifier.send_to_serverchan3(report) or non_wechat_success
                    elif channel == NotificationChannel.DISCORD:
                        non_wechat_success = self.notifier.send_to_discord(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHOVER:
                        non_wechat_success = self.notifier.send_to_pushover(report) or non_wechat_success
                    elif channel == NotificationChannel.ASTRBOT:
                        non_wechat_success = self.notifier.send_to_astrbot(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知渠道: {channel}")

                success = wechat_success or non_wechat_success or context_success
                if success:
                    logger.info("决策仪表盘推送成功")
                else:
                    logger.warning("决策仪表盘推送失败")
            else:
                logger.info("通知渠道未配置，跳过推送")
                
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
