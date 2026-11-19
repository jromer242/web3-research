import os
from web3 import Web3

# Free public RPCs (fallback)
PUBLIC_POLYGON_RPC = "https://polygon.drpc.org"
PUBLIC_ETHEREUM_RPC = "https://eth.llamarpc.com"
PUBLIC_SEPOLIA_RPC = "https://rpc.sepolia.org"
PUBLIC_BASE_RPC = "https://base.drpc.org"


def _get_polygon_rpc():
    url = os.environ.get("INFURA_POLY_URL")
    key = os.environ.get("INFURA_KEY")
    if url and key:
        return f"{url}{key}"
    return PUBLIC_POLYGON_RPC


def _get_ethereum_rpc():
    url = os.environ.get("INFURA_ETH_URL")
    key = os.environ.get("INFURA_KEY")
    if url and key:
        return f"{url}{key}"
    return PUBLIC_ETHEREUM_RPC

def _get_base_rpc():
    url = os.environ.get("INFURA_BASE_URL")
    key = os.environ.get("INFURA_KEY")
    if url and key:
        return f"{url}{key}"
    return PUBLIC_BASE_RPC

def get_polygon_w3():
    return Web3(Web3.HTTPProvider(_get_polygon_rpc()))

def get_ethereum_w3():
    return Web3(Web3.HTTPProvider(_get_ethereum_rpc()))

def get_base_w3():
    return Web3(Web3.HTTPProvider(_get_base_rpc()))


def get_sepolia_w3():
    return Web3(Web3.HTTPProvider(PUBLIC_SEPOLIA_RPC))
