# market-data-history

Market Signal Monitor 검증용 시장 데이터 일봉 히스토리 (2010~). GitHub Actions가 평일 KST 08:23에 자동 갱신.

| 파일 | 내용 |
|---|---|
| `data/yahoo_close.csv` | 지수·변동성·ETF 종가 (SPX, NDX, IXIC, VIX, VIX3M, VXN, SKEW, SOXX, HYG 등) |
| `data/yahoo_adjclose.csv` | 수정종가 (배당 반영, ETF 수익률 계산용) |
| `data/fred.csv` | HY OAS, IG OAS, DGS10, DGS2, T10Y2Y, DGS3MO |
| `data/fear_greed.csv` | CNN Fear & Greed (whit3rabbit/fear-greed-data 미러) |
| `data/manifest.json` | 시리즈별 수집 상태·마지막 날짜 |

- FRED: 저장소 시크릿 `FRED_API_KEY`가 있으면 공식 API, 없으면 fredgraph.csv로 수집.
- 핵심 시리즈(SPX/NDX/VIX) 수집 실패 시 커밋하지 않음.
- 수동 실행: Actions → History Backfill → Run workflow.
