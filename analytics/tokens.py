from web3 import Web3
from config.rpc import get_polygon_w3
from contracts.loader import ERC20_ABI


class TokenAnalyzer:
    def __init__(self, w3=None):
        self.w3 = w3 or get_polygon_w3()

    def get_contract(self, token_address):
        token_address = Web3.to_checksum_address(token_address)
        return self.w3.eth.contract(address=token_address, abi=ERC20_ABI)

    def get_info(self, token_address):
        contract = self.get_contract(token_address)
        return {
            "address": token_address,
            "name": contract.functions.name().call(),
            "symbol": contract.functions.symbol().call(),
            "decimals": contract.functions.decimals().call(),
            "total_supply": contract.functions.totalSupply().call(),
        }

    def get_balance_of(self, token_address, holder_address):
        contract = self.get_contract(token_address)
        decimals = contract.functions.decimals().call()
        raw = contract.functions.balanceOf(
            Web3.to_checksum_address(holder_address)
        ).call()
        return raw / (10 ** decimals)

    def get_allowance(self, token_address, owner, spender):
        contract = self.get_contract(token_address)
        decimals = contract.functions.decimals().call()
        raw = contract.functions.allowance(
            Web3.to_checksum_address(owner),
            Web3.to_checksum_address(spender),
        ).call()
        return raw / (10 ** decimals)

    def get_transfer_events(self, token_address, from_block, to_block=None):
        contract = self.get_contract(token_address)
        if to_block is None:
            to_block = self.w3.eth.block_number

        transfer_filter = contract.events.Transfer.create_filter(
            from_block=from_block,
            to_block=to_block,
        )
        events = transfer_filter.get_all_entries()
        decimals = contract.functions.decimals().call()

        return [
            {
                "from": e.args["from"],
                "to": e.args["to"],
                "value": e.args["value"] / (10 ** decimals),
                "block": e.blockNumber,
                "tx_hash": e.transactionHash.hex(),
            }
            for e in events
        ]

    def top_holders_from_transfers(self, token_address, from_block, to_block=None):
        transfers = self.get_transfer_events(token_address, from_block, to_block)
        balances = {}
        for t in transfers:
            balances[t["from"]] = balances.get(t["from"], 0) - t["value"]
            balances[t["to"]] = balances.get(t["to"], 0) + t["value"]

        sorted_holders = sorted(balances.items(), key=lambda x: x[1], reverse=True)
        return [
            {"address": addr, "net_flow": flow}
            for addr, flow in sorted_holders
            if flow > 0
        ]
