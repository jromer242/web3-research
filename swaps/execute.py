"""
Transaction building, signing, and sending for Uniswap V3 swaps.
Uses SwapRouter02's multicall(deadline, data[]) pattern.
"""
import os
import time
from web3 import Web3
from config.rpc import get_polygon_w3
from config.uniswap import UNISWAP_V3_SWAP_ROUTER_02
from contracts.loader import UNISWAP_V3_SWAP_ROUTER_ABI


def build_and_send_swap(
    token_in,
    token_out,
    fee,
    amount_in_raw,
    amount_out_minimum,
    recipient,
    deadline_seconds=300,
    w3=None,
):
    """
    Build, sign, and send an exactInputSingle swap via multicall.

    Parameters
    ----------
    token_in : str           — Input token address
    token_out : str          — Output token address
    fee : int                — Pool fee tier
    amount_in_raw : int      — Exact input in raw units
    amount_out_minimum : int — Min acceptable output (slippage protection)
    recipient : str          — Address to receive output
    deadline_seconds : int   — Seconds until tx expires (default 300)
    w3 : Web3, optional

    Returns
    -------
    dict:
        tx_hash             — Transaction hash
        status              — 1 = success, 0 = revert
        block_number        — Block mined in
        gas_used            — Gas consumed
        effective_gas_price — Actual gas price paid
    """
    w3 = w3 or get_polygon_w3()
    router = w3.eth.contract(
        address=Web3.to_checksum_address(UNISWAP_V3_SWAP_ROUTER_02),
        abi=UNISWAP_V3_SWAP_ROUTER_ABI,
    )

    pk = os.environ.get("WALLET_PK")
    if not pk:
        raise EnvironmentError(
            "WALLET_PK not set. Run with: op run --env-file=.env -- python cli.py ..."
        )

    sender = Web3.to_checksum_address(recipient)

    # Encode the inner exactInputSingle call
    swap_params = (
        Web3.to_checksum_address(token_in),
        Web3.to_checksum_address(token_out),
        fee,
        Web3.to_checksum_address(recipient),
        amount_in_raw,
        amount_out_minimum,
        0,  # sqrtPriceLimitX96 = 0 (no limit, slippage handled by amountOutMinimum)
    )
    swap_calldata = router.encode_abi("exactInputSingle", args=[swap_params])

    # Wrap in multicall with deadline
    deadline = int(time.time()) + deadline_seconds
    multicall_tx = router.functions.multicall(
        deadline, [swap_calldata]
    ).build_transaction({
        "from": sender,
        "value": 0,
        "nonce": w3.eth.get_transaction_count(sender),
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(30, "gwei"),
    })

    # Estimate gas with buffer
    try:
        gas_estimate = w3.eth.estimate_gas(multicall_tx)
        multicall_tx["gas"] = int(gas_estimate * 1.2)
    except Exception:
        multicall_tx["gas"] = 250_000

    signed = w3.eth.account.sign_transaction(multicall_tx, private_key=pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    return {
        "tx_hash": tx_hash.hex(),
        "status": receipt["status"],
        "block_number": receipt["blockNumber"],
        "gas_used": receipt["gasUsed"],
        "effective_gas_price": receipt["effectiveGasPrice"],
    }
