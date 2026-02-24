# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 大盘复盘模块
===================================

职责：
1. 执行大盘复盘分析
2. 生成复盘报告
3. 保存和发送复盘报告
4. （可选）触发智能选股，输出候选名单
"""

import logging
from datetime import datetime
from typing import Optional

from src.notification import NotificationService
from src.market_analyzer import MarketAnalyzer
from src.search_service import SearchService
from src.analyzer import GeminiAnalyzer


logger = logging.getLogger(__name__)


def run_market_review(
    notifier: NotificationService, 
    analyzer: Optional[GeminiAnalyzer] = None, 
    search_service: Optional[SearchService] = None,
    send_notification: bool = True,
    run_stock_selection: bool = True
) -> Optional[str]:
    """
    执行大盘复盘分析

    Args:
        notifier: 通知服务
        analyzer: AI分析器（可选）
        search_service: 搜索服务（可选）
        send_notification: 是否发送通知
        run_stock_selection: 是否在复盘后执行智能选股（默认开启）

    Returns:
        复盘报告文本
    """
    logger.info("开始执行大盘复盘分析...")
    
    market_overview = None  # 保存 overview 供选股复用

    try:
        market_analyzer = MarketAnalyzer(
            search_service=search_service,
            analyzer=analyzer
        )
        
        # 获取市场概览（同时保存供选股模块复用，避免重复请求）
        market_overview = market_analyzer.get_market_overview()

        # 搜索市场新闻
        news = market_analyzer.search_market_news()

        # 生成复盘报告
        review_report = market_analyzer.generate_market_review(market_overview, news)
        
        if review_report:
            # 保存报告到文件
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"# 🎯 大盘复盘\n\n{review_report}", 
                report_filename
            )
            logger.info(f"大盘复盘报告已保存: {filepath}")
            
            # 推送通知
            if send_notification and notifier.is_available():
                # 添加标题
                report_content = f"🎯 大盘复盘\n\n{review_report}"
                
                success = notifier.send(report_content)
                if success:
                    logger.info("大盘复盘推送成功")
                else:
                    logger.warning("大盘复盘推送失败")
            elif not send_notification:
                logger.info("已跳过推送通知 (--no-notify)")

    except Exception as e:
        logger.error(f"大盘复盘分析失败: {e}")
        review_report = None

    # ===================================================
    # 智能选股（在大盘复盘完成后执行，复用 market_overview）
    # ===================================================
    if run_stock_selection:
        _run_stock_selection(
            notifier=notifier,
            market_overview=market_overview,
            send_notification=send_notification
        )

    return review_report


def _run_stock_selection(
    notifier: NotificationService,
    market_overview=None,
    send_notification: bool = True
) -> None:
    """
    执行智能选股并推送候选名单

    Args:
        notifier: 通知服务
        market_overview: 大盘概览数据（复用，避免重复请求板块数据）
        send_notification: 是否推送
    """
    logger.info("=" * 50)
    logger.info("开始执行智能选股（板块联动 + 资金流向）")
    logger.info("=" * 50)

    try:
        from src.stock_selector import StockSelector, format_selection_report

        selector = StockSelector()
        result = selector.run(market_overview=market_overview)

        # 格式化报告
        report = format_selection_report(result)

        # 保存到文件
        date_str = datetime.now().strftime('%Y%m%d')
        report_filename = f"stock_selection_{date_str}.md"
        try:
            filepath = notifier.save_report_to_file(
                f"# 🎯 智能选股候选名单\n\n{report}",
                report_filename
            )
            logger.info(f"选股报告已保存: {filepath}")
        except Exception as save_err:
            logger.warning(f"选股报告保存失败（不影响推送）: {save_err}")

        # 推送通知
        if send_notification and notifier.is_available():
            success = notifier.send(report)
            if success:
                logger.info(f"智能选股推送成功，共 {len(result.candidates)} 只候选")
            else:
                logger.warning("智能选股推送失败")
        else:
            # 不推送时也打印到日志
            logger.info("智能选股候选（未推送）:")
            for s in result.candidates:
                logger.info(
                    f"  [{s.score:.0f}分] {s.name}({s.code}) "
                    f"板块:{s.sector} 净流入:{s.net_inflow:+.1f}亿"
                )

    except Exception as e:
        logger.error(f"智能选股执行失败: {e}", exc_info=True)
