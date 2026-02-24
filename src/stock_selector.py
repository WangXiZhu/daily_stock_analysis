# -*- coding: utf-8 -*-
"""
===================================
智能选股模块 - 板块联动 + 资金流向
===================================

策略说明：
1. 【方案B - 板块联动】从大盘复盘获取领涨板块，在板块内部寻找热门个股
2. 【方案C - 资金流向】找到主力资金持续净流入的个股

核心筛选流程（双重验证）：
  步骤1: 获取今日领涨板块 Top3
  步骤2: 在领涨板块内找主力净流入 Top 个股
  步骤3: 技术面过滤（换手率、乖离率、成交额）
  步骤4: 输出候选股名单 + 快照数据

交易理念（与系统现有策略一致）：
- 不追高：价格未超过 MA20 的 5%
- 换手率：1%~8%（排除死水和爆炒）
- 成交额：> 1亿（保证流动性）
- 连续资金流入：优先选3日净流入均为正的标的
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CandidateStock:
    """候选股票数据"""
    code: str                       # 股票代码（6位，如 600519）
    name: str                       # 股票名称
    sector: str                     # 所属板块
    current_price: float = 0.0      # 当前价格
    change_pct: float = 0.0         # 今日涨跌幅(%)
    turnover_rate: float = 0.0      # 换手率(%)
    amount: float = 0.0             # 成交额(亿元)
    net_inflow: float = 0.0         # 主力净流入(亿元，正=流入)
    net_inflow_pct: float = 0.0     # 主力净流入占比(%)
    ma5: float = 0.0                # 5日均线
    ma10: float = 0.0               # 10日均线
    ma20: float = 0.0               # 20日均线
    bias_ma5: float = 0.0           # 相对 MA5 的乖离率(%)
    bias_ma20: float = 0.0          # 相对 MA20 的乖离率(%)
    is_ma_bullish: bool = False      # 是否多头排列(MA5>MA10>MA20)
    market_cap: float = 0.0         # 总市值(亿元)
    select_reason: str = ""         # 入选理由
    score: float = 0.0              # 综合评分(0-100)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'current_price': self.current_price,
            'change_pct': self.change_pct,
            'turnover_rate': self.turnover_rate,
            'amount': self.amount,
            'net_inflow': self.net_inflow,
            'net_inflow_pct': self.net_inflow_pct,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'bias_ma5': self.bias_ma5,
            'bias_ma20': self.bias_ma20,
            'is_ma_bullish': self.is_ma_bullish,
            'market_cap': self.market_cap,
            'select_reason': self.select_reason,
            'score': self.score,
        }


@dataclass
class SelectionResult:
    """选股结果"""
    date: str                                           # 选股日期
    top_sectors: List[Dict] = field(default_factory=list)   # 领涨板块
    candidates: List[CandidateStock] = field(default_factory=list)  # 候选股
    filtered_out: int = 0                               # 过滤掉的数量
    data_source: str = ""                               # 数据来源说明
    error: Optional[str] = None                         # 错误信息


class StockSelector:
    """
    智能选股器

    工作流程：
    1. get_top_sectors()      - 获取领涨板块（来自 MarketAnalyzer）
    2. get_sector_stocks()    - 获取板块内成分股 + 资金流向
    3. apply_filters()        - 技术面过滤
    4. score_and_rank()       - 评分排序
    5. build_result()         - 组装结果
    """

    # 筛选参数（可配置）
    TURNOVER_RATE_MIN = 1.0      # 换手率下限(%)，低于此值为死水
    TURNOVER_RATE_MAX = 15.0     # 换手率上限(%)，高于此值为过热/爆炒
    AMOUNT_MIN_YI = 1.0          # 成交额最低要求(亿元)
    BIAS_MA20_MAX = 8.0          # 相对 MA20 最大乖离率(%)，超过此值视为过度追高
    MARKET_CAP_MIN_YI = 20.0    # 市值下限(亿元)，过小市值流动性差
    MARKET_CAP_MAX_YI = 3000.0  # 市值上限(亿元)，限中小盘
    TOP_SECTORS = 3              # 取前几个领涨板块
    STOCKS_PER_SECTOR = 5        # 每个板块取几只候选
    MAX_CANDIDATES = 8           # 最终候选上限

    def __init__(self):
        self._ak = None  # 懒加载 akshare

    def _get_ak(self):
        """懒加载 akshare"""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                raise ImportError("需要安装 akshare: pip install akshare")
        return self._ak

    def _sleep(self, secs: float = 2.0):
        """防封禁休眠"""
        time.sleep(secs)

    # =========================================================
    # 步骤1: 获取领涨板块
    # =========================================================

    def get_top_sectors(self, from_overview=None) -> List[Dict]:
        """
        获取领涨板块列表

        优先级：
        1. MarketOverview 已有数据（最优，无额外请求）
        2. MarketAnalyzer.get_market_overview()：复用 DataFetcherManager
           内置随机 UA + 限速 + 新浪兜底，比裸调 AkShare 稳定得多
        3. 直接裸调 AkShare（仅最后兜底，基本不会走到这里）

        Args:
            from_overview: MarketOverview 对象（已有时直接复用）

        Returns:
            板块列表，每项含 name, change_pct, type
        """
        # ── 路径1: 直接复用已有数据（大盘复盘已拉取过，零额外网络请求）──
        if from_overview and hasattr(from_overview, 'top_sectors') and from_overview.top_sectors:
            sectors = [
                {**s, 'type': s.get('type', 'industry')}
                for s in from_overview.top_sectors[:self.TOP_SECTORS]
            ]
            logger.info(
                f"[选股] 复用大盘复盘数据，领涨板块: {[s['name'] for s in sectors]}"
            )
            return sectors

        # ── 路径2: 调用 MarketAnalyzer（使用 DataFetcherManager 含随机UA+限速+新浪兜底）──
        logger.info("[选股] 通过 MarketAnalyzer 获取板块数据（含随机UA + 新浪兜底）...")
        try:
            from src.market_analyzer import MarketAnalyzer
            ma = MarketAnalyzer()
            overview = ma.get_market_overview()
            if overview and overview.top_sectors:
                sectors = [
                    {**s, 'type': s.get('type', 'industry')}
                    for s in overview.top_sectors[:self.TOP_SECTORS]
                ]
                logger.info(
                    f"[选股] MarketAnalyzer 板块获取成功: {[s['name'] for s in sectors]}"
                )
                return sectors
            else:
                logger.warning("[选股] MarketAnalyzer 未返回板块数据")
        except Exception as e:
            logger.warning(f"[选股] MarketAnalyzer 获取板块失败: {e}")

        # ── 路径3: 裸调 AkShare 新浪板块接口（最后兜底）──
        logger.info("[选股] 尝试新浪板块接口兜底...")
        try:
            ak = self._get_ak()
            self._sleep(2)
            df = ak.stock_sector_spot(indicator='新浪行业')
            if df is not None and not df.empty:
                name_col = next((c for c in ['板块', '板块名称', 'label', 'name'] if c in df.columns), None)
                chg_col = next((c for c in ['涨跌幅', 'change_pct', '涨幅'] if c in df.columns), None)
                if name_col and chg_col:
                    import pandas as pd
                    df[chg_col] = pd.to_numeric(df[chg_col], errors='coerce')
                    df = df.dropna(subset=[chg_col]).sort_values(chg_col, ascending=False)
                    sectors = []
                    for _, row in df.head(self.TOP_SECTORS).iterrows():
                        name = str(row[name_col])
                        pct = float(row[chg_col])
                        if name:
                            sectors.append({'name': name, 'change_pct': pct, 'type': 'sina'})
                    if sectors:
                        logger.info(f"[选股] 新浪板块兜底成功: {[s['name'] for s in sectors]}")
                        return sectors
        except Exception as e:
            logger.error(f"[选股] 新浪板块兜底也失败: {e}")

        logger.error("[选股] 所有板块数据源均失败")
        return []

    def _get_industry_sectors(self) -> List[Dict]:
        """东财行业板块（内部直接调 AkShare，仅作保留）"""
        ak = self._get_ak()
        self._sleep(2)
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return []
        col = '涨跌幅' if '涨跌幅' in df.columns else '最新涨跌幅'
        if col not in df.columns:
            return []
        df = df.sort_values(col, ascending=False)
        sectors = []
        for _, row in df.head(self.TOP_SECTORS).iterrows():
            name = row.get('板块名称', row.get('名称', ''))
            pct = float(row.get(col, 0) or 0)
            if name:
                sectors.append({'name': name, 'change_pct': pct, 'type': 'industry'})
        if sectors:
            logger.info(f"[选股] 东财行业板块成功: {[s['name'] for s in sectors]}")
        return sectors

    # =========================================================
    # 步骤2: 获取板块内成分股 + 资金流向
    # =========================================================

    def get_sector_stocks_with_flow(self, sector: Dict) -> List[CandidateStock]:
        """
        获取板块成分股及其资金流向数据

        Args:
            sector: 板块信息 {'name': ..., 'change_pct': ..., 'type': ...}

        Returns:
            候选股列表（已粗过滤）
        """
        sector_name = sector['name']
        sector_type = sector.get('type', 'concept')
        candidates = []

        try:
            ak = self._get_ak()
            self._sleep(2)

            # 获取板块成分股
            if sector_type == 'concept':
                df = ak.stock_board_concept_cons_em(symbol=sector_name)
            else:
                df = ak.stock_board_industry_cons_em(symbol=sector_name)

            if df is None or df.empty:
                logger.warning(f"[选股] 板块 {sector_name} 无成分股数据")
                return []

            logger.info(f"[选股] 板块 {sector_name} 获取到 {len(df)} 只成分股")

            # 按涨跌幅排序，取前20只做资金流分析（避免请求过多）
            pct_col = '涨跌幅' if '涨跌幅' in df.columns else None
            if pct_col:
                df = df.sort_values(pct_col, ascending=False)
            df = df.head(20)

            # 获取资金流向
            self._sleep(2)
            flow_df = self._get_money_flow_top(sector_name, sector_type)

            # 合并数据，构建候选股
            for _, row in df.iterrows():
                code = str(row.get('代码', '')).strip()
                name = str(row.get('名称', '')).strip()
                if not code or len(code) != 6:
                    continue
                # 排除 ST 股
                if 'ST' in name.upper() or '*' in name:
                    continue

                stock = CandidateStock(
                    code=code,
                    name=name,
                    sector=sector_name,
                    change_pct=float(row.get('涨跌幅', 0) or 0),
                    turnover_rate=float(row.get('换手率', 0) or 0),
                    current_price=float(row.get('最新价', row.get('收盘', 0)) or 0),
                )

                # 成交额（单位转换为"亿元"）
                raw_amount = float(row.get('成交额', 0) or 0)
                # AkShare 通常返回元，转换为亿元
                if raw_amount > 1e8:
                    stock.amount = raw_amount / 1e8
                elif raw_amount > 0:
                    stock.amount = raw_amount  # 可能已经是亿元

                # 合并资金流向
                if flow_df is not None and not flow_df.empty:
                    flow_row = flow_df[flow_df['代码'] == code]
                    if not flow_row.empty:
                        fr = flow_row.iloc[0]
                        stock.net_inflow = float(fr.get('主力净流入', fr.get('净流入', 0)) or 0)
                        # 转换为亿元
                        if abs(stock.net_inflow) > 1e8:
                            stock.net_inflow = stock.net_inflow / 1e8
                        stock.net_inflow_pct = float(fr.get('主力净占比', fr.get('净流入占比', 0)) or 0)

                candidates.append(stock)

        except Exception as e:
            logger.error(f"[选股] 获取板块 {sector_name} 成分股失败: {e}")

        # 资金流向排序：净流入高的优先
        candidates.sort(key=lambda x: x.net_inflow, reverse=True)
        return candidates[:self.STOCKS_PER_SECTOR * 2]  # 宽松初筛

    def _get_money_flow_top(self, sector_name: str, sector_type: str) -> Optional[Any]:
        """获取板块内个股资金流向"""
        try:
            ak = self._get_ak()
            self._sleep(1.5)

            if sector_type == 'concept':
                df = ak.stock_board_concept_fund_flow_individual(symbol=sector_name)
            else:
                df = ak.stock_board_industry_fund_flow_individual(symbol=sector_name)

            return df
        except Exception as e:
            logger.debug(f"[选股] 获取 {sector_name} 个股资金流失败: {e}")
            # 尝试备选接口
            return self._get_money_flow_fallback()

    def _get_money_flow_fallback(self) -> Optional[Any]:
        """备选：获取全市场主力资金净流入 Top"""
        try:
            ak = self._get_ak()
            self._sleep(2)
            # 获取全市场资金流向，用于后续 merge
            df = ak.stock_individual_fund_flow_rank(indicator="今日")
            return df
        except Exception as e:
            logger.debug(f"[选股] 备选资金流接口失败: {e}")
            return None

    # =========================================================
    # 步骤3: 技术面过滤 + MA 计算
    # =========================================================

    def enrich_with_technical(self, stock: CandidateStock) -> bool:
        """
        补充技术面数据（MA5/MA10/MA20/乖离率）

        Returns:
            True = 数据获取成功
        """
        try:
            ak = self._get_ak()
            self._sleep(1.5)

            end_date = date.today().strftime('%Y%m%d')
            # 取最近 30 个交易日以计算均线
            df = ak.stock_zh_a_hist(
                symbol=stock.code,
                period="daily",
                start_date="",  # 不传则取最近数据
                end_date=end_date,
                adjust="qfq"
            )

            if df is None or df.empty or len(df) < 5:
                return False

            closes = df['收盘'].astype(float).values
            if len(closes) >= 5:
                stock.ma5 = float(closes[-5:].mean())
            if len(closes) >= 10:
                stock.ma10 = float(closes[-10:].mean())
            if len(closes) >= 20:
                stock.ma20 = float(closes[-20:].mean())

            # 如果实时价格为空，用最后收盘价补充
            if stock.current_price <= 0 and len(closes) > 0:
                stock.current_price = float(closes[-1])

            # 乖离率
            if stock.current_price > 0:
                if stock.ma5 > 0:
                    stock.bias_ma5 = (stock.current_price - stock.ma5) / stock.ma5 * 100
                if stock.ma20 > 0:
                    stock.bias_ma20 = (stock.current_price - stock.ma20) / stock.ma20 * 100

            # 多头排列判断
            stock.is_ma_bullish = (
                stock.ma5 > 0 and stock.ma10 > 0 and stock.ma20 > 0
                and stock.ma5 > stock.ma10 > stock.ma20
            )

            return True

        except Exception as e:
            logger.debug(f"[选股] 获取 {stock.code} 技术数据失败: {e}")
            return False

    def apply_filters(self, candidates: List[CandidateStock]) -> Tuple[List[CandidateStock], int]:
        """
        技术面过滤

        过滤条件：
        1. 换手率在合理范围（排除死水和爆炒）
        2. 成交额足够（保证流动性）
        3. 乖离率不超过上限（不追高）
        4. 主力净流入为正（资金验证）

        Returns:
            (通过列表, 过滤掉的数量)
        """
        passed = []
        filtered = 0

        for stock in candidates:
            reasons = []

            # 换手率检查
            if stock.turnover_rate > 0:
                if stock.turnover_rate < self.TURNOVER_RATE_MIN:
                    reasons.append(f"换手率过低({stock.turnover_rate:.1f}%<{self.TURNOVER_RATE_MIN}%)")
                elif stock.turnover_rate > self.TURNOVER_RATE_MAX:
                    reasons.append(f"换手率过高({stock.turnover_rate:.1f}%>{self.TURNOVER_RATE_MAX}%，可能爆炒)")

            # 成交额检查
            if stock.amount > 0 and stock.amount < self.AMOUNT_MIN_YI:
                reasons.append(f"成交额不足({stock.amount:.2f}亿<{self.AMOUNT_MIN_YI}亿)")

            # 乖离率检查（防止追高）
            if stock.bias_ma20 > self.BIAS_MA20_MAX:
                reasons.append(f"乖离率过高({stock.bias_ma20:.1f}%>{self.BIAS_MA20_MAX}%，追高风险)")

            # 资金验证（必须有资金流入，或者流向数据缺失时放行）
            if stock.net_inflow < -2.0:  # 净流出超过2亿，强烈排除
                reasons.append(f"主力大幅净流出({stock.net_inflow:.1f}亿)")

            if reasons:
                logger.debug(f"[选股] 过滤 {stock.name}({stock.code}): {'; '.join(reasons)}")
                filtered += 1
            else:
                passed.append(stock)

        return passed, filtered

    # =========================================================
    # 步骤4: 评分排序
    # =========================================================

    def score_candidates(self, candidates: List[CandidateStock]) -> List[CandidateStock]:
        """
        综合评分（0-100分）

        评分权重：
        - 资金面（40分）：净流入规模 + 净流入占比
        - 技术面（40分）：多头排列 + 乖离率安全
        - 动量（20分）：板块效应 + 当日涨幅适中
        """
        for stock in candidates:
            score = 0.0

            # === 资金面（40分）===
            # 净流入越大分越高，但有上限
            if stock.net_inflow > 5:
                score += 25
            elif stock.net_inflow > 2:
                score += 18
            elif stock.net_inflow > 0.5:
                score += 12
            elif stock.net_inflow > 0:
                score += 6

            # 净流入占比
            if stock.net_inflow_pct > 10:
                score += 15
            elif stock.net_inflow_pct > 5:
                score += 10
            elif stock.net_inflow_pct > 0:
                score += 5

            # === 技术面（40分）===
            # 多头排列
            if stock.is_ma_bullish:
                score += 20

            # 乖离率（越小越好）
            bias = abs(stock.bias_ma5)
            if bias < 1:
                score += 20  # 完美买点
            elif bias < 3:
                score += 14
            elif bias < 5:
                score += 7
            # >5% 不加分（也不扣分，因为前面过滤器已经放行了）

            # === 动量（20分）===
            # 涨幅适中（1%-5% 最佳，说明启动了但没有爆炒）
            pct = stock.change_pct
            if 1 <= pct <= 5:
                score += 15
            elif 0 < pct < 1:
                score += 8
            elif 5 < pct <= 8:
                score += 5

            # 换手率适中（3%-8% 最佳）
            tr = stock.turnover_rate
            if 3 <= tr <= 8:
                score += 5
            elif 1 <= tr < 3 or 8 < tr <= 12:
                score += 2

            stock.score = min(score, 100.0)

        return sorted(candidates, key=lambda x: x.score, reverse=True)

    def _build_select_reason(self, stock: CandidateStock) -> str:
        """生成入选理由"""
        reasons = []
        if stock.net_inflow > 0:
            reasons.append(f"主力净流入{stock.net_inflow:.1f}亿")
        if stock.is_ma_bullish:
            reasons.append("均线多头排列")
        if abs(stock.bias_ma5) < 2:
            reasons.append("价格近MA5(最佳买点附近)")
        elif abs(stock.bias_ma5) < 5:
            reasons.append("价格未明显偏离MA5")
        if 2 <= stock.change_pct <= 6:
            reasons.append(f"今日涨幅适中({stock.change_pct:.1f}%)")
        if stock.turnover_rate >= 3:
            reasons.append(f"换手活跃({stock.turnover_rate:.1f}%)")
        return "；".join(reasons) if reasons else "板块联动候选"

    # =========================================================
    # 主入口：执行完整选股流程
    # =========================================================

    def run(self, market_overview=None, max_candidates: int = MAX_CANDIDATES) -> SelectionResult:
        """
        执行完整选股流程

        Args:
            market_overview: 可选的 MarketOverview 对象（来自大盘复盘，避免重复请求）
            max_candidates: 最终候选股上限

        Returns:
            SelectionResult
        """
        today = datetime.now().strftime('%Y-%m-%d')
        result = SelectionResult(date=today)

        logger.info("=" * 50)
        logger.info("开始智能选股（板块联动 + 资金流向）")
        logger.info("=" * 50)

        try:
            # 步骤1: 获取领涨板块
            top_sectors = self.get_top_sectors(from_overview=market_overview)

            if top_sectors:
                # ── 正常路径：板块联动 + 资金流向 ──
                result.top_sectors = top_sectors
                logger.info(f"[选股] 步骤1完成 - 领涨板块: {[s['name'] for s in top_sectors]}")

                # 步骤2: 获取板块内成分股 + 资金流向
                all_candidates: List[CandidateStock] = []
                for sector in top_sectors:
                    logger.info(f"[选股] 分析板块: {sector['name']} ({sector['change_pct']:+.2f}%)")
                    stocks = self.get_sector_stocks_with_flow(sector)
                    logger.info(f"[选股] 板块 {sector['name']} 初始候选: {len(stocks)} 只")
                    all_candidates.extend(stocks)
                    self._sleep(2)

                if not all_candidates:
                    logger.warning("[选股] 板块成分股为空，切换热度榜兜底")
                    all_candidates = self._get_candidates_from_hot_rank()
                    result.data_source = "AkShare（热门股票榜 Top100，板块接口不可用）"
                else:
                    result.data_source = "AkShare（东方财富板块数据 + 个股资金流向）"

            else:
                # ── 兜底路径：热度榜 Top 100（板块接口全部失败时）──
                logger.warning("[选股] 板块数据不可用，启用热度榜兜底（stock_hot_rank_em）")
                all_candidates = self._get_candidates_from_hot_rank()
                result.data_source = "AkShare（热门股票榜 Top100，板块接口不可用）"

            if not all_candidates:
                result.error = "未能获取任何候选股数据（板块接口和热度榜均失败）"
                logger.error("[选股] " + result.error)
                return result

            logger.info(f"[选股] 步骤2完成 - 共 {len(all_candidates)} 只初始候选")

            # 步骤3: 补充技术面数据
            enriched = []
            for i, stock in enumerate(all_candidates):
                logger.debug(f"[选股] 获取技术数据 {i+1}/{len(all_candidates)}: {stock.name}")
                self.enrich_with_technical(stock)
                enriched.append(stock)
                if (i + 1) % 5 == 0:
                    logger.info(f"[选股] 技术数据获取进度: {i+1}/{len(all_candidates)}")

            # 步骤4: 过滤
            passed, filtered_count = self.apply_filters(enriched)
            result.filtered_out = filtered_count
            logger.info(f"[选股] 步骤4完成 - 过滤后剩余 {len(passed)} 只 (过滤 {filtered_count} 只)")

            # 步骤5: 评分排序
            ranked = self.score_candidates(passed)

            # 最终候选（去重 + 限量）
            seen_codes = set()
            final = []
            for stock in ranked:
                if stock.code not in seen_codes and len(final) < max_candidates:
                    stock.select_reason = self._build_select_reason(stock)
                    final.append(stock)
                    seen_codes.add(stock.code)

            result.candidates = final

            logger.info(f"[选股] ✅ 选股完成！最终候选 {len(final)} 只:")
            for s in final:
                bullish_tag = "✅多头" if s.is_ma_bullish else "⚠️非多头"
                logger.info(
                    f"  [{s.score:.0f}分] {s.name}({s.code}) "
                    f"换手:{s.turnover_rate:.1f}% "
                    f"乖离:{s.bias_ma5:+.1f}% {bullish_tag}"
                )

        except Exception as e:
            logger.exception(f"[选股] 选股流程异常: {e}")
            result.error = str(e)

        return result

    def _get_candidates_from_hot_rank(self, top_n: int = 40) -> List[CandidateStock]:
        """
        热度榜兜底：从东方财富热门股票榜取 Top N 作为候选池

        当板块接口全不可用时，改用 stock_hot_rank_em() 获取候选。
        该接口通过不同域名（emappdata.eastmoney.com），稳定性优于板块接口。

        Args:
            top_n: 取热度榜前 N 只

        Returns:
            候选股列表（只含基础字段，无资金流和板块分类）
        """
        logger.info(f"[选股] 获取热度榜 Top {top_n}...")
        candidates = []
        try:
            ak = self._get_ak()
            self._sleep(1)
            df = ak.stock_hot_rank_em()
            if df is None or df.empty:
                logger.warning("[选股] 热度榜数据为空")
                return []

            logger.info(f"[选股] 热度榜获取成功: {len(df)} 只")
            df = df.head(top_n)

            for _, row in df.iterrows():
                raw_code = str(row.get('代码', '')).strip()
                # 去掉 SZ/SH 前缀，只保留 6 位数字
                code = raw_code[-6:] if len(raw_code) > 6 else raw_code
                name = str(row.get('股票名称', '')).strip()

                if not code or len(code) != 6:
                    continue
                if not code.isdigit():
                    continue
                # 排除 ST 股
                if 'ST' in name.upper() or '*' in name:
                    continue

                change_pct = float(row.get('涨跌幅', 0) or 0)
                current_price = float(row.get('最新价', 0) or 0)

                stock = CandidateStock(
                    code=code,
                    name=name,
                    sector='热门榜（板块数据不可用）',
                    current_price=current_price,
                    change_pct=change_pct,
                )
                candidates.append(stock)

            logger.info(f"[选股] 热度榜候选（去ST后）: {len(candidates)} 只")
        except Exception as e:
            logger.error(f"[选股] 热度榜获取失败: {e}")

        return candidates


def format_selection_report(result: SelectionResult) -> str:
    """
    格式化选股结果为 Markdown 推送报告

    Args:
        result: SelectionResult 对象

    Returns:
        Markdown 字符串
    """
    lines = [
        f"## 🎯 {result.date} 智能选股候选名单",
        "",
    ]

    if result.error:
        lines.append(f"> ⚠️ 选股过程出现问题：{result.error}")
        lines.append("")

    # 领涨板块
    if result.top_sectors:
        sector_str = " | ".join(
            [f"**{s['name']}**({s['change_pct']:+.2f}%)" for s in result.top_sectors]
        )
        lines.extend([
            f"📡 **今日联动板块**: {sector_str}",
            "",
        ])

    if not result.candidates:
        lines.append("> 今日暂无满足条件的候选股（市场可能普涨/普跌，信号弱）")
        lines.append("")
        lines.append("---")
        return "\n".join(lines)

    lines.extend([
        f"> 共筛选候选股 **{len(result.candidates)}** 只 | 过滤掉 {result.filtered_out} 只不达标个股",
        "",
        "---",
        "",
    ])

    # 候选股详情
    for i, stock in enumerate(result.candidates, 1):
        # 信号标签
        if stock.score >= 70:
            signal = "🟢 强信号"
        elif stock.score >= 50:
            signal = "🟡 中等信号"
        else:
            signal = "⚪ 弱信号"

        bullish_tag = "✅ 多头排列" if stock.is_ma_bullish else "⚠️ 非多头"
        flow_arrow = "📈" if stock.net_inflow > 0 else "📉"

        lines.extend([
            f"### {i}. {signal} {stock.name} (`{stock.code}`)",
            "",
        ])

        # 核心指标
        lines.extend([
            f"| 指标 | 数值 | 指标 | 数值 |",
            f"|------|------|------|------|",
            f"| 所属板块 | {stock.sector} | 当前价格 | {stock.current_price:.2f} 元 |",
            f"| 今日涨跌 | {stock.change_pct:+.2f}% | 综合评分 | **{stock.score:.0f}分** |",
            f"| {flow_arrow} 主力净流入 | **{stock.net_inflow:+.1f} 亿** | 净流入占比 | {stock.net_inflow_pct:+.1f}% |",
            f"| 换手率 | {stock.turnover_rate:.1f}% | 成交额 | {stock.amount:.1f} 亿 |",
            f"| 均线状态 | {bullish_tag} | 乖离MA5 | {stock.bias_ma5:+.1f}% |",
            "",
        ])

        # 均线位置
        if stock.ma5 > 0:
            lines.extend([
                f"> MA5: **{stock.ma5:.2f}** | MA10: **{stock.ma10:.2f}** | MA20: **{stock.ma20:.2f}**",
                "",
            ])

        # 入选理由
        lines.extend([
            f"💡 **入选理由**: {stock.select_reason}",
            "",
        ])

        # 操作提示
        if stock.is_ma_bullish and abs(stock.bias_ma5) < 3:
            op_hint = f"✅ 技术面良好，可关注回踩 MA5 ({stock.ma5:.2f}元) 买入机会"
        elif stock.is_ma_bullish:
            op_hint = f"⚠️ 均线多头但偏离较大，等待回踩 MA5 ({stock.ma5:.2f}元) 再介入"
        else:
            op_hint = f"⚠️ 均线尚未形成多头，以观察为主，待趋势确认后再操作"

        lines.extend([
            f"🎯 **操作提示**: {op_hint}",
            "",
            "---",
            "",
        ])

    # 底部说明
    lines.extend([
        "> ⚠️ **风险提示**: 候选名单仅供参考，不构成投资建议。入场前请结合大盘环境和个人风控执行。严格止损。",
        "",
        f"*数据来源: {result.data_source} | 生成时间: {datetime.now().strftime('%H:%M')}*",
    ])

    return "\n".join(lines)
