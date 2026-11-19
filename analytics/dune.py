"""
Dune Analytics integration for on-chain research.

Parameterized SQL queries for wallet profiling, whale detection,
exchange flow analysis, and market structure research.

API access requires DUNE_API_KEY (Analyst plan, $65/mo, 4000 credits).
Without a key, use get_sql() to export queries for Dune's web editor.
"""
import os
from typing import Any, Optional


QUERIES: dict[str, dict[str, Any]] = {
    "wallet_dex_activity": {
        "description": "DEX trades for a wallet — protocol, pairs, USD value, timestamps",
        "sql": """\
SELECT
    block_time,
    project AS dex,
    token_bought_symbol,
    token_sold_symbol,
    token_bought_amount,
    token_sold_amount,
    amount_usd,
    tx_hash
FROM dex.trades
WHERE blockchain = '{{blockchain}}'
    AND taker = {{wallet_address}}
    AND block_time >= NOW() - INTERVAL '{{days}}' DAY
ORDER BY block_time DESC
LIMIT {{limit}}""",
        "params": {
            "wallet_address": {"type": "address", "required": True},
            "blockchain": {"type": "text", "default": "ethereum"},
            "days": {"type": "number", "default": 30},
            "limit": {"type": "number", "default": 200},
        },
    },
    "token_large_transfers": {
        "description": "Whale movements — large ERC-20 transfers above a USD threshold",
        "sql": """\
SELECT
    t.evt_block_time AS block_time,
    t."from" AS sender,
    t."to" AS receiver,
    CAST(t.value AS DOUBLE) / POWER(10, tok.decimals) AS amount,
    CAST(t.value AS DOUBLE) / POWER(10, tok.decimals) * p.price AS amount_usd,
    tok.symbol,
    t.evt_tx_hash AS tx_hash,
    ls.name AS sender_label,
    lr.name AS receiver_label
FROM erc20_{{blockchain}}.evt_Transfer t
JOIN tokens.erc20 tok
    ON tok.contract_address = t.contract_address
    AND tok.blockchain = '{{blockchain}}'
LEFT JOIN prices.usd p
    ON p.contract_address = t.contract_address
    AND p.blockchain = '{{blockchain}}'
    AND p.minute = DATE_TRUNC('minute', t.evt_block_time)
LEFT JOIN labels.addresses ls
    ON ls.address = t."from"
    AND ls.blockchain = '{{blockchain}}'
LEFT JOIN labels.addresses lr
    ON lr.address = t."to"
    AND lr.blockchain = '{{blockchain}}'
WHERE t.contract_address = {{token_address}}
    AND t.evt_block_time >= NOW() - INTERVAL '{{days}}' DAY
    AND CAST(t.value AS DOUBLE) / POWER(10, tok.decimals) * p.price >= {{min_usd}}
ORDER BY amount_usd DESC
LIMIT {{limit}}""",
        "params": {
            "token_address": {"type": "address", "required": True},
            "blockchain": {"type": "text", "default": "ethereum"},
            "days": {"type": "number", "default": 7},
            "min_usd": {"type": "number", "default": 100000},
            "limit": {"type": "number", "default": 100},
        },
    },
    "exchange_net_flows": {
        "description": "Hourly token flows to/from CEX wallets — net inflow signals sell pressure",
        "sql": """\
WITH cex_wallets AS (
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE category = 'exchange'
        AND blockchain = '{{blockchain}}'
),
flows AS (
    SELECT
        DATE_TRUNC('hour', t.evt_block_time) AS hour,
        CASE
            WHEN t."to" IN (SELECT address FROM cex_wallets) THEN 'inflow'
            WHEN t."from" IN (SELECT address FROM cex_wallets) THEN 'outflow'
        END AS direction,
        CAST(t.value AS DOUBLE) / POWER(10, tok.decimals) AS amount,
        CAST(t.value AS DOUBLE) / POWER(10, tok.decimals) * p.price AS amount_usd
    FROM erc20_{{blockchain}}.evt_Transfer t
    JOIN tokens.erc20 tok
        ON tok.contract_address = t.contract_address
        AND tok.blockchain = '{{blockchain}}'
    LEFT JOIN prices.usd p
        ON p.contract_address = t.contract_address
        AND p.blockchain = '{{blockchain}}'
        AND p.minute = DATE_TRUNC('minute', t.evt_block_time)
    WHERE t.contract_address = {{token_address}}
        AND t.evt_block_time >= NOW() - INTERVAL '{{days}}' DAY
        AND (
            t."to" IN (SELECT address FROM cex_wallets)
            OR t."from" IN (SELECT address FROM cex_wallets)
        )
)
SELECT
    hour,
    SUM(CASE WHEN direction = 'inflow' THEN amount_usd ELSE 0 END) AS inflow_usd,
    SUM(CASE WHEN direction = 'outflow' THEN amount_usd ELSE 0 END) AS outflow_usd,
    SUM(CASE WHEN direction = 'inflow' THEN amount_usd ELSE 0 END)
        - SUM(CASE WHEN direction = 'outflow' THEN amount_usd ELSE 0 END) AS net_flow_usd,
    SUM(CASE WHEN direction = 'inflow' THEN amount ELSE 0 END) AS inflow_tokens,
    SUM(CASE WHEN direction = 'outflow' THEN amount ELSE 0 END) AS outflow_tokens
FROM flows
GROUP BY hour
ORDER BY hour DESC""",
        "params": {
            "token_address": {"type": "address", "required": True},
            "blockchain": {"type": "text", "default": "ethereum"},
            "days": {"type": "number", "default": 7},
        },
    },
    "token_holder_concentration": {
        "description": "Top holders by on-chain balance — supply concentration and entity labels",
        "sql": """\
WITH received AS (
    SELECT
        "to" AS address,
        SUM(CAST(value AS DOUBLE)) / POWER(10, {{decimals}}) AS total_in
    FROM erc20_{{blockchain}}.evt_Transfer
    WHERE contract_address = {{token_address}}
    GROUP BY "to"
),
sent AS (
    SELECT
        "from" AS address,
        SUM(CAST(value AS DOUBLE)) / POWER(10, {{decimals}}) AS total_out
    FROM erc20_{{blockchain}}.evt_Transfer
    WHERE contract_address = {{token_address}}
    GROUP BY "from"
),
balances AS (
    SELECT
        COALESCE(r.address, s.address) AS address,
        COALESCE(r.total_in, 0) - COALESCE(s.total_out, 0) AS balance
    FROM received r
    FULL OUTER JOIN sent s ON r.address = s.address
)
SELECT
    b.address,
    l.name AS label,
    l.category,
    b.balance,
    b.balance * 100.0 / SUM(b.balance) OVER () AS pct_supply
FROM balances b
LEFT JOIN labels.addresses l
    ON l.address = b.address
    AND l.blockchain = '{{blockchain}}'
WHERE b.balance > 0
ORDER BY b.balance DESC
LIMIT {{limit}}""",
        "params": {
            "token_address": {"type": "address", "required": True},
            "blockchain": {"type": "text", "default": "ethereum"},
            "decimals": {"type": "number", "default": 18},
            "limit": {"type": "number", "default": 50},
        },
    },
    "dex_pair_volume": {
        "description": "Daily DEX volume by protocol for a token pair — market structure view",
        "sql": """\
SELECT
    block_date,
    project AS dex,
    COUNT(*) AS num_trades,
    SUM(amount_usd) AS volume_usd,
    AVG(amount_usd) AS avg_trade_usd
FROM dex.trades
WHERE blockchain = '{{blockchain}}'
    AND (
        (token_bought_symbol = '{{token_a}}' AND token_sold_symbol = '{{token_b}}')
        OR (token_bought_symbol = '{{token_b}}' AND token_sold_symbol = '{{token_a}}')
    )
    AND block_time >= NOW() - INTERVAL '{{days}}' DAY
GROUP BY block_date, project
ORDER BY block_date DESC, volume_usd DESC""",
        "params": {
            "token_a": {"type": "text", "default": "WETH"},
            "token_b": {"type": "text", "default": "USDC"},
            "blockchain": {"type": "text", "default": "ethereum"},
            "days": {"type": "number", "default": 30},
        },
    },
    "smart_money_accumulation": {
        "description": "Wallets accumulating a token via DEX buys — early positioning detection",
        "sql": """\
WITH buys AS (
    SELECT
        taker AS wallet,
        SUM(token_bought_amount) AS total_bought,
        SUM(amount_usd) AS total_usd,
        COUNT(*) AS num_trades,
        MIN(block_time) AS first_buy,
        MAX(block_time) AS last_buy
    FROM dex.trades
    WHERE blockchain = '{{blockchain}}'
        AND token_bought_address = {{token_address}}
        AND block_time >= NOW() - INTERVAL '{{days}}' DAY
        AND amount_usd > 0
    GROUP BY taker
    HAVING SUM(amount_usd) >= {{min_usd}}
)
SELECT
    b.wallet,
    l.name AS label,
    l.category,
    b.total_bought,
    b.total_usd,
    b.num_trades,
    b.first_buy,
    b.last_buy,
    b.total_usd / b.num_trades AS avg_trade_usd
FROM buys b
LEFT JOIN labels.addresses l
    ON l.address = b.wallet
    AND l.blockchain = '{{blockchain}}'
ORDER BY b.total_usd DESC
LIMIT {{limit}}""",
        "params": {
            "token_address": {"type": "address", "required": True},
            "blockchain": {"type": "text", "default": "ethereum"},
            "days": {"type": "number", "default": 14},
            "min_usd": {"type": "number", "default": 10000},
            "limit": {"type": "number", "default": 50},
        },
    },
}


