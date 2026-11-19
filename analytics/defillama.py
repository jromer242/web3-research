"""
DefiLlama analytics — free, no-auth on-chain data.

Covers token prices, protocol TVL, DEX volumes, yield opportunities,
stablecoin market caps, and chain-level TVL trends. All endpoints are
completely free with no API key required.

Docs: https://defillama.com/docs/api
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


BASE = "https://api.llama.fi"
COINS = "https://coins.llama.fi"
STABLES = "https://stablecoins.llama.fi"
YIELDS = "https://yields.llama.fi"
VOLUMES = "https://api.llama.fi"

CHAIN_MAP = {
    "ethereum": "ethereum",
    "polygon": "polygon",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "avalanche": "avax",
    "bsc": "bsc",
    "solana": "solana",
}


def _coin_id(chain: str, address: str) -> str:
    return f"{CHAIN_MAP.get(chain, chain)}:{address}"


@dataclass
class DefiLlamaClient:
    """Thin HTTP wrapper with retry."""

    timeout: float = 30.0
    _client: httpx.Client = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Accept": "application/json"},
        )

    def _get(self, url: str, params: dict | None = None) -> Any:
        log.debug("GET %s params=%s", url, params)
        resp = self._client.get(url, params=params)
        log.debug("  -> %s (%d bytes)", resp.status_code, len(resp.content))
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()


class DefiLlamaAnalyzer:
    """Free on-chain analytics via DefiLlama APIs."""

    def __init__(self):
        self._http = DefiLlamaClient()

    # ── Token Prices ────────────────────────────────────────────────────

    def prices_current(
        self,
        tokens: list[tuple[str, str]],
    ) -> dict[str, dict]:
        """Current prices for a list of (chain, address) pairs."""
        coin_ids = ",".join(_coin_id(c, a) for c, a in tokens)
        data = self._http._get(f"{COINS}/prices/current/{coin_ids}")
        result = {}
        for key, info in data.get("coins", {}).items():
            result[info.get("symbol", key)] = {
                "price": info["price"],
                "confidence": info.get("confidence"),
                "decimals": info.get("decimals"),
                "timestamp": info.get("timestamp"),
            }
        return result

    def price_history(
        self,
        chain: str,
        address: str,
        days: int = 30,
        period: str = "1d",
    ) -> list[dict]:
        """Historical prices for a single token.

        period: '1d' for daily, '1h' for hourly (3600s), etc.
        """
        coin_id = _coin_id(chain, address)
        start_ts = int(time.time()) - (days * 86400)

        period_seconds = {"1d": 86400, "1h": 3600, "4h": 14400}.get(period, 86400)
        span = max(1, (days * 86400) // period_seconds)

        params = {"start": start_ts, "span": span, "period": period_seconds}
        data = self._http._get(f"{COINS}/chart/{coin_id}", params)
        coins = data.get("coins", {})
        if coin_id not in coins:
            return []
        return [
            {"timestamp": p["timestamp"], "price": p["price"]}
            for p in coins[coin_id].get("prices", [])
        ]

    def price_at_timestamp(
        self, chain: str, address: str, timestamp: int
    ) -> dict | None:
        """Price of a token at a specific unix timestamp."""
        coin_id = _coin_id(chain, address)
        data = self._http._get(f"{COINS}/prices/historical/{timestamp}/{coin_id}")
        coins = data.get("coins", {})
        if coin_id not in coins:
            return None
        info = coins[coin_id]
        return {
            "price": info["price"],
            "symbol": info.get("symbol"),
            "timestamp": info.get("timestamp"),
        }

    # ── Protocol TVL ────────────────────────────────────────────────────

    def protocols(self, top_n: int = 25) -> list[dict]:
        """Top protocols by TVL across all chains."""
        data = self._http._get(f"{BASE}/protocols")
        sorted_data = sorted(data, key=lambda x: x.get("tvl", 0) or 0, reverse=True)
        return [
            {
                "name": p["name"],
                "slug": p.get("slug", p["name"].lower().replace(" ", "-")),
                "symbol": p.get("symbol"),
                "tvl": p.get("tvl"),
                "change_1d": p.get("change_1d"),
                "change_7d": p.get("change_7d"),
                "chains": p.get("chains", []),
                "category": p.get("category"),
            }
            for p in sorted_data[:top_n]
        ]

    def protocol_detail(self, slug: str) -> dict:
        """Detailed TVL breakdown for a protocol (use slug, e.g. 'aave')."""
        data = self._http._get(f"{BASE}/protocol/{slug}")
        chain_tvls = {}
        skip_suffixes = ("-borrowed", "-staking", "-pool2")
        skip_names = ("borrowed", "staking", "pool2")
        for chain, info in data.get("chainTvls", {}).items():
            if chain.lower() in skip_names or any(chain.lower().endswith(s) for s in skip_suffixes):
                continue
            if isinstance(info, dict) and "tvl" in info:
                latest = info["tvl"][-1] if info["tvl"] else {}
                chain_tvls[chain] = latest.get("totalLiquidityUSD", 0)

        tvl_raw = data.get("tvl")
        if isinstance(tvl_raw, list) and tvl_raw:
            current_tvl = tvl_raw[-1].get("totalLiquidityUSD", 0)
        else:
            current_tvl = tvl_raw or 0

        return {
            "name": data.get("name"),
            "symbol": data.get("symbol"),
            "tvl": current_tvl,
            "category": data.get("category"),
            "chains": data.get("chains", []),
            "chain_tvls": chain_tvls,
            "description": data.get("description"),
        }

    def protocol_tvl_history(self, slug: str) -> list[dict]:
        """Daily TVL history for a protocol."""
        data = self._http._get(f"{BASE}/protocol/{slug}")
        tvl_data = data.get("tvl", [])
        if isinstance(tvl_data, list):
            return [
                {"date": p.get("date"), "tvl": p.get("totalLiquidityUSD")}
                for p in tvl_data
            ]
        return []

    # ── Chain TVL ───────────────────────────────────────────────────────

    def chains(self) -> list[dict]:
        """All chains ranked by TVL."""
        data = self._http._get(f"{BASE}/v2/chains")
        return [
            {"name": c["name"], "tvl": c.get("tvl", 0)}
            for c in sorted(data, key=lambda x: x.get("tvl", 0) or 0, reverse=True)
        ]

    def chain_tvl_history(self, chain: str) -> list[dict]:
        """Daily TVL history for a specific chain."""
        data = self._http._get(f"{BASE}/v2/historicalChainTvl/{chain}")
        return [{"date": p["date"], "tvl": p.get("tvl", 0)} for p in data]

    # ── DEX Volumes ─────────────────────────────────────────────────────

    def dex_volumes(self, top_n: int = 20) -> list[dict]:
        """Top DEXes by 24h volume."""
        data = self._http._get(
            f"{VOLUMES}/overview/dexs",
            params={
                "excludeTotalDataChart": "true",
                "excludeTotalDataChartBreakdown": "true",
            },
        )
        protocols = sorted(
            data.get("protocols", []),
            key=lambda x: x.get("total24h", 0) or 0,
            reverse=True,
        )
        return [
            {
                "name": p["name"],
                "volume_24h": p.get("total24h"),
                "volume_7d": p.get("total7d"),
                "change_1d": p.get("change_1d"),
                "chains": p.get("chains", []),
            }
            for p in protocols[:top_n]
        ]

    def dex_volume_by_chain(self, chain: str, top_n: int = 15) -> list[dict]:
        """DEX volume breakdown for a specific chain."""
        data = self._http._get(
            f"{VOLUMES}/overview/dexs/{chain}",
            params={
                "excludeTotalDataChart": "true",
                "excludeTotalDataChartBreakdown": "true",
            },
        )
        protocols = sorted(
            data.get("protocols", []),
            key=lambda x: x.get("total24h", 0) or 0,
            reverse=True,
        )
        return [
            {
                "name": p["name"],
                "volume_24h": p.get("total24h"),
                "volume_7d": p.get("total7d"),
                "change_1d": p.get("change_1d"),
            }
            for p in protocols[:top_n]
        ]

    # ── Stablecoins ─────────────────────────────────────────────────────

    def stablecoins(self, top_n: int = 15) -> list[dict]:
        """Top stablecoins by circulating supply."""
        data = self._http._get(
            f"{STABLES}/stablecoins", params={"includePrices": "true"}
        )
        assets = sorted(
            data.get("peggedAssets", []),
            key=lambda x: x.get("circulating", {}).get("peggedUSD", 0) or 0,
            reverse=True,
        )
        return [
            {
                "name": s["name"],
                "symbol": s.get("symbol"),
                "circulating": s.get("circulating", {}).get("peggedUSD"),
                "chains": s.get("chains", []),
                "price": s.get("price"),
                "peg_mechanism": s.get("pegMechanism"),
            }
            for s in assets[:top_n]
        ]

    def stablecoin_chain_breakdown(self, stablecoin_id: int) -> dict:
        """Per-chain supply breakdown for a stablecoin (get id from stablecoins())."""
        data = self._http._get(f"{STABLES}/stablecoin/{stablecoin_id}")
        chain_circs = {}
        for chain, hist in data.get("chainCirculating", {}).items():
            if hist and isinstance(hist, list):
                latest = hist[-1].get("circulating", {}).get("peggedUSD", 0)
                chain_circs[chain] = latest
        return {
            "name": data.get("name"),
            "symbol": data.get("symbol"),
            "total_circulating": data.get("circulating", {}).get("peggedUSD"),
            "chains": dict(
                sorted(chain_circs.items(), key=lambda x: x[1], reverse=True)
            ),
        }

    # ── Yields ──────────────────────────────────────────────────────────

    def yields(
        self,
        chain: Optional[str] = None,
        project: Optional[str] = None,
        top_n: int = 25,
        min_tvl: float = 1_000_000,
    ) -> list[dict]:
        """Top yield opportunities, optionally filtered by chain/project."""
        data = self._http._get(f"{YIELDS}/pools")
        pools = data.get("data", [])

        if chain:
            pools = [p for p in pools if p.get("chain", "").lower() == chain.lower()]
        if project:
            pools = [p for p in pools if project.lower() in p.get("project", "").lower()]

        pools = [p for p in pools if (p.get("tvlUsd") or 0) >= min_tvl]
        pools.sort(key=lambda x: x.get("apy", 0) or 0, reverse=True)

        return [
            {
                "symbol": p.get("symbol"),
                "chain": p.get("chain"),
                "project": p.get("project"),
                "apy": p.get("apy"),
                "apy_base": p.get("apyBase"),
                "apy_reward": p.get("apyReward"),
                "tvl": p.get("tvlUsd"),
                "il_risk": p.get("ilRisk"),
                "pool_id": p.get("pool"),
            }
            for p in pools[:top_n]
        ]

    def yield_history(self, pool_id: str) -> list[dict]:
        """Historical APY for a specific pool."""
        data = self._http._get(f"{YIELDS}/chart/{pool_id}")
        return [
            {
                "timestamp": p.get("timestamp"),
                "apy": p.get("apy"),
                "tvl": p.get("tvlUsd"),
            }
            for p in data.get("data", [])
        ]

    # ── Composite Research Methods ──────────────────────────────────────

    def market_overview(self) -> dict:
        """Snapshot: top chains, top DEXes, top stablecoins, top yields."""
        return {
            "top_chains": self.chains()[:10],
            "top_dexes": self.dex_volumes(10),
            "top_stablecoins": self.stablecoins(10),
            "top_yields": self.yields(top_n=10),
        }

    def chain_deep_dive(self, chain: str) -> dict:
        """Full analysis of a single chain: TVL, DEX activity, yields."""
        return {
            "dex_volumes": self.dex_volume_by_chain(chain),
            "top_yields": self.yields(chain=chain, top_n=15),
        }

    def token_price_check(
        self,
        tokens: list[tuple[str, str]],
    ) -> list[dict]:
        """Quick price check for multiple tokens with formatting."""
        prices = self.prices_current(tokens)
        return [
            {
                "symbol": symbol,
                "price": info["price"],
                "confidence": info.get("confidence"),
            }
            for symbol, info in prices.items()
        ]
