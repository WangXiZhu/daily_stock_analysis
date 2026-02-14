import akshare as ak
import time

code = 'HK09988'
print(f"Testing {code}")

try:
    start = time.time()
    df = ak.stock_hk_spot_em()
    elapsed = time.time() - start
    print(f"EM (full market): {len(df)} rows, {elapsed:.2f}s")
    print(df[df['代码'] == '09988'])
except Exception as e:
    print(f"EM failed: {e}")

try:
    start = time.time()
    # Sina? Usually stock_hk_spot returns full market too?
    df = ak.stock_hk_spot()
    elapsed = time.time() - start
    print(f"Sina: {len(df)} rows, {elapsed:.2f}s")
    print(df[df['symbol'] == '00988' if 'symbol' in df else df.columns])
except Exception as e:
    print(f"Sina failed: {e}")
