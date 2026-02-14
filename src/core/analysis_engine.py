# -*- coding: utf-8 -*-
"""
===================================
核心分析引擎
===================================

职责：
1. 执行单只股票的深度分析
2. 整合实时行情、技术指标、筹码分布、舆情搜索
3. 调用 LLM 生成最终分析报告
"""

import logging
import uuid
from typing import Dict, Any, Optional

from src.config import get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from data_provider.realtime_types import ChipDistribution
from src.analyzer import GeminiAnalyzer, AnalysisResult, STOCK_NAME_MAP
from src.search_service import SearchService
from src.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from src.enums import ReportType

logger = logging.getLogger(__name__)


class StockAnalysisEngine:
    """
    股票分析引擎
    
    负责具体的分析逻辑执行，不包含调度和通知
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        self.trend_analyzer = StockTrendAnalyzer()
        self.analyzer = GeminiAnalyzer()
        
        # 初始化搜索服务
        self.search_service = SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            brave_keys=self.config.brave_api_keys,
            serpapi_keys=self.config.serpapi_keys,
        )
        
        self.save_context_snapshot = self.config.save_context_snapshot

    def analyze_stock(
        self, 
        code: str, 
        report_type: ReportType = ReportType.SIMPLE,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        source_message: Optional[Any] = None
    ) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）
        
        流程：
        1. 获取实时行情（量比、换手率）
        2. 获取筹码分布
        3. 趋势分析
        4. 多维度情报搜索
        5. 增强上下文并调用 AI
        """
        try:
            # 获取股票名称（优先从实时行情获取真实名称）
            stock_name = STOCK_NAME_MAP.get(code, '')
            
            # Step 1: 获取实时行情
            realtime_quote = None
            try:
                realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                if realtime_quote:
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                    turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                    logger.info(f"[{code}] {stock_name} 实时行情: 价格={realtime_quote.price}, "
                              f"量比={volume_ratio}, 换手率={turnover_rate}%")
            except Exception as e:
                logger.warning(f"[{code}] 获取实时行情失败: {e}")
            
            if not stock_name:
                stock_name = f'股票{code}'
            
            # Step 2: 获取筹码分布
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(f"[{code}] 筹码分布: 获利比例={chip_data.profit_ratio:.1%}")
            except Exception as e:
                logger.warning(f"[{code}] 获取筹码分布失败: {e}")
            
            # Step 3: 趋势分析
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                context = self.db.get_analysis_context(code)
                if context and 'raw_data' in context:
                    import pandas as pd
                    raw_data = context['raw_data']
                    # 适配 list of dict 或 DataFrame
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                         df = pd.DataFrame(raw_data)
                    elif isinstance(raw_data, pd.DataFrame):
                         df = raw_data
                    else:
                         df = None

                    if df is not None and not df.empty:
                        trend_result = self.trend_analyzer.analyze(df, code)
                        logger.info(f"[{code}] 趋势分析: {trend_result.trend_status.value}, "
                                  f"评分={trend_result.signal_score}")
            except Exception as e:
                logger.warning(f"[{code}] 趋势分析失败: {e}")
            
            # Step 4: 多维度情报搜索
            news_context = None
            if self.search_service.is_available:
                logger.info(f"[{code}] 开始多维度情报搜索...")
                try:
                    intel_results = self.search_service.search_comprehensive_intel(
                        stock_code=code,
                        stock_name=stock_name,
                        max_searches=5
                    )
                    
                    if intel_results:
                        news_context = self.search_service.format_intel_report(intel_results, stock_name)
                        
                        # 保存新闻情报
                        query_context = self._build_query_context(query_id, query_source, source_message)
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code,
                                    name=stock_name,
                                    dimension=dim_name,
                                    query=response.query,
                                    response=response,
                                    query_context=query_context
                                )
                except Exception as e:
                    logger.warning(f"[{code}] 情报搜索异常: {e}")
            
            # Step 5: 获取基础上下文
            context = self.db.get_analysis_context(code)
            if context is None:
                from datetime import date
                context = {
                    'code': code,
                    'stock_name': stock_name,
                    'date': date.today().isoformat(),
                    'data_missing': True,
                    'today': {},
                    'yesterday': {}
                }
            
            # Step 6: 增强上下文
            enhanced_context = self._enhance_context(
                context, 
                realtime_quote, 
                chip_data, 
                trend_result,
                stock_name
            )
            
            # Step 7: AI 分析
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)

            if result:
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')

                # 保存历史记录
                try:
                    # 为每只股票生成唯一 query_id
                    per_stock_query_id = uuid.uuid4().hex
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data
                    )
                    self.db.save_analysis_history(
                        result=result,
                        query_id=per_stock_query_id,
                        report_type=report_type.value,
                        news_content=news_context,
                        context_snapshot=context_snapshot,
                        save_snapshot=self.save_context_snapshot
                    )
                except Exception as e:
                    logger.warning(f"[{code}] 保存分析历史失败: {e}")

            return result
            
        except Exception as e:
            logger.error(f"[{code}] 分析失败: {e}")
            logger.exception(f"[{code}] 详细错误信息:")
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = ""
    ) -> Dict[str, Any]:
        """增强分析上下文"""
        enhanced = context.copy()
        
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name
        
        if realtime_quote:
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'change_pct': getattr(realtime_quote, 'change_pct', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(volume_ratio) if volume_ratio else '无数据',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': getattr(realtime_quote, 'source', None),
            }
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}
        
        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }
        
        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }
        
        return enhanced
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        if volume_ratio < 0.5: return "极度萎缩"
        elif volume_ratio < 0.8: return "明显萎缩"
        elif volume_ratio < 1.2: return "正常"
        elif volume_ratio < 2.0: return "温和放量"
        elif volume_ratio < 3.0: return "明显放量"
        else: return "巨量"

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution]
    ) -> Dict[str, Any]:
        return {
            "enhanced_context": enhanced_context,
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        if value is None: return None
        if hasattr(value, "to_dict"):
            try: return value.to_dict()
            except: pass
        if hasattr(value, "__dict__"):
            try: return dict(value.__dict__)
            except: pass
        return None

    def _build_query_context(
        self, 
        query_id: Optional[str], 
        query_source: Optional[str],
        source_message: Optional[Any]
    ) -> Dict[str, str]:
        """生成用户查询关联信息"""
        context = {
            "query_id": query_id or "",
            "query_source": query_source or "",
        }
        if source_message:
            context.update({
                "requester_platform": getattr(source_message, 'platform', "") or "",
                "requester_user_id": getattr(source_message, 'user_id', "") or "",
                "requester_user_name": getattr(source_message, 'user_name', "") or "",
                "requester_chat_id": getattr(source_message, 'chat_id', "") or "",
                "requester_message_id": getattr(source_message, 'message_id', "") or "",
                "requester_query": getattr(source_message, 'content', "") or "",
            })
        return context
        return context

    def analyze_stocks_batch(
        self,
        codes: list[str],
        report_type: ReportType = ReportType.SIMPLE,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        source_message: Optional[Any] = None
    ) -> list[AnalysisResult]:
        """
        批量分析股票列表
        """
        if not codes:
            return []
            
        contexts = []
        news_contexts = {}
        processed_meta = {} # code -> {realtime:..., chip:..., news_obj:...}
        
        # 1. 准备所有股票的上下文数据
        for code in codes:
            try:
                # 获取名称
                stock_name = STOCK_NAME_MAP.get(code, '')
                
                # Realtime
                realtime_quote = None
                try:
                    realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                    if realtime_quote and realtime_quote.name:
                         stock_name = realtime_quote.name
                except Exception: pass
                
                if not stock_name: stock_name = f'股票{code}'
                
                # Chip
                chip_data = None
                try:
                    if self.config.enable_chip_distribution:
                         chip_data = self.fetcher_manager.get_chip_distribution(code)
                except Exception: pass
                
                # Trend
                trend_result = None
                try:
                     ctx = self.db.get_analysis_context(code)
                     if ctx and 'raw_data' in ctx:
                         import pandas as pd
                         raw = ctx['raw_data']
                         if isinstance(raw, list) and raw: df = pd.DataFrame(raw)
                         elif isinstance(raw, pd.DataFrame): df = raw
                         else: df = None
                         
                         if df is not None:
                             trend_result = self.trend_analyzer.analyze(df, code)
                except Exception: pass
                
                # News
                news_text = ""
                # Batch 模式下，可以考虑简化搜索 or 并行搜索。这里先串行。
                if self.search_service.is_available:
                     try:
                         # 减少搜索数量以加快批量速度
                         intel = self.search_service.search_comprehensive_intel(code, stock_name, max_searches=3)
                         if intel:
                             news_text = self.search_service.format_intel_report(intel, stock_name)
                             # 保存新闻情报到DB
                             q_ctx = self._build_query_context(query_id, query_source, source_message)
                             for dim, resp in intel.items():
                                 if resp and resp.success and resp.results:
                                     self.db.save_news_intel(code, stock_name, dim, resp.query, resp, q_ctx)
                     except Exception: pass
                
                news_contexts[code] = news_text
                
                # Build context
                base_ctx = self.db.get_analysis_context(code)
                if not base_ctx:
                     from datetime import date
                     base_ctx = {'code': code, 'stock_name': stock_name, 'date': date.today().isoformat(), 'today':{}}
                
                enhanced = self._enhance_context(base_ctx, realtime_quote, chip_data, trend_result, stock_name)
                contexts.append(enhanced)
                
                processed_meta[code] = {
                    'realtime': realtime_quote,
                    'chip': chip_data,
                    'news': news_text
                }
                
            except Exception as e:
                logger.error(f"[{code}] 批量准备上下文失败: {e}")
                continue
        
        # 2. 调用批量 LLM 分析
        if not contexts:
            return []
            
        results_map = self.analyzer.analyze_batch_optimized(contexts, news_contexts)
        
        final_results = []
        
        # 3. 处理结果并保存
        for code, result in results_map.items():
            if not result: continue
            
            meta = processed_meta.get(code, {})
            realtime_quote = meta.get('realtime')
            if realtime_quote:
                 result.current_price = getattr(realtime_quote, 'price', None)
                 result.change_pct = getattr(realtime_quote, 'change_pct', None)
            
            # 保存历史
            try:
                per_stock_query_id = uuid.uuid4().hex
                # 找到对应的 enhanced context
                enhanced = next((c for c in contexts if c['code'] == code), {})
                
                snapshot = self._build_context_snapshot(
                    enhanced, 
                    meta.get('news'), 
                    realtime_quote, 
                    meta.get('chip')
                )
                
                self.db.save_analysis_history(
                    result=result,
                    query_id=per_stock_query_id,
                    report_type=report_type.value,
                    news_content=meta.get('news'),
                    context_snapshot=snapshot,
                    save_snapshot=self.save_context_snapshot
                )
            except Exception as e:
                logger.warning(f"[{code}] 保存批量分析历史失败: {e}")
            
            final_results.append(result)
            
        return final_results
