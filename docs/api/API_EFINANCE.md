# API Reference

## Stock

### `get_all_company_performance`

```python
efinance.stock.get_all_company_performance(date: str = None) -> DataFrame
```

获取沪深市场股票某一季度的表现情况

**Parameters**

*   **date** (*str, optional*) – 报告发布日期 部分可选示例如下(默认为 ``None``)
    *   ``None`` : 最新季报
    *   ``'2021-06-30'`` : 2021 年 Q2 季度报
    *   ``'2021-03-31'`` : 2021 年 Q1 季度报

**Returns**

*   **DataFrame** – 获取沪深市场股票某一季度的表现情况

### `get_all_report_dates`

```python
efinance.stock.get_all_report_dates() -> DataFrame
```

获取沪深市场的全部股票报告期信息

**Returns**

*   **DataFrame** – 沪深市场的全部股票报告期信息

### `get_base_info`

```python
efinance.stock.get_base_info(stock_codes: Union[str, List[str]]) -> Union[Series, DataFrame]
```

**Parameters**

*   **stock_codes** (*Union[str, List[str]]*) – 股票代码或股票代码构成的列表

**Returns**

*   **Union[Series, DataFrame]**
    *   ``Series`` : 包含单只股票基本信息(当 ``stock_codes`` 是字符串时)
    *   ``DataFrame`` : 包含多只股票基本信息(当 ``stock_codes`` 是字符串列表时)

### `get_belong_board`

```python
efinance.stock.get_belong_board(stock_code: str) -> DataFrame
```

获取股票所属板块

**Parameters**

*   **stock_code** (*str*) – 股票代码或者股票名称

**Returns**

*   **DataFrame** – 股票所属板块

### `get_daily_billboard`

```python
efinance.stock.get_daily_billboard(start_date: str = None, end_date: str = None) -> DataFrame
```

获取指定日期区间的龙虎榜详情数据

**Parameters**

*   **start_date** (*str, optional*) – 开始日期
    *   ``None`` 最新一个榜单公开日(默认值)
    *   ``"2021-08-27"`` 2021年8月27日
*   **end_date** (*str, optional*) – 结束日期
    *   ``None`` 最新一个榜单公开日(默认值)
    *   ``"2021-08-31"`` 2021年8月31日

**Returns**

*   **DataFrame** – 龙虎榜详情数据

### `get_deal_detail`

```python
efinance.stock.get_deal_detail(stock_code: str, max_count: int = 1000000, **kwargs) -> DataFrame
```

获取股票最新交易日成交明细

**Parameters**

*   **stock_code** (*str*) – 股票代码或者股票名称
*   **max_count** (*int, optional*) – 最近的最大数据条数, 默认为 ``1000000``

**Returns**

*   **DataFrame** – 最新交易日成交明细

### `get_history_bill`

```python
efinance.stock.get_history_bill(stock_code: str) -> DataFrame
```

获取单只股票历史单子流入流出数据

**Parameters**

*   **stock_code** (*str*) – 股票代码

**Returns**

*   **DataFrame** – 沪深市场单只股票历史单子流入流出数据

### `get_latest_holder_number`

```python
efinance.stock.get_latest_holder_number(date: str = None) -> DataFrame
```

获取沪深A股市场最新公开的股东数目变化情况 也可获取指定报告期的股东数目变化情况

**Parameters**

*   **date** (*str, optional*) – 报告期日期
    *   ``None`` 最新的报告期
    *   ``'2021-06-30'`` 2021年中报
    *   ``'2021-03-31'`` 2021年一季报

**Returns**

*   **DataFrame** – 沪深A股市场最新公开的或指定报告期的股东数目变化情况

### `get_latest_ipo_info`

```python
efinance.stock.get_latest_ipo_info() -> DataFrame
```

获取企业 IPO 审核状态

**Returns**

*   **DataFrame** – 企业 IPO 审核状态

### `get_latest_quote`

```python
efinance.stock.get_latest_quote(stock_codes: Union[str, List[str]], **kwargs) -> DataFrame
```

获取沪深市场多只股票的实时涨幅情况

**Parameters**

