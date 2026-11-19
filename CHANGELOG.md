# Changelog

## [Unreleased]

### Fixed
- Protocol Deep Dive crashing on protocols like OKX — slug was derived from
  the `url` field (producing `www.okx.com`) instead of the API's `slug` field.
  Added error handling for failed protocol lookups. (b685b65)

## [0.1.0] — 2026-11-19

### Added
- **CLI** (`cli.py`): 28 commands across 3 subgroups — wallet profiling,
  ERC-20 token analysis, Uniswap V3 pool discovery, gas prices, swap
  pipeline (quote/approve/execute), Dune SQL queries, DefiLlama analytics.
- **Analytics modules**:
  - `analytics/wallet.py` — multi-chain wallet profiling (Polygon, Ethereum, Base)
  - `analytics/tokens.py` — ERC-20 info, transfer events, top holders
  - `analytics/pools.py` — Uniswap V3 pool discovery and state
  - `analytics/dune.py` — 6 parameterized DuneSQL queries (whale detection,
    exchange flows, smart money accumulation, holder concentration)
  - `analytics/defillama.py` — 15+ methods covering token prices, protocol TVL,
    DEX volumes, stablecoins, yields, chain analysis (free, no API key)
- **Swap pipeline** (`swaps/`): quote, approve, execute via Uniswap V3
  SwapRouter02 on Polygon.
- **Streamlit dashboard** (`dashboard/app.py`): 5 interactive pages —
  Market Overview, Protocol Deep Dive, DEX Volumes, Yield Explorer,
  Price Tracker. All data cached 5min, no API key required.
- **Config**: RPC endpoints with Infura fallback to free public RPCs,
  token addresses for Polygon/Ethereum/Base, Uniswap V3 contract addresses.
- **Contract ABIs**: ERC-20, Uniswap V3 Factory, Pool, QuoterV2, SwapRouter.
