"""
ERC-20 approval logic for SwapRouter02.
Checks existing allowance, approves if insufficient.
"""
import os
from web3 import Web3
from config.rpc import get_polygon_w3
from config.uniswap import UNISWAP_V3_SWAP_ROUTER_02
from contracts.loader import ERC20_ABI


def check_and_approve(token_address, owner_address, amount_raw, w3=None):
    """
    Ensure SwapRouter02 has sufficient allowance.

    If allowance >= amount_raw, returns immediately.
    Otherwise sends an approve tx for the exact amount and waits for receipt.

    Returns
    -------
    dict:
        status            — "already_approved" or "approved"
        allowance_before  — Raw allowance before
        allowance_after   — Raw allowance after
        tx_hash           — Approval tx hash (None if already approved)
        gas_used          — Gas consumed (None if already approved)
    """
    w3 = w3 or get_polygon_w3()
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI,
    )
    router = Web3.to_checksum_address(UNISWAP_V3_SWAP_ROUTER_02)
    owner = Web3.to_checksum_address(owner_address)

    current_allowance = token.functions.allowance(owner, router).call()

    if current_allowance >= amount_raw:
        return {
            "status": "already_approved",
            "allowance_before": current_allowance,
            "allowance_after": current_allowance,
            "tx_hash": None,
            "gas_used": None,
        }

    pk = os.environ.get("WALLET_PK")
    if not pk:
        raise EnvironmentError(
            "WALLET_PK not set. Run with: op run --env-file=.env -- python cli.py ..."
        )

    nonce = w3.eth.get_transaction_count(owner)
    approve_tx = token.functions.approve(router, amount_raw).build_transaction({
        "from": owner,
        "nonce": nonce,
        "gas": 60_000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(30, "gwei"),
    })

    signed = w3.eth.account.sign_transaction(approve_tx, private_key=pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    new_allowance = token.functions.allowance(owner, router).call()

    return {
        "status": "approved",
        "allowance_before": current_allowance,
        "allowance_after": new_allowance,
        "tx_hash": tx_hash.hex(),
        "gas_used": receipt["gasUsed"],
    }