*   **stock_codes** (*Union[str, List[str]]*) – 单只股票代码或者多只股票代码构成的列表
    *   ``'600519'``
    *   ``['600519','300750']``

**Returns**

*   **DataFrame** – 沪深市场、港股、美股多只股票的实时涨幅情况

### `get_members`

```python
efinance.stock.get_members(index_code: str) -> DataFrame
```

获取指数成分股信息

**Parameters**

*   **index_code** (*str*) – 指数名称或者指数代码

**Returns**

*   **DataFrame** – 指数成分股信息

### `get_quote_history`

```python
efinance.stock.get_quote_history(
    stock_codes: Union[str, List[str]],
    beg: str = '19000101',
    end: str = '20500101',
    klt: int = 101,
    fqt: int = 1,
    market_type: MarketType | None = None,
    suppress_error: bool = False,
    use_id_cache: bool = True,
    **kwargs
) -> Union[DataFrame, Dict[str, DataFrame]]
```

获取股票的 K 线数据

**Parameters**

*   **stock_codes** (*Union[str, List[str]]*) – 股票代码、名称 或者 股票代码、名称构成的列表
*   **beg** (*str, optional*) – 开始日期，默认为 ``'19000101'``
*   **end** (*str, optional*) – 结束日期，默认为 ``'20500101'``
*   **klt** (*int, optional*) – 行情之间的时间间隔，默认为 ``101``
    *   ``1`` : 分钟
    *   ``5`` : 5 分钟
    *   ``15`` : 15 分钟
    *   ``30`` : 30 分钟
    *   ``60`` : 60 分钟
    *   ``101`` : 日
    *   ``102`` : 周
    *   ``103`` : 月
*   **fqt** (*int, optional*) – 复权方式，默认为 ``1``
    *   ``0`` : 不复权
    *   ``1`` : 前复权
    *   ``2`` : 后复权
*   **market_type** (*MarketType, optional*) – 市场类型
    *   ``A_stock`` : A股
    *   ``Hongkong`` : 香港
    *   ``London_stock_exchange`` : 英股
    *   ``US_stock`` : 美股
*   **suppress_error** (*bool, optional*) – 遇到未查到的股票代码，是否不报错，返回空的DataFrame
*   **use_id_cache** (*bool, optional*) – 是否使用本地缓存的东方财富股票行情ID

**Returns**

*   **Union[DataFrame, Dict[str, DataFrame]]**
    *   ``DataFrame`` : 当 ``stock_codes`` 是 ``str`` 时
    *   ``Dict[str, DataFrame]`` : 当 ``stock_codes`` 是 ``List[str]`` 时

### `get_quote_snapshot`

```python
efinance.stock.get_quote_snapshot(stock_code: str) -> Series
```

获取沪深市场股票最新行情快照

**Parameters**

*   **stock_code** (*str*) – 股票代码

**Returns**

*   **Series**

### `get_realtime_quotes`

```python
efinance.stock.get_realtime_quotes(fs: Union[str, List[str]] = None, **kwargs) -> DataFrame
```

获取单个或者多个市场行情的最新状况

**Parameters**

*   **fs** (*Union[str, List[str]], optional*) – 行情名称或者多个行情名列表
    *   ``None`` 沪深京A股市场行情
    *   ``'沪深A股'``
    *   ``'沪A'``
    *   ``'深A'``
    *   ``'北A'``
    *   ``'可转债'``
    *   ``'期货'``
    *   ``'创业板'``
    *   ``'美股'``
    *   ``'港股'``
    *   ``'中概股'``
    *   ``'新股'``
    *   ``'科创板'``
    *   ``'沪股通'``
    *   ``'深股通'``
    *   ``'行业板块'``
    *   ``'概念板块'``
    *   ``'沪深系列指数'``
    *   ``'上证系列指数'``
    *   ``'深证系列指数'``
    *   ``'ETF'``
    *   ``'LOF'``

**Returns**

*   **DataFrame** – 单个或者多个市场行情的最新状况

### `get_today_bill`

```python
efinance.stock.get_today_bill(stock_code: str) -> DataFrame
```

