"""
Swap pipeline — orchestrates: quote -> approve -> swap -> receipt.
"""
from web3 import Web3
from config.rpc import get_polygon_w3
from config.tokens import POLYGON
from config.wallets import MY_ADDRESS
from analytics.pools import PoolAnalyzer
from analytics.tokens import TokenAnalyzer
from functions.gas_estimate import get_gas_price
from swaps.quote import get_quote
from swaps.approve import check_and_approve
from swaps.execute import build_and_send_swap


class SwapPipeline:
    def __init__(self, w3=None):
        self.w3 = w3 or get_polygon_w3()
        self.pool_analyzer = PoolAnalyzer(self.w3)
        self.token_analyzer = TokenAnalyzer(self.w3)

    def resolve_token(self, symbol_or_address):
        """Resolve a symbol like 'USDC' to its Polygon address, or pass through a raw address."""
        upper = symbol_or_address.upper()
        if upper == "MATIC":
            raise ValueError(
                "Native MATIC cannot be used directly in swaps. Use WMATIC instead."
            )
        if upper in POLYGON:
            return POLYGON[upper]
        if symbol_or_address.startswith("0x"):
            return symbol_or_address
        raise ValueError(
            f"Unknown token: {symbol_or_address}. "
            f"Available: {', '.join(k for k in POLYGON.keys() if k != 'MATIC')}"
        )

    def get_swap_quote(self, token_in_symbol, token_out_symbol, amount_human):
        """
        Get a full quote with human-readable amounts.

        Returns dict with token info, amounts, pool details, gas estimate, rate.
        """
        addr_in = self.resolve_token(token_in_symbol)
        addr_out = self.resolve_token(token_out_symbol)

        info_in = self.token_analyzer.get_info(addr_in)
        info_out = self.token_analyzer.get_info(addr_out)

        best_pool = self.pool_analyzer.find_best_pool(addr_in, addr_out)
        if not best_pool:
            raise ValueError(
                f"No Uniswap V3 pool found for {info_in['symbol']}/{info_out['symbol']}"
            )

        amount_in_raw = int(amount_human * (10 ** info_in["decimals"]))

        quote = get_quote(
            token_in=addr_in,
            token_out=addr_out,
            amount_in_raw=amount_in_raw,
            fee=best_pool["fee"],
            w3=self.w3,
        )

        amount_out_human = quote["amount_out_raw"] / (10 ** info_out["decimals"])

        return {
            "token_in": {
                "address": addr_in,
                "symbol": info_in["symbol"],
                "decimals": info_in["decimals"],
            },
            "token_out": {
                "address": addr_out,
                "symbol": info_out["symbol"],
                "decimals": info_out["decimals"],
            },
            "amount_in_human": amount_human,
            "amount_in_raw": amount_in_raw,
            "amount_out_human": amount_out_human,
            "amount_out_raw": quote["amount_out_raw"],
            "pool_address": best_pool["address"],
            "pool_fee": best_pool["fee"],
            "pool_fee_pct": best_pool["fee_pct"],
            "pool_liquidity": best_pool["liquidity"],
            "gas_estimate_units": quote["gas_estimate"],
            "price": amount_out_human / amount_human if amount_human > 0 else 0,
        }

    def execute_swap(
        self,
        token_in_symbol,
        token_out_symbol,
        amount_human,
        slippage_pct=0.5,
        sender=MY_ADDRESS,
    ):
        """
        Full pipeline: quote -> balance check -> approve -> swap -> receipt.

        Parameters
        ----------
        slippage_pct : float — Slippage tolerance as percentage (0.5 = 0.5%)
        """
        # Step 1: Quote
        quote_result = self.get_swap_quote(token_in_symbol, token_out_symbol, amount_human)

        # Step 2: Balance check
        balance = self.token_analyzer.get_balance_of(
            quote_result["token_in"]["address"], sender
        )
        if balance < amount_human:
            raise ValueError(
                f"Insufficient balance: have {balance:.6f} "
                f"{quote_result['token_in']['symbol']}, need {amount_human:.6f}"
            )

        # Step 3: Slippage-adjusted minimum
        slippage_factor = 1 - (slippage_pct / 100)
        amount_out_minimum = int(quote_result["amount_out_raw"] * slippage_factor)
        amount_out_min_human = amount_out_minimum / (10 ** quote_result["token_out"]["decimals"])

        # Step 4: Gas cost estimate
        gas_info = get_gas_price("polygon")
        gas_cost_ether = float(self.w3.from_wei(gas_info["wei"], "ether")) * quote_result["gas_estimate_units"]
        gas_cost_usd = gas_cost_ether * gas_info["native_usd"] if gas_info["native_usd"] else None

        # Step 5: Approve
        approval = check_and_approve(
            token_address=quote_result["token_in"]["address"],
            owner_address=sender,
            amount_raw=quote_result["amount_in_raw"],
            w3=self.w3,
        )

        # Step 6: Swap
        swap_result = build_and_send_swap(
            token_in=quote_result["token_in"]["address"],
            token_out=quote_result["token_out"]["address"],
            fee=quote_result["pool_fee"],
            amount_in_raw=quote_result["amount_in_raw"],
            amount_out_minimum=amount_out_minimum,
            recipient=sender,
            w3=self.w3,
        )

        return {
            "quote": quote_result,
            "approval": approval,
            "swap": swap_result,
            "amount_out_minimum_human": amount_out_min_human,
            "slippage_pct": slippage_pct,
            "gas_cost_usd": gas_cost_usd,
        }
