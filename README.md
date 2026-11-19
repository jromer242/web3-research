# Web3 Research Toolkit

On-chain analytics CLI and dashboard for DeFi research — token prices, protocol TVL, DEX volumes, yield opportunities, whale tracking, and market structure analysis.

## Features

### CLI (`cli.py`)
28 commands across three domains:

- **Wallet & Token Analysis** — multi-chain wallet profiling (Polygon, Ethereum, Base), ERC-20 token info, transfer events, top holders
- **DEX & Pools** — Uniswap V3 pool discovery, gas prices, swap pipeline (quote → approve → execute)
- **Research Analytics** — DefiLlama market data (free, no key) + Dune SQL queries (whale detection, exchange flows, smart money accumulation)

```bash
# DefiLlama (free)
python cli.py defi overview
python cli.py defi prices ethereum 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
python cli.py defi protocol aave

# Dune (requires API key)
python cli.py dune run wallet_dex_activity --wallet-address 0x...

# On-chain
python cli.py wallet 0x...
python cli.py gas
```

### Streamlit Dashboard (`dashboard/app.py`)
Interactive analytics dashboard — no API key required.

- **Market Overview** — chain TVL rankings, stablecoin market caps, top protocols
- **Protocol Deep Dive** — per-chain TVL breakdown with bar + pie charts
- **DEX Volumes** — global and per-chain volume analysis
- **Yield Explorer** — APY vs TVL scatter plot with chain/protocol filters
- **Price Tracker** — historical price charts for major tokens + custom input

```bash
streamlit run dashboard/app.py
```

### Analytics Modules (`analytics/`)

| Module | Coverage | Auth |
|--------|----------|------|
| `defillama.py` | Token prices, protocol TVL, DEX volumes, stablecoins, yields | Free |
| `dune.py` | 6 parameterized SQL queries for on-chain research | API key ($65/mo) |
| `wallet.py` | Multi-chain wallet profiling via RPC | RPC endpoint |
| `tokens.py` | ERC-20 info, transfers, holder analysis | RPC endpoint |
| `pools.py` | Uniswap V3 pool discovery and state | RPC endpoint |

## Setup

```bash
python -m venv .venv-web3-research
source .venv-web3-research/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Required | Notes |
|----------|----------|-------|
| `WEB3_WALLET_ADDRESS` | For wallet commands | Your EVM address |
| `INFURA_KEY` | For RPC commands | Free tier works |
| `DUNE_API_KEY` | For Dune queries | Analyst plan, 4000 credits/mo |

DefiLlama endpoints require no authentication.

## Project Structure

```
web3-research/
├── analytics/          # Core analysis modules
│   ├── defillama.py    # DefiLlama API client + analyzer
│   ├── dune.py         # Dune SQL query library
│   ├── wallet.py       # Wallet profiling
│   ├── tokens.py       # ERC-20 analysis
│   └── pools.py        # Uniswap V3 pools
├── dashboard/
│   └── app.py          # Streamlit dashboard
├── config/             # RPC endpoints, token addresses, ABIs
├── contracts/          # Contract ABI JSON files
├── swaps/              # Uniswap V3 swap pipeline
├── cli.py              # Typer CLI entrypoint
└── requirements.txt
```

## License

MIT