获取单只股票最新交易日的日内分钟级单子流入流出数据

**Parameters**

*   **stock_code** (*str*) – 股票代码

**Returns**

*   **DataFrame** – 单只股票最新交易日的日内分钟级单子流入流出数据

### `get_top10_stock_holder_info`

```python
efinance.stock.get_top10_stock_holder_info(stock_code: str, top: int = 4) -> DataFrame
```

获取沪深市场指定股票前十大股东信息

**Parameters**

*   **stock_code** (*str*) – 股票代码
*   **top** (*int, optional*) – 最新 top 个前 10 大流通股东公开信息, 默认为 ``4``

**Returns**

*   **DataFrame** – 个股持仓占比前 10 的股东的一些信息

## Fund

### `get_base_info`

```python
efinance.fund.get_base_info(fund_codes: Union[str, List[str]]) -> Union[Series, DataFrame]
```

获取基金的一些基本信息

**Parameters**

*   **fund_codes** (*Union[str, List[str]]*) – 6 位基金代码 或多个 6 位 基金代码构成的列表

**Returns**

*   **Union[Series, DataFrame]**
    *   ``Series`` : 包含单只基金基本信息(当 ``fund_codes`` 是字符串时)
    *   ``DataFrame`` : 包含多只基金基本信息(当 ``fund_codes`` 是字符串列表时)

### `get_fund_codes`

```python
efinance.fund.get_fund_codes(ft: str = None) -> DataFrame
```

获取天天基金网公开的全部公募基金名单

**Parameters**

*   **ft** (*str, optional*) – 基金类型
    *   ``'zq'`` : 债券类型基金
    *   ``'gp'`` : 股票类型基金
    *   ``'etf'`` : ETF 基金
    *   ``'hh'`` : 混合型基金
    *   ``'zs'`` : 指数型基金
    *   ``'fof'`` : FOF 基金
    *   ``'qdii'``: QDII 型基金
    *   ``None`` : 全部

**Returns**

*   **DataFrame** – 天天基金网基金名单数据

### `get_fund_manager`

```python
efinance.fund.get_fund_manager(ft: str) -> DataFrame
```

### `get_industry_distribution`

```python
efinance.fund.get_industry_distribution(fund_code: str, dates: Union[str, List[str]] = None) -> DataFrame
```

获取指定基金行业分布信息

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码
*   **dates** (*Union[str, List[str]], optional*) – 日期
    *   ``None`` : 最新公开日期
    *   ``'2020-01-01'`` : 一个公开持仓日期
    *   ``['2020-12-31' ,'2019-12-31']`` : 多个公开持仓日期

**Returns**

*   **DataFrame** – 指定基金行业持仓信息

### `get_invest_position`

```python
efinance.fund.get_invest_position(fund_code: str, dates: Union[str, List[str]] = None) -> DataFrame
```

获取基金持仓占比数据

**Parameters**

*   **fund_code** (*str*) – 基金代码
*   **dates** (*Union[str, List[str]], optional*) – 日期或者日期构成的列表
    *   ``None`` : 最新公开日期
    *   ``'2020-01-01'`` : 一个公开持仓日期
    *   ``['2020-12-31' ,'2019-12-31']`` : 多个公开持仓日期

**Returns**

*   **DataFrame** – 基金持仓占比数据

### `get_pdf_reports`

```python
efinance.fund.get_pdf_reports(fund_code: str, max_count: int = 12, save_dir: str = 'pdf') -> None
```

根据基金代码获取其全部 pdf 报告

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码
*   **max_count** (*int, optional*) – 要获取的最大个数个 pdf (从最新的的开始数), 默认为 ``12``
*   **save_dir** (*str, optional*) – pdf 保存的文件夹路径, 默认为 ``'pdf'``

### `get_period_change`

```python
efinance.fund.get_period_change(fund_code: str) -> DataFrame
```

获取基金阶段涨跌幅度

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码

**Returns**

*   **DataFrame** – 指定基金的阶段涨跌数据

### `get_public_dates`

```python
efinance.fund.get_public_dates(fund_code: str) -> List[str]
```

