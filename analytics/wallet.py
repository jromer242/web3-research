from web3 import Web3
from config.rpc import get_polygon_w3, get_ethereum_w3, get_base_w3
from config.tokens import POLYGON, ETHEREUM, BASE
from contracts.loader import ERC20_ABI

CHAINS = {
    "polygon": {
        "get_w3": get_polygon_w3,
        "tokens": POLYGON,
        "native": "MATIC",
        "native_skip": ("MATIC",),
    },
    "ethereum": {
        "get_w3": get_ethereum_w3,
        "tokens": ETHEREUM,
        "native": "ETH",
        "native_skip": (),
    },
    "base": {
        "get_w3": get_base_w3,
        "tokens": BASE,
        "native": "ETH",
        "native_skip": (),
    },
}


class WalletAnalyzer:
    def __init__(self, chain="polygon", w3=None):
        if chain not in CHAINS:
            raise ValueError(f"Unknown chain: {chain}. Available: {', '.join(CHAINS)}")
        self.chain = chain
        self.chain_config = CHAINS[chain]
        self.w3 = w3 or self.chain_config["get_w3"]()

    def get_native_balance(self, address):
        balance_wei = self.w3.eth.get_balance(Web3.to_checksum_address(address))
        return self.w3.from_wei(balance_wei, "ether")

    def get_token_balance(self, address, token_address):
        address = Web3.to_checksum_address(address)
        token_address = Web3.to_checksum_address(token_address)
        contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = contract.functions.decimals().call()
        raw_balance = contract.functions.balanceOf(address).call()
        return raw_balance / (10 ** decimals)

    def get_all_balances(self, address):
        native = self.chain_config["native"]
        balances = {native: float(self.get_native_balance(address))}
        for symbol, token_addr in self.chain_config["tokens"].items():
            if symbol in self.chain_config["native_skip"]:
                continue
            try:
                bal = self.get_token_balance(address, token_addr)
                if bal > 0:
                    balances[symbol] = bal
            except Exception:
                pass
        return balances

    def get_tx_count(self, address):
        return self.w3.eth.get_transaction_count(Web3.to_checksum_address(address))

    def get_recent_transactions(self, address, last_n_blocks=1000):
        address = Web3.to_checksum_address(address)
        latest = self.w3.eth.block_number
        start_block = max(0, latest - last_n_blocks)

        txs = []
        for block_num in range(start_block, latest + 1):
            block = self.w3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                if tx["from"] == address or tx.get("to") == address:
                    txs.append({
                        "hash": tx["hash"].hex(),
                        "block": tx["blockNumber"],
                        "from": tx["from"],
                        "to": tx.get("to"),
                        "value": self.w3.from_wei(tx["value"], "ether"),
                        "gas_price_gwei": self.w3.from_wei(tx["gasPrice"], "gwei"),
                    })
        return txs

    def profile(self, address):
        return {
            "address": address,
            "chain": self.chain,
            "tx_count": self.get_tx_count(address),
            "balances": self.get_all_balances(address),
        }
