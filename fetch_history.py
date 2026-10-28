"""market-data-history: 시장 데이터 일봉 히스토리 수집

GitHub Actions에서 실행 → data/*.csv 커밋.
- Yahoo (yfinance): 지수·ETF 종가 / 수정종가
- FRED: HY OAS, 금리 (FRED_API_KEY 시크릿 있으면 API, 없으면 fredgraph.csv)
- CNN Fear & Greed: whit3rabbit/fear-greed-data CSV
"""
import io
import json
import os
import signal
import sys
import time
import warnings

warnings.filterwarnings("ignore")
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

START = "2010-01-01"
OUT = "data"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

YAHOO = {
    # 지수
    "SPX": "^GSPC", "NDX": "^NDX", "IXIC": "^IXIC", "RUT": "^RUT",
    # 변동성
    "VIX": "^VIX", "VIX3M": "^VIX3M", "VIX9D": "^VIX9D", "VVIX": "^VVIX",
    "VXN": "^VXN", "SKEW": "^SKEW",
    # ETF (섹터·신용·채권)
    "QQQ": "QQQ", "SPY": "SPY", "SOXX": "SOXX", "SMH": "SMH", "HYG": "HYG",
    "LQD": "LQD", "TLT": "TLT", "XLP": "XLP", "XLY": "XLY", "KRE": "KRE", "IWM": "IWM",
    # 매크로
    "DXY": "DX-Y.NYB", "TNX": "^TNX",
}

FRED = ["BAMLH0A0HYM2", "BAMLC0A0CM", "DGS10", "DGS2", "T10Y2Y", "DGS3MO"]

FG_URL = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout("hard timeout")


signal.signal(signal.SIGALRM, _alarm)


def with_timeout(sec, fn, *a, **k):
    """요청이 멈춰도 sec초 뒤 강제 중단 (Linux 전용)"""
    signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)


def fetch_yahoo(ticker, tries=3):
    for i in range(tries):
        try:
            df = with_timeout(60, yf.Ticker(ticker).history, start=START, interval="1d",
                              auto_adjust=False, timeout=30)
            if df is not None and len(df) > 0:
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                return df
            print(f"  ! {ticker} try{i+1}: empty")
        except Exception as e:
            print(f"  ! {ticker} try{i+1}: {e}")
        time.sleep(3 * (i + 1))
    return None


def fetch_fred(series):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        try:
            r = with_timeout(60, requests.get, "https://api.stlouisfed.org/fred/series/observations",
                             params={"series_id": series, "api_key": key, "file_type": "json",
                                     "observation_start": START}, timeout=(10, 30))
            r.raise_for_status()
            obs = r.json()["observations"]
            s = pd.Series({pd.Timestamp(o["date"]): o["value"] for o in obs})
            return pd.to_numeric(s, errors="coerce").rename(series), "api"
        except Exception as e:
            print(f"  ! FRED API {series}: {e} → fredgraph 시도")
    for i in range(2):
        try:
            r = with_timeout(60, requests.get, "https://fred.stlouisfed.org/graph/fredgraph.csv",
                             params={"id": series, "cosd": START}, headers=UA, timeout=(10, 40))
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                          index=pd.to_datetime(df.iloc[:, 0]), name=series)
            return s, "fredgraph"
        except Exception as e:
            print(f"  ! fredgraph {series} try{i+1}: {e}")
            time.sleep(5 * (i + 1))
    return None, "fail"


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {"updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "start": START, "yahoo": {}, "fred": {}, "fear_greed": {}}

    close, adj = {}, {}
    for name, tk in YAHOO.items():
        df = fetch_yahoo(tk)
        if df is None:
            manifest["yahoo"][name] = {"ticker": tk, "status": "fail"}
            print(f"✗ {name} ({tk})")
            continue
        close[name] = df["Close"]
        if "Adj Close" in df:
            adj[name] = df["Adj Close"]
        manifest["yahoo"][name] = {"ticker": tk, "status": "ok", "rows": int(len(df)),
                                   "first": str(df.index[0].date()), "last": str(df.index[-1].date())}
        print(f"✓ {name} {len(df)} rows → {df.index[-1].date()}")
        time.sleep(0.5)

    c = pd.DataFrame(close).sort_index()
    c.index.name = "date"
    c.round(4).to_csv(f"{OUT}/yahoo_close.csv")
    a = pd.DataFrame(adj).sort_index()
    a.index.name = "date"
    a.round(4).to_csv(f"{OUT}/yahoo_adjclose.csv")

    fr = []
    for s in FRED:
        ser, how = fetch_fred(s)
        if ser is None:
            manifest["fred"][s] = {"status": "fail"}
            print(f"✗ FRED {s}")
            continue
        ser = ser.dropna()
        fr.append(ser)
        manifest["fred"][s] = {"status": "ok", "via": how, "rows": int(len(ser)),
                               "last": str(ser.index[-1].date())}
        print(f"✓ FRED {s} ({how}) → {ser.index[-1].date()}")
    if fr:
        f = pd.concat(fr, axis=1).sort_index()
        f.index.name = "date"
        f.to_csv(f"{OUT}/fred.csv")

    try:
        r = with_timeout(60, requests.get, FG_URL, timeout=(10, 30))
        r.raise_for_status()
        g = pd.read_csv(io.StringIO(r.text))
        g.columns = ["date", "fear_greed", "rating"][: len(g.columns)]
        g.to_csv(f"{OUT}/fear_greed.csv", index=False)
        manifest["fear_greed"] = {"status": "ok", "rows": int(len(g)), "last": str(g["date"].iloc[-1])}
        print(f"✓ F&G → {g['date'].iloc[-1]}")
    except Exception as e:
        manifest["fear_greed"] = {"status": "fail", "error": str(e)}
        print(f"✗ F&G: {e}")

    with open(f"{OUT}/manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    # 최소 품질 기준: 핵심 시리즈 누락 시 실패 처리 (기존 데이터를 덮어쓰지 않도록)
    core_ok = all(manifest["yahoo"].get(k, {}).get("status") == "ok" for k in ("SPX", "NDX", "VIX"))
    if not core_ok or len(c) < 3000:
        print("❌ 핵심 시리즈(SPX/NDX/VIX) 누락 또는 행 수 부족 — 실패 처리")
        sys.exit(1)


if __name__ == "__main__":
    main()