获取历史上更新持仓情况的日期列表

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码

**Returns**

*   **List[str]** – 指定基金公开持仓的日期列表

### `get_quote_history`

```python
efinance.fund.get_quote_history(fund_code: str, pz: int = 40000) -> DataFrame
```

根据基金代码和要获取的页码抓取基金净值信息

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码
*   **pz** (*int, optional*) – 页码, 默认为 40000 以获取全部历史数据

**Returns**

*   **DataFrame** – 包含基金历史净值等数据

### `get_quote_history_multi`

```python
efinance.fund.get_quote_history_multi(fund_codes: List[str], pz: int = 40000, **kwargs) -> Dict[str, DataFrame]
```

### `get_realtime_increase_rate`

```python
efinance.fund.get_realtime_increase_rate(fund_codes: Union[List[str], str]) -> DataFrame
```

获取基金实时估算涨跌幅度

**Parameters**

*   **fund_codes** (*Union[List[str], str]*) – 6 位基金代码或者 6 位基金代码构成的字符串列表

**Returns**

*   **DataFrame** – 单只或者多只基金实时估算涨跌情况

### `get_types_percentage`

```python
efinance.fund.get_types_percentage(fund_code: str, dates: Union[List[str], str, None] = None) -> DataFrame
```

获取指定基金不同类型占比信息

**Parameters**

*   **fund_code** (*str*) – 6 位基金代码
*   **dates** (*Union[List[str], str, None]*) – 可选值类型示例如下
    *   ``None`` : 最新公开日期
    *   ``'2020-01-01'`` : 一个公开持仓日期
    *   ``['2020-12-31' ,'2019-12-31']`` : 多个公开持仓日期

**Returns**

*   **DataFrame** – 指定基金的在不同日期的不同类型持仓占比信息

## Bond

### `get_all_base_info`

```python
efinance.bond.get_all_base_info() -> DataFrame
```

获取全部债券基本信息列表

**Returns**

*   **DataFrame** – 债券一些基本信息

### `get_base_info`

```python
efinance.bond.get_base_info(bond_codes: Union[str, List[str]]) -> Union[DataFrame, Series]
```

获取单只或多只债券基本信息

**Parameters**

*   **bond_codes** (*Union[str, List[str]]*) – 债券代码、名称 或者 债券代码、名称构成的列表

**Returns**

*   **Union[DataFrame, Series]**
    *   ``DataFrame`` : 当 ``bond_codes`` 是字符串列表时
    *   ``Series`` : 当 ``bond_codes`` 是字符串时

### `get_deal_detail`

```python
efinance.bond.get_deal_detail(bond_code: str, max_count: int = 1000000, **kwargs) -> DataFrame
```

获取债券最新交易日成交明细

**Parameters**

*   **bond_code** (*str*) – 债券代码或者名称
*   **max_count** (*int, optional*) – 最近的最大数据条数, 默认为 ``1000000``

**Returns**

*   **DataFrame** – 债券最新交易日成交明细

### `get_history_bill`

```python
efinance.bond.get_history_bill(bond_code: str) -> DataFrame
```

获取单支债券的历史单子流入流出数据

**Parameters**

*   **bond_code** (*str*) – 债券代码

**Returns**

*   **DataFrame** – 沪深市场单只债券历史单子流入流出数据

### `get_quote_history`

```python
efinance.bond.get_quote_history(
    bond_codes: Union[str, List[str]],
    beg: str = '19000101',
    end: str = '20500101',
    klt: int = 101,
    fqt: int = 1,
    **kwargs
) -> Union[DataFrame, Dict[str, DataFrame]]
```

获取债券的 K 线数据

**Parameters**

*   **bond_codes** (*Union[str, List[str]]*) – 债券代码、名称 或者 代码、名称构成的列表
*   **beg** (*str, optional*) – 开始日期，默认为 ``'19000101'``
*   **end** (*str, optional*) – 结束日期，默认为 ``'20500101'``
*   **klt** (*int, optional*) – 行情之间的时间间隔，默认为 ``101``
    *   ``1`` : 分钟
    *   ``5`` : 5 分钟
    *   ``15`` : 15 分钟
    *   ``30`` : 30 分钟
    *   ``60`` : 60 分钟
    *   ``101`` : 日
    *   ``102`` : 周
    *   ``103`` : 月
