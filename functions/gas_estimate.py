from web3 import Web3
from config.rpc import get_polygon_w3, get_ethereum_w3
from config.tokens import POLYGON
from config.uniswap import UNISWAP_V3_FACTORY
from contracts.loader import UNISWAP_V3_FACTORY_ABI, UNISWAP_V3_POOL_ABI


def _get_usd_price(w3, token_address, usdc_address, factory_address):
    factory = w3.eth.contract(
        address=Web3.to_checksum_address(factory_address),
        abi=UNISWAP_V3_FACTORY_ABI,
    )
    pool_addr = factory.functions.getPool(
        Web3.to_checksum_address(token_address),
        Web3.to_checksum_address(usdc_address),
        500,
    ).call()
    if pool_addr == "0x0000000000000000000000000000000000000000":
        return None

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(pool_addr), abi=UNISWAP_V3_POOL_ABI
    )
    slot0 = pool.functions.slot0().call()
    token0 = pool.functions.token0().call()
    sqrt_price_x96 = slot0[0]
    raw_price = (sqrt_price_x96 / (2**96)) ** 2

    # USDC has 6 decimals, native tokens have 18
    decimal_adj = 10 ** (18 - 6)
    price = raw_price * decimal_adj

    # If USDC is token0, price is inverted (token1 per token0 = native per USDC)
    if token0.lower() == usdc_address.lower():
        return 1 / price if price > 0 else None
    return price


def get_native_usd_price(chain="polygon"):
    w3 = get_polygon_w3()
    if chain == "polygon":
        return _get_usd_price(w3, POLYGON["WMATIC"], POLYGON["USDC"], UNISWAP_V3_FACTORY)
    elif chain == "ethereum":
        return _get_usd_price(w3, POLYGON["WETH"], POLYGON["USDC"], UNISWAP_V3_FACTORY)
    return None


def get_gas_price(chain="polygon"):
    if chain == "polygon":
        w3 = get_polygon_w3()
    elif chain == "ethereum":
        w3 = get_ethereum_w3()
    else:
        raise ValueError(f"Unsupported chain: {chain}")

    gas_price = w3.eth.gas_price
    gas_ether = float(w3.from_wei(gas_price, "ether"))

    usd_price = get_native_usd_price(chain)
    gas_usd = gas_ether * usd_price * 21000 if usd_price else None

    return {
        "wei": gas_price,
        "gwei": w3.from_wei(gas_price, "gwei"),
        "ether": gas_ether,
        "native_usd": usd_price,
        "transfer_cost_usd": gas_usd,
    }


if __name__ == "__main__":
    for chain in ["polygon", "ethereum"]:
        price = get_gas_price(chain)
        usd = f"${price['transfer_cost_usd']:.6f}" if price["transfer_cost_usd"] else "N/A"
        print(f"{chain}: {price['gwei']:.2f} gwei | simple transfer: {usd}")
