import json
from pathlib import Path

ABI_DIR = Path(__file__).parent / "abi"


def load_abi(name):
    path = ABI_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


ERC20_ABI = load_abi("erc20_abi")
UNISWAP_V3_SWAP_ROUTER_ABI = load_abi("uniswap_v3_swap_router")
UNISWAP_V3_FACTORY_ABI = load_abi("uniswap_v3_factory")
UNISWAP_V3_POOL_ABI = load_abi("uniswap_v3_pool")
UNISWAP_V3_QUOTER_V2_ABI = load_abi("uniswap_v3_quoter_v2")