*   **fqt** (*int, optional*) – 复权方式，默认为 ``1``
    *   ``0`` : 不复权
    *   ``1`` : 前复权
    *   ``2`` : 后复权

**Returns**

*   **Union[DataFrame, Dict[str, DataFrame]]**
    *   ``DataFrame`` : 当 ``codes`` 是 ``str`` 时
    *   ``Dict[str, DataFrame]`` : 当 ``bond_codes`` 是 ``List[str]`` 时

### `get_realtime_quotes`

```python
efinance.bond.get_realtime_quotes(**kwargs) -> DataFrame
```

获取沪深市场全部债券实时行情信息

**Returns**

*   **DataFrame** – 沪深市场全部债券实时行情信息

### `get_today_bill`

```python
efinance.bond.get_today_bill(bond_code: str) -> DataFrame
```

获取单只债券最新交易日的日内分钟级单子流入流出数据

**Parameters**

*   **bond_code** (*str*) – 债券代码

**Returns**

*   **DataFrame** – 单只债券最新交易日的日内分钟级单子流入流出数据

## Futures

### `get_deal_detail`

```python
efinance.futures.get_deal_detail(quote_id: str, max_count: int = 1000000) -> DataFrame
```

获取期货最新交易日成交明细

**Parameters**

*   **quote_id** (*str*) – 期货行情ID
*   **max_count** (*int, optional*) – 最大返回条数,  默认为 ``1000000``

**Returns**

*   **DataFrame** – 期货最新交易日成交明细

**Notes**

行情ID 格式参考 ``efinance.futures.get_futures_base_info`` 中得到的数据

### `get_futures_base_info`

```python
efinance.futures.get_futures_base_info() -> DataFrame
```

获取四个交易所全部期货基本信息

**Returns**

*   **DataFrame** – 四个交易所全部期货一些基本信息

**Notes**

这里的 行情ID 主要作用是为使用函数 ``efinance.futures.get_quote_history`` 获取期货行情信息提供参数

### `get_quote_history`

```python
efinance.futures.get_quote_history(
    quote_ids: Union[str, List[str]],
    beg: str = '19000101',
    end: str = '20500101',
    klt: int = 101,
    fqt: int = 1,
    **kwargs
) -> DataFrame
```

获取期货历史行情信息

**Parameters**

*   **quote_ids** (*Union[str, List[str]]*) – 一个期货 或者多个期货 行情ID 构成的列表
*   **beg** (*str, optional*) – 开始日期，默认为 ``'19000101'``
*   **end** (*str, optional*) – 结束日期，默认为 ``'20500101'``
*   **klt** (*int, optional*) – 行情之间的时间间隔，默认为 ``101``
    *   ``1`` : 分钟
    *   ``5`` : 5 分钟
    *   ``15`` : 15 分钟
    *   ``30`` : 30 分钟
    *   ``60`` : 60 分钟
    *   ``101`` : 日
    *   ``102`` : 周
    *   ``103`` : 月
*   **fqt** (*int, optional*) – 复权方式，默认为 ``1``
    *   ``0`` : 不复权
    *   ``1`` : 前复权
    *   ``2`` : 后复权

**Returns**

*   **Union[DataFrame, Dict[str, DataFrame]]**
    *   ``DataFrame`` : 当 ``secids`` 是 ``str`` 时
    *   ``Dict[str, DataFrame]`` : 当 ``quote_ids`` 是 ``List[str]`` 时

### `get_realtime_quotes`

```python
efinance.futures.get_realtime_quotes() -> DataFrame
```

获取期货最新行情总体情况

**Returns**

*   **DataFrame** – 期货市场的最新行情信息（涨跌幅、换手率等信息）

**Notes**

如果不记得行情ID,则可以调用函数 ``efinance.futures.get_realtime_quotes`` 获取
接着便可以使用函数 ``efinance.futures.get_quote_history``
来获取期货 K 线数据
