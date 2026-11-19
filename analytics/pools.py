import time
from web3 import Web3
from config.rpc import get_polygon_w3
from config.uniswap import UNISWAP_V3_FACTORY
from config.tokens import POLYGON
from contracts.loader import (
    ERC20_ABI,
    UNISWAP_V3_FACTORY_ABI,
    UNISWAP_V3_POOL_ABI,
)

COMMON_FEES = [100, 500, 3000, 10000]


def _rpc_call(fn, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if "rate limit" in str(e).lower() and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


class PoolAnalyzer:
    def __init__(self, w3=None):
        self.w3 = w3 or get_polygon_w3()
        self.factory = self.w3.eth.contract(
            address=Web3.to_checksum_address(UNISWAP_V3_FACTORY),
            abi=UNISWAP_V3_FACTORY_ABI,
        )

    def find_pool(self, token_a, token_b, fee=3000):
        token_a = Web3.to_checksum_address(token_a)
        token_b = Web3.to_checksum_address(token_b)
        pool_address = _rpc_call(
            lambda: self.factory.functions.getPool(token_a, token_b, fee).call()
        )
        if pool_address == "0x0000000000000000000000000000000000000000":
            return None
        return pool_address

    def find_best_pool(self, token_a, token_b):
        best = None
        for fee in COMMON_FEES:
            pool_addr = self.find_pool(token_a, token_b, fee)
            if pool_addr:
                pool = self.w3.eth.contract(
                    address=Web3.to_checksum_address(pool_addr),
                    abi=UNISWAP_V3_POOL_ABI,
                )
                liquidity = _rpc_call(lambda: pool.functions.liquidity().call())
                if best is None or liquidity > best["liquidity"]:
                    best = {
                        "address": pool_addr,
                        "fee": fee,
                        "fee_pct": f"{fee / 10000:.2f}%",
                        "liquidity": liquidity,
                    }
        return best

    def get_pool_state(self, pool_address):
        pool = self.w3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=UNISWAP_V3_POOL_ABI,
        )
        slot0 = _rpc_call(lambda: pool.functions.slot0().call())
        token0 = _rpc_call(lambda: pool.functions.token0().call())
        token1 = _rpc_call(lambda: pool.functions.token1().call())
        fee = _rpc_call(lambda: pool.functions.fee().call())
        liquidity = _rpc_call(lambda: pool.functions.liquidity().call())
        sqrt_price_x96 = slot0[0]
        tick = slot0[1]

        price = (sqrt_price_x96 / (2 ** 96)) ** 2

        return {
            "pool_address": pool_address,
            "token0": token0,
            "token1": token1,
            "fee": fee,
            "fee_pct": f"{fee / 10000:.2f}%",
            "liquidity": liquidity,
            "sqrt_price_x96": sqrt_price_x96,
            "tick": tick,
            "price_token1_per_token0": price,
            "price_token0_per_token1": 1 / price if price > 0 else 0,
        }

    def get_pool_price_adjusted(self, pool_address, token0_decimals, token1_decimals):
        state = self.get_pool_state(pool_address)
        decimal_adjustment = 10 ** (token0_decimals - token1_decimals)
        raw_price = state["price_token1_per_token0"]
        return raw_price * decimal_adjustment

    def scan_pairs(self, base_token=None):
        if base_token is None:
            base_token = POLYGON["WMATIC"]

        results = []
        for symbol, addr in POLYGON.items():
            if addr.lower() == base_token.lower():
                continue
            pool = self.find_best_pool(base_token, addr)
            if pool:
                pool["pair"] = f"WMATIC/{symbol}"
                results.append(pool)
        return results

    def get_recent_swaps(self, pool_address, from_block, to_block=None):
        pool = self.w3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=UNISWAP_V3_POOL_ABI,
        )
        if to_block is None:
            to_block = self.w3.eth.block_number

        swap_filter = pool.events.Swap.create_filter(
            from_block=from_block,
            to_block=to_block,
        )
        events = swap_filter.get_all_entries()

        return [
            {
                "sender": e.args["sender"],
                "recipient": e.args["recipient"],
                "amount0": e.args["amount0"],
                "amount1": e.args["amount1"],
                "sqrt_price_x96": e.args["sqrtPriceX96"],
                "liquidity": e.args["liquidity"],
                "tick": e.args["tick"],
                "block": e.blockNumber,
                "tx_hash": e.transactionHash.hex(),
            }
            for e in events
        ]
