"""
Quoter V2 integration for Uniswap V3.
Uses eth_call to simulate swap and return expected output.
"""
import time
from web3 import Web3
from config.rpc import get_polygon_w3
from config.uniswap import UNISWAP_V3_QUOTER_V2
from contracts.loader import UNISWAP_V3_QUOTER_V2_ABI


def _rpc_call(fn, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if "rate limit" in str(e).lower() and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def get_quote(token_in, token_out, amount_in_raw, fee, w3=None):
    """
    Get a quote for an exact-input-single swap.

    Parameters
    ----------
    token_in : str       — Input token address
    token_out : str      — Output token address
    amount_in_raw : int  — Amount in raw units (smallest denomination)
    fee : int            — Pool fee tier (100, 500, 3000, 10000)
    w3 : Web3, optional

    Returns
    -------
    dict:
        amount_out_raw     — Expected output in raw units
        sqrt_price_after   — sqrtPriceX96 after the swap
        ticks_crossed      — Number of initialized ticks crossed
        gas_estimate       — Gas units estimate from the quoter
    """
    w3 = w3 or get_polygon_w3()
    quoter = w3.eth.contract(
        address=Web3.to_checksum_address(UNISWAP_V3_QUOTER_V2),
        abi=UNISWAP_V3_QUOTER_V2_ABI,
    )

    params = (
        Web3.to_checksum_address(token_in),
        Web3.to_checksum_address(token_out),
        amount_in_raw,
        fee,
        0,  # sqrtPriceLimitX96 = 0 means no limit
    )

    result = _rpc_call(
        lambda: quoter.functions.quoteExactInputSingle(params).call()
    )

    return {
        "amount_out_raw": result[0],
        "sqrt_price_after": result[1],
        "ticks_crossed": result[2],
        "gas_estimate": result[3],
    }