class DuneAnalyzer:
    """SQL-based on-chain analytics via Dune."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("DUNE_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise EnvironmentError(
                    "DUNE_API_KEY not set. Get one at dune.com/settings/api "
                    "(Analyst plan, $65/mo for 4,000 credits).\n"
                    "Use DuneAnalyzer.get_sql() for queries without an API key."
                )
            from dune_client.client import DuneClient
            self._client = DuneClient(api_key=self.api_key)
        return self._client

    @staticmethod
    def list_queries() -> list[dict[str, str]]:
        return [
            {"name": name, "description": q["description"]}
            for name, q in QUERIES.items()
        ]

    @staticmethod
    def get_sql(query_name: str, **params) -> str:
        """Return query SQL with {{param}} placeholders, or with values substituted."""
        if query_name not in QUERIES:
            available = ", ".join(QUERIES.keys())
            raise ValueError(f"Unknown query: {query_name}. Available: {available}")

        sql = QUERIES[query_name]["sql"]

        if not params:
            return sql

        defaults = {
            k: v.get("default")
            for k, v in QUERIES[query_name]["params"].items()
            if "default" in v
        }
        merged = {**defaults, **params}

        for key, value in merged.items():
            if value is not None:
                sql = sql.replace("{{" + key + "}}", str(value))

        return sql

    def _resolve_params(self, query_name: str, params: dict) -> dict:
        query_def = QUERIES[query_name]
        defaults = {
            k: v.get("default")
            for k, v in query_def["params"].items()
            if "default" in v
        }
        merged = {**defaults, **params}

        missing = [
            k for k, spec in query_def["params"].items()
            if spec.get("required") and merged.get(k) is None
        ]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

        return merged

    def run(self, query_name: str, **params) -> list[dict]:
        """Execute a named query by saved query ID or by creating a temp query."""
        if query_name not in QUERIES:
            available = ", ".join(QUERIES.keys())
            raise ValueError(f"Unknown query: {query_name}. Available: {available}")

        merged = self._resolve_params(query_name, params)

        # If a query_id was passed, run the saved query with parameters
        if "query_id" in merged and merged["query_id"]:
            qid = int(merged.pop("query_id"))
            return self.run_saved(qid, **{
                k: v for k, v in merged.items()
                if v is not None and k in QUERIES[query_name]["params"]
            })

        # Otherwise try to create a temp query (requires Plus plan)
        sql = QUERIES[query_name]["sql"]
        for key, value in merged.items():
            if value is not None:
                sql = sql.replace("{{" + key + "}}", str(value))

        from dune_client.query import QueryBase

        try:
            created = self.client.create_query(
                name=f"web3cli_{query_name}",
                query_sql=sql,
                is_private=True,
            )
        except Exception as e:
            if "403" in str(e) or "Forbidden" in str(e):
                raise PermissionError(
                    f"Your Dune plan doesn't allow creating queries via API.\n"
                    f"Save the SQL on dune.com (use 'dune sql {query_name}'), "
                    f"then rerun with --id <query_id>."
                ) from None
            raise

        query_id = created.base.query_id
        try:
            result = self.client.run_query(QueryBase(query_id=query_id))
            return result.result.rows
        finally:
            try:
                self.client.archive_query(query_id)
            except Exception:
                pass

    def run_saved(self, query_id: int, **params) -> list[dict]:
        """Execute a saved Dune query by its numeric ID."""
        from dune_client.query import QueryBase
        from dune_client.types import QueryParameter

        query_params = []
        for key, value in params.items():
            if isinstance(value, (int, float)):
                query_params.append(QueryParameter.number_type(key, value))
            else:
                query_params.append(QueryParameter.text_type(key, str(value)))

        query = QueryBase(
            query_id=query_id,
            params=query_params if query_params else None,
        )
        result = self.client.run_query(query)
        return result.result.rows

    def get_latest(self, query_id: int) -> list[dict]:
        """Get cached results for a saved query (no execution credits used)."""
        result = self.client.get_latest_result(query_id)
        return result.result.rows

    # ── Convenience methods ──────────────────────────────────────────────

    def wallet_dex_activity(
        self, address: str, blockchain: str = "ethereum",
        days: int = 30, limit: int = 200,
    ) -> list[dict]:
        return self.run(
            "wallet_dex_activity",
            wallet_address=address, blockchain=blockchain,
            days=days, limit=limit,
        )

    def token_large_transfers(
        self, token_address: str, blockchain: str = "ethereum",
        days: int = 7, min_usd: float = 100000, limit: int = 100,
    ) -> list[dict]:
        return self.run(
            "token_large_transfers",
            token_address=token_address, blockchain=blockchain,
            days=days, min_usd=int(min_usd), limit=limit,
        )

    def exchange_net_flows(
        self, token_address: str, blockchain: str = "ethereum", days: int = 7,
    ) -> list[dict]:
        return self.run(
            "exchange_net_flows",
            token_address=token_address, blockchain=blockchain, days=days,
        )

    def token_holder_concentration(
        self, token_address: str, blockchain: str = "ethereum",
        decimals: int = 18, limit: int = 50,
    ) -> list[dict]:
        return self.run(
            "token_holder_concentration",
            token_address=token_address, blockchain=blockchain,
            decimals=decimals, limit=limit,
        )

    def dex_pair_volume(
        self, token_a: str, token_b: str,
        blockchain: str = "ethereum", days: int = 30,
    ) -> list[dict]:
        return self.run(
            "dex_pair_volume",
            token_a=token_a, token_b=token_b,
            blockchain=blockchain, days=days,
        )

    def smart_money_accumulation(
        self, token_address: str, blockchain: str = "ethereum",
        days: int = 14, min_usd: float = 10000, limit: int = 50,
    ) -> list[dict]:
        return self.run(
            "smart_money_accumulation",
            token_address=token_address, blockchain=blockchain,
            days=days, min_usd=int(min_usd), limit=limit,
        )
