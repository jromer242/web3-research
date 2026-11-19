import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.wallets import MY_ADDRESS
from config.tokens import POLYGON, ETHEREUM, BASE

app = typer.Typer(help="On-chain analytics CLI — Polygon focused")
console = Console()


@app.command()
def wallet(
    address: str = typer.Argument(default=MY_ADDRESS, help="Wallet address to profile"),
    chain: str = typer.Option("polygon", help="Chain to query (polygon, ethereum, base)"),
):
    """Show wallet balances, tx count, and summary."""
    from analytics.wallet import WalletAnalyzer

    console.print(f"\n[bold]Profiling[/bold] {address} on [cyan]{chain}[/cyan]\n")

    with console.status(f"Fetching wallet data from {chain}..."):
        wa = WalletAnalyzer(chain=chain)
        profile = wa.profile(address)

    table = Table(title=f"Balances ({chain.title()})")
    table.add_column("Token", style="cyan")
    table.add_column("Balance", justify="right", style="green")

    for token, balance in profile["balances"].items():
        table.add_row(token, f"{balance:,.6f}")

    console.print(table)
    console.print(f"\nTransactions: [bold]{profile['tx_count']}[/bold]")


@app.command()
def token(address: str = typer.Argument(help="Token contract address")):
    """Get info about an ERC-20 token."""
    from analytics.tokens import TokenAnalyzer

    with console.status("Fetching token info..."):
        ta = TokenAnalyzer()
        info = ta.get_info(address)

    table = Table(title=f"{info['name']} ({info['symbol']})")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    decimals = info["decimals"]
    supply = info["total_supply"] / (10 ** decimals)

    table.add_row("Address", info["address"])
    table.add_row("Decimals", str(decimals))
    table.add_row("Total Supply", f"{supply:,.2f}")

    console.print(table)


@app.command()
def pool(
    token_a: str = typer.Argument(help="Token A symbol (e.g. WMATIC) or address"),
    token_b: str = typer.Argument(help="Token B symbol (e.g. USDC) or address"),
):
    """Find and inspect the best Uniswap V3 pool for a pair."""
    from analytics.pools import PoolAnalyzer
    from analytics.tokens import TokenAnalyzer

    addr_a = POLYGON.get(token_a.upper(), token_a)
    addr_b = POLYGON.get(token_b.upper(), token_b)

    with console.status(f"Finding best pool for {token_a}/{token_b}..."):
        pa = PoolAnalyzer()
        best = pa.find_best_pool(addr_a, addr_b)

    if not best:
        console.print(f"[red]No pool found for {token_a}/{token_b}[/red]")
        raise typer.Exit(1)

    with console.status("Reading pool state..."):
        state = pa.get_pool_state(best["address"])
        ta = TokenAnalyzer()
        info0 = ta.get_info(state["token0"])
        info1 = ta.get_info(state["token1"])
        price = pa.get_pool_price_adjusted(
            best["address"], info0["decimals"], info1["decimals"]
        )

    table = Table(title=f"Pool: {info0['symbol']}/{info1['symbol']}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Pool Address", best["address"])
    table.add_row("Fee Tier", best["fee_pct"])
    table.add_row("Liquidity", f"{best['liquidity']:,}")
    table.add_row("Tick", str(state["tick"]))
    table.add_row(
        f"Price ({info1['symbol']} per {info0['symbol']})",
        f"{price:.6f}",
    )
    table.add_row(
        f"Price ({info0['symbol']} per {info1['symbol']})",
        f"{1/price:.6f}" if price > 0 else "N/A",
    )

    console.print(table)


@app.command()
def gas():
    """Show current gas prices on Polygon and Ethereum."""
    from functions.gas_estimate import get_gas_price

    table = Table(title="Gas Prices")
    table.add_column("Chain", style="cyan")
    table.add_column("Gwei", justify="right", style="green")
    table.add_column("ETH/MATIC", justify="right", style="dim")
    table.add_column("USD Value", justify="right", style="dim") # Start here to produce the usd amount 

    for chain in ["polygon", "ethereum"]:
        with console.status(f"Fetching {chain} gas..."):
            try:
                price = get_gas_price(chain)
                usd = f"${price['transfer_cost_usd']:.6f}" if price["transfer_cost_usd"] else "N/A"
                table.add_row(
                    chain.title(),
                    f"{price['gwei']:.2f}",
                    f"{price['ether']:.10f}",
                    usd,
                )
            except Exception as e:
                table.add_row(chain.title(), f"[red]Error: {e}[/red]", "", "")

    console.print(table)


@app.command()
def scan():
    """Scan all WMATIC trading pairs on Uniswap V3 Polygon."""
    from analytics.pools import PoolAnalyzer

    with console.status("Scanning WMATIC pairs across fee tiers..."):
        pa = PoolAnalyzer()
        pairs = pa.scan_pairs()

    table = Table(title="WMATIC Pairs on Uniswap V3 (Polygon)")
    table.add_column("Pair", style="cyan")
    table.add_column("Fee", justify="right", style="yellow")
    table.add_column("Liquidity", justify="right", style="green")
    table.add_column("Pool", style="dim")

    for p in sorted(pairs, key=lambda x: x["liquidity"], reverse=True):
        table.add_row(
            p["pair"],
            p["fee_pct"],
            f"{p['liquidity']:,}",
            p["address"][:16] + "...",
        )

    console.print(table)


@app.command()
def transfers(
    token_address: str = typer.Argument(help="Token contract address"),
    blocks: int = typer.Option(100, help="Number of recent blocks to scan"),
):
    """Show recent transfer events for a token."""
    from analytics.tokens import TokenAnalyzer

    ta = TokenAnalyzer()

    with console.status("Fetching transfer events..."):
        latest = ta.w3.eth.block_number
        events = ta.get_transfer_events(token_address, latest - blocks)
        info = ta.get_info(token_address)

    console.print(
        f"\n[bold]{info['symbol']}[/bold] transfers in last {blocks} blocks "
        f"({len(events)} found)\n"
    )

    table = Table()
    table.add_column("Block", style="dim")
    table.add_column("From", style="red", max_width=16)
    table.add_column("To", style="green", max_width=16)
    table.add_column("Amount", justify="right", style="cyan")
    table.add_column("Tx", style="dim", max_width=16)

    for e in events[:25]:
        table.add_row(
            str(e["block"]),
            e["from"][:16] + "...",
            e["to"][:16] + "...",
            f"{e['value']:,.4f}",
            e["tx_hash"][:16] + "...",
        )

    if len(events) > 25:
        console.print(f"[dim]Showing 25 of {len(events)} transfers[/dim]")

    console.print(table)


@app.command()
def quote(
    token_in: str = typer.Argument(help="Input token symbol (e.g. USDC) or address"),
    token_out: str = typer.Argument(help="Output token symbol (e.g. WMATIC) or address"),
    amount: float = typer.Argument(help="Amount of input token to swap"),
):
    """Get a swap quote from Uniswap V3 without executing."""
    from swaps.pipeline import SwapPipeline

    with console.status(f"Getting quote for {amount} {token_in} → {token_out}..."):
        pipeline = SwapPipeline()
        q = pipeline.get_swap_quote(token_in, token_out, amount)

    table = Table(title=f"Swap Quote: {q['token_in']['symbol']} → {q['token_out']['symbol']}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Input", f"{q['amount_in_human']:,.6f} {q['token_in']['symbol']}")
    table.add_row("Expected Output", f"{q['amount_out_human']:,.6f} {q['token_out']['symbol']}")
    table.add_row("Rate", f"1 {q['token_in']['symbol']} = {q['price']:,.6f} {q['token_out']['symbol']}")
    table.add_row("Pool Fee", q["pool_fee_pct"])
    table.add_row("Pool Address", q["pool_address"])
    table.add_row("Pool Liquidity", f"{q['pool_liquidity']:,}")
    table.add_row("Gas Estimate", f"{q['gas_estimate_units']:,} units")

    console.print(table)


@app.command()
def swap(
    token_in: str = typer.Argument(help="Input token symbol (e.g. USDC) or address"),
    token_out: str = typer.Argument(help="Output token symbol (e.g. WMATIC) or address"),
    amount: float = typer.Argument(help="Amount of input token to swap"),
    slippage: float = typer.Option(0.5, help="Slippage tolerance in percent"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Execute a token swap on Uniswap V3 (Polygon)."""
    from swaps.pipeline import SwapPipeline
    from functions.gas_estimate import get_gas_price

    # Step 1: Quote
    with console.status(f"Getting quote for {amount} {token_in} → {token_out}..."):
        pipeline = SwapPipeline()
        q = pipeline.get_swap_quote(token_in, token_out, amount)

    # Step 2: Slippage calc
    slippage_factor = 1 - (slippage / 100)
    min_out = q["amount_out_human"] * slippage_factor

    # Step 3: Gas cost
    with console.status("Estimating gas cost..."):
        gas_info = get_gas_price("polygon")
        gas_cost_ether = float(pipeline.w3.from_wei(gas_info["wei"], "ether")) * q["gas_estimate_units"]
        gas_cost_usd = gas_cost_ether * gas_info["native_usd"] if gas_info["native_usd"] else None

    # Step 4: Preview
    table = Table(title="Swap Preview")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Swap", f"{q['amount_in_human']:,.6f} {q['token_in']['symbol']} → {q['token_out']['symbol']}")
    table.add_row("Expected Output", f"{q['amount_out_human']:,.6f} {q['token_out']['symbol']}")
    table.add_row("Minimum Output", f"{min_out:,.6f} {q['token_out']['symbol']} ({slippage}% slippage)")
    table.add_row("Rate", f"1 {q['token_in']['symbol']} = {q['price']:,.6f} {q['token_out']['symbol']}")
    table.add_row("Pool Fee", q["pool_fee_pct"])
    gas_usd_str = f"${gas_cost_usd:.4f}" if gas_cost_usd else "N/A"
    table.add_row("Est. Gas Cost", gas_usd_str)

    console.print(table)

    # Step 5: Confirm
    if not yes:
        confirmed = typer.confirm("\nProceed with swap?")
        if not confirmed:
            console.print("[yellow]Swap cancelled.[/yellow]")
            raise typer.Exit()

    # Step 6: Approve
    with console.status("Checking allowance and approving if needed..."):
        from swaps.approve import check_and_approve
        approval = check_and_approve(
            token_address=q["token_in"]["address"],
            owner_address=MY_ADDRESS,
            amount_raw=q["amount_in_raw"],
            w3=pipeline.w3,
        )

    if approval["status"] == "approved":
        console.print(f"[green]Approved {q['token_in']['symbol']} for SwapRouter02[/green] (tx: {approval['tx_hash'][:16]}...)")
    else:
        console.print("[dim]Allowance already sufficient[/dim]")

    # Step 7: Swap
    with console.status("Sending swap transaction..."):
        from swaps.execute import build_and_send_swap
        amount_out_minimum = int(q["amount_out_raw"] * slippage_factor)
        result = build_and_send_swap(
            token_in=q["token_in"]["address"],
            token_out=q["token_out"]["address"],
            fee=q["pool_fee"],
            amount_in_raw=q["amount_in_raw"],
            amount_out_minimum=amount_out_minimum,
            recipient=MY_ADDRESS,
            w3=pipeline.w3,
        )

    # Step 8: Receipt
    if result["status"] == 1:
        console.print(Panel(
            f"[bold green]Swap successful![/bold green]\n\n"
            f"Tx Hash: {result['tx_hash']}\n"
            f"Block: {result['block_number']}\n"
            f"Gas Used: {result['gas_used']:,}\n"
            f"PolygonScan: https://polygonscan.com/tx/{result['tx_hash']}",
            title="Receipt",
        ))
    else:
        console.print(Panel(
            f"[bold red]Swap REVERTED[/bold red]\n\n"
            f"Tx Hash: {result['tx_hash']}\n"
            f"Check: https://polygonscan.com/tx/{result['tx_hash']}",
            title="Receipt",
            style="red",
        ))


# ── Dune Analytics ───────────────────────────────────────────────────

dune_app = typer.Typer(help="Dune Analytics — SQL-based on-chain research")
app.add_typer(dune_app, name="dune")


@dune_app.command("queries")
def dune_queries():
    """List available Dune SQL queries."""
    from analytics.dune import DuneAnalyzer

    table = Table(title="Dune SQL Queries")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")

    for q in DuneAnalyzer.list_queries():
        table.add_row(q["name"], q["description"])

    console.print(table)
    console.print("\n[dim]Use [bold]dune sql <name>[/bold] to view the query[/dim]")


@dune_app.command("sql")
def dune_sql(
    name: str = typer.Argument(help="Query name from 'dune queries'"),
):
    """Print raw SQL for a query — paste into Dune's web editor."""
    from analytics.dune import DuneAnalyzer
    from rich.syntax import Syntax

    try:
        sql = DuneAnalyzer.get_sql(name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(Syntax(sql, "sql", theme="monokai", line_numbers=True))
    console.print(
        "\n[dim]Paste into dune.com/queries — set param types in the editor.\n"
        "Or set DUNE_API_KEY to run directly.[/dim]"
    )


def _run_or_show_sql(query_name: str, query_id: int = None, **params):
    """Try to run via API; if no key or permission denied, print the SQL instead."""
    from analytics.dune import DuneAnalyzer
    import os

    if os.environ.get("DUNE_API_KEY"):
        analyzer = DuneAnalyzer()
        if query_id:
            params["query_id"] = query_id
        try:
            return analyzer.run(query_name, **params)
        except PermissionError as e:
            from rich.syntax import Syntax

            console.print(f"[yellow]{e}[/yellow]\n")
            sql = DuneAnalyzer.get_sql(query_name, **params)
            console.print(Syntax(sql, "sql", theme="monokai", line_numbers=True))
            return None
    else:
        from rich.syntax import Syntax

        sql = DuneAnalyzer.get_sql(query_name, **params)
        console.print("[yellow]No DUNE_API_KEY — showing substituted SQL instead.[/yellow]\n")
        console.print(Syntax(sql, "sql", theme="monokai", line_numbers=True))
        console.print("\n[dim]Set DUNE_API_KEY to execute, or paste into dune.com/queries[/dim]")
        return None


@dune_app.command("wallet")
def dune_wallet(
    address: str = typer.Argument(help="Wallet address"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    days: int = typer.Option(30, help="Lookback in days"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Profile a wallet's DEX trading activity."""
    rows = _run_or_show_sql(
        "wallet_dex_activity", query_id=id,
        wallet_address=address, blockchain=chain, days=days,
    )
    if rows is None:
        return

    table = Table(title=f"DEX Activity: {address[:16]}...")
    table.add_column("Time", style="dim")
    table.add_column("DEX", style="cyan")
    table.add_column("Bought", style="green")
    table.add_column("Sold", style="red")
    table.add_column("USD", justify="right", style="yellow")

    for r in rows[:30]:
        time_str = str(r.get("block_time", ""))[:19]
        bought = f"{r.get('token_bought_amount', 0):,.2f} {r.get('token_bought_symbol', '')}"
        sold = f"{r.get('token_sold_amount', 0):,.2f} {r.get('token_sold_symbol', '')}"
        usd = f"${r.get('amount_usd', 0):,.2f}" if r.get("amount_usd") else "N/A"
        table.add_row(time_str, r.get("dex", ""), bought, sold, usd)

    console.print(table)
    if len(rows) > 30:
        console.print(f"[dim]Showing 30 of {len(rows)} trades[/dim]")


@dune_app.command("whales")
def dune_whales(
    token: str = typer.Argument(help="Token contract address"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    days: int = typer.Option(7, help="Lookback in days"),
    min_usd: float = typer.Option(100000, help="Minimum transfer USD"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Detect whale movements — large token transfers."""
    rows = _run_or_show_sql(
        "token_large_transfers", query_id=id,
        token_address=token, blockchain=chain, days=days, min_usd=int(min_usd),
    )
    if rows is None:
        return

    table = Table(title=f"Whale Transfers (>${min_usd:,.0f} USD)")
    table.add_column("Time", style="dim")
    table.add_column("From", max_width=20)
    table.add_column("To", max_width=20)
    table.add_column("Amount", justify="right", style="cyan")
    table.add_column("USD", justify="right", style="yellow")

    for r in rows[:25]:
        time_str = str(r.get("block_time", ""))[:19]
        sender = r.get("sender_label") or (str(r.get("sender", ""))[:16] + "...")
        receiver = r.get("receiver_label") or (str(r.get("receiver", ""))[:16] + "...")
        amt = f"{r.get('amount', 0):,.2f} {r.get('symbol', '')}"
        usd = f"${r.get('amount_usd', 0):,.0f}" if r.get("amount_usd") else "N/A"
        table.add_row(time_str, sender, receiver, amt, usd)

    console.print(table)


@dune_app.command("flows")
def dune_flows(
    token: str = typer.Argument(help="Token contract address"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    days: int = typer.Option(7, help="Lookback in days"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Track token flows to/from exchanges — net inflow = sell pressure."""
    rows = _run_or_show_sql(
        "exchange_net_flows", query_id=id,
        token_address=token, blockchain=chain, days=days,
    )
    if rows is None:
        return

    table = Table(title="Exchange Net Flows (Hourly)")
    table.add_column("Hour", style="dim")
    table.add_column("Inflow USD", justify="right", style="red")
    table.add_column("Outflow USD", justify="right", style="green")
    table.add_column("Net Flow", justify="right")

    for r in rows[:48]:
        hour = str(r.get("hour", ""))[:16]
        inflow = f"${r.get('inflow_usd', 0):,.0f}"
        outflow = f"${r.get('outflow_usd', 0):,.0f}"
        net = r.get("net_flow_usd", 0)
        net_style = "red" if net > 0 else "green"
        net_str = f"[{net_style}]${abs(net):,.0f} {'IN' if net > 0 else 'OUT'}[/{net_style}]"
        table.add_row(hour, inflow, outflow, net_str)

    console.print(table)


@dune_app.command("holders")
def dune_holders(
    token: str = typer.Argument(help="Token contract address"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    decimals: int = typer.Option(18, help="Token decimals"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Analyze token holder concentration — top wallets by balance."""
    rows = _run_or_show_sql(
        "token_holder_concentration", query_id=id,
        token_address=token, blockchain=chain, decimals=decimals,
    )
    if rows is None:
        return

    table = Table(title="Top Token Holders")
    table.add_column("#", style="dim")
    table.add_column("Address / Label", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Balance", justify="right", style="green")
    table.add_column("% Supply", justify="right", style="yellow")

    for i, r in enumerate(rows[:25], 1):
        label = r.get("label") or (str(r.get("address", ""))[:16] + "...")
        cat = r.get("category") or ""
        balance = f"{r.get('balance', 0):,.2f}"
        pct = f"{r.get('pct_supply', 0):.2f}%"
        table.add_row(str(i), label, cat, balance, pct)

    console.print(table)


@dune_app.command("volume")
def dune_volume(
    token_a: str = typer.Argument(help="Token A symbol (e.g. WETH)"),
    token_b: str = typer.Argument(help="Token B symbol (e.g. USDC)"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    days: int = typer.Option(30, help="Lookback in days"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Compare DEX volume by protocol for a trading pair."""
    rows = _run_or_show_sql(
        "dex_pair_volume", query_id=id,
        token_a=token_a.upper(), token_b=token_b.upper(),
        blockchain=chain, days=days,
    )
    if rows is None:
        return

    table = Table(title=f"DEX Volume: {token_a.upper()}/{token_b.upper()}")
    table.add_column("Date", style="dim")
    table.add_column("DEX", style="cyan")
    table.add_column("Trades", justify="right")
    table.add_column("Volume USD", justify="right", style="green")
    table.add_column("Avg Trade", justify="right", style="dim")

    for r in rows[:40]:
        date_str = str(r.get("block_date", ""))[:10]
        trades = f"{r.get('num_trades', 0):,}"
        vol = f"${r.get('volume_usd', 0):,.0f}"
        avg = f"${r.get('avg_trade_usd', 0):,.0f}"
        table.add_row(date_str, r.get("dex", ""), trades, vol, avg)

    console.print(table)


@dune_app.command("accumulation")
def dune_accumulation(
    token: str = typer.Argument(help="Token contract address"),
    chain: str = typer.Option("ethereum", help="Blockchain"),
    days: int = typer.Option(14, help="Lookback in days"),
    min_usd: float = typer.Option(10000, help="Min total USD bought"),
    id: int = typer.Option(None, "--id", help="Saved Dune query ID"),
):
    """Find wallets accumulating a token via DEX buys — smart money detection."""
    rows = _run_or_show_sql(
        "smart_money_accumulation", query_id=id,
        token_address=token, blockchain=chain, days=days, min_usd=int(min_usd),
    )
    if rows is None:
        return

    table = Table(title=f"Token Accumulation (>${min_usd:,.0f} USD)")
    table.add_column("Wallet / Label", style="cyan", max_width=24)
    table.add_column("Category", style="dim")
    table.add_column("Total Bought", justify="right", style="green")
    table.add_column("Total USD", justify="right", style="yellow")
    table.add_column("Trades", justify="right")
    table.add_column("Avg Trade", justify="right", style="dim")

    for r in rows[:25]:
        label = r.get("label") or (str(r.get("wallet", ""))[:16] + "...")
        cat = r.get("category") or ""
        bought = f"{r.get('total_bought', 0):,.2f}"
        usd = f"${r.get('total_usd', 0):,.0f}"
        trades = str(r.get("num_trades", 0))
        avg = f"${r.get('avg_trade_usd', 0):,.0f}"
        table.add_row(label, cat, bought, usd, trades, avg)

    console.print(table)


# ── DefiLlama — Free On-Chain Analytics ─────────────────────────────

defi_app = typer.Typer(help="DefiLlama — free on-chain data (no API key)")
app.add_typer(defi_app, name="defi")


@defi_app.command("overview")
def defi_overview():
    """Market snapshot — top chains, DEXes, stablecoins, yields."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()

    with console.status("Fetching market overview..."):
        data = dl.market_overview()

    # Chains
    table = Table(title="Top Chains by TVL")
    table.add_column("Chain", style="cyan")
    table.add_column("TVL", justify="right", style="green")
    for c in data["top_chains"]:
        table.add_row(c["name"], f"${c['tvl']:,.0f}")
    console.print(table)

    # DEXes
    console.print()
    table = Table(title="Top DEXes by 24h Volume")
    table.add_column("DEX", style="cyan")
    table.add_column("24h Volume", justify="right", style="green")
    table.add_column("7d Volume", justify="right", style="dim")
    table.add_column("24h Change", justify="right")
    for d in data["top_dexes"]:
        vol24 = f"${d['volume_24h']:,.0f}" if d.get("volume_24h") else "N/A"
        vol7d = f"${d['volume_7d']:,.0f}" if d.get("volume_7d") else "N/A"
        chg = d.get("change_1d")
        chg_str = f"[{'green' if chg and chg > 0 else 'red'}]{chg:+.1f}%[/]" if chg else "N/A"
        table.add_row(d["name"], vol24, vol7d, chg_str)
    console.print(table)

    # Stablecoins
    console.print()
    table = Table(title="Top Stablecoins by Market Cap")
    table.add_column("Stablecoin", style="cyan")
    table.add_column("Circulating", justify="right", style="green")
    table.add_column("Peg", style="dim")
    for s in data["top_stablecoins"]:
        circ = f"${s['circulating']:,.0f}" if s.get("circulating") else "N/A"
        table.add_row(f"{s['name']} ({s.get('symbol', '')})", circ, s.get("peg_mechanism", ""))
    console.print(table)

    # Yields
    console.print()
    table = Table(title="Top Yield Opportunities (TVL > $1M)")
    table.add_column("Pool", style="cyan")
    table.add_column("Chain", style="dim")
    table.add_column("Protocol", style="dim")
    table.add_column("APY", justify="right", style="green")
    table.add_column("TVL", justify="right", style="yellow")
    for y in data["top_yields"]:
        apy = f"{y['apy']:.2f}%" if y.get("apy") else "N/A"
        tvl = f"${y['tvl']:,.0f}" if y.get("tvl") else "N/A"
        table.add_row(y.get("symbol", ""), y.get("chain", ""), y.get("project", ""), apy, tvl)
    console.print(table)


@defi_app.command("prices")
def defi_prices(
    tokens: list[str] = typer.Argument(help="Tokens as chain:address (e.g. ethereum:0xA0b8...)"),
):
    """Check current prices for one or more tokens."""
    from analytics.defillama import DefiLlamaAnalyzer

    pairs = []
    for t in tokens:
        if ":" not in t:
            console.print(f"[red]Invalid format: {t} — use chain:address[/red]")
            raise typer.Exit(1)
        chain, addr = t.split(":", 1)
        pairs.append((chain, addr))

    dl = DefiLlamaAnalyzer()
    with console.status("Fetching prices..."):
        prices = dl.prices_current(pairs)

    table = Table(title="Current Prices")
    table.add_column("Token", style="cyan")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Confidence", justify="right", style="dim")

    for symbol, info in prices.items():
        conf = f"{info['confidence']:.3f}" if info.get("confidence") else "N/A"
        table.add_row(symbol, f"${info['price']:,.6f}", conf)

    console.print(table)


@defi_app.command("history")
def defi_history(
    token: str = typer.Argument(help="Token as chain:address"),
    days: int = typer.Option(30, help="Number of days of history"),
):
    """Price history for a token over time."""
    from analytics.defillama import DefiLlamaAnalyzer

    if ":" not in token:
        console.print("[red]Use chain:address format (e.g. ethereum:0xA0b8...)[/red]")
        raise typer.Exit(1)

    chain, addr = token.split(":", 1)
    dl = DefiLlamaAnalyzer()

    with console.status(f"Fetching {days}d price history..."):
        history = dl.price_history(chain, addr, days=days)

    if not history:
        console.print("[yellow]No price data found[/yellow]")
        raise typer.Exit(1)

    from datetime import datetime

    table = Table(title=f"Price History ({days}d)")
    table.add_column("Date", style="dim")
    table.add_column("Price", justify="right", style="green")

    for p in history:
        dt = datetime.fromtimestamp(p["timestamp"]).strftime("%Y-%m-%d %H:%M")
        table.add_row(dt, f"${p['price']:,.6f}")

    console.print(table)
    console.print(
        f"\n[dim]Range: ${min(p['price'] for p in history):,.4f} — "
        f"${max(p['price'] for p in history):,.4f}[/dim]"
    )


@defi_app.command("tvl")
def defi_tvl(
    top: int = typer.Option(25, help="Number of protocols to show"),
):
    """Top protocols ranked by TVL."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status("Fetching protocol TVL data..."):
        protocols = dl.protocols(top_n=top)

    table = Table(title=f"Top {top} Protocols by TVL")
    table.add_column("#", style="dim")
    table.add_column("Protocol", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("TVL", justify="right", style="green")
    table.add_column("1d Change", justify="right")
    table.add_column("7d Change", justify="right")
    table.add_column("Chains", style="dim", max_width=30)

    for i, p in enumerate(protocols, 1):
        tvl = f"${p['tvl']:,.0f}" if p.get("tvl") else "N/A"
        d1 = p.get("change_1d")
        d7 = p.get("change_7d")
        d1_str = f"[{'green' if d1 and d1 > 0 else 'red'}]{d1:+.1f}%[/]" if d1 is not None else "N/A"
        d7_str = f"[{'green' if d7 and d7 > 0 else 'red'}]{d7:+.1f}%[/]" if d7 is not None else "N/A"
        chains = ", ".join(p.get("chains", [])[:5])
        if len(p.get("chains", [])) > 5:
            chains += f" +{len(p['chains']) - 5}"
        table.add_row(str(i), p["name"], p.get("category", ""), tvl, d1_str, d7_str, chains)

    console.print(table)


@defi_app.command("protocol")
def defi_protocol(
    slug: str = typer.Argument(help="Protocol slug (e.g. aave, uniswap, lido)"),
):
    """Detailed TVL breakdown for a protocol by chain."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status(f"Fetching {slug} details..."):
        detail = dl.protocol_detail(slug)

    console.print(Panel(
        f"[bold]{detail['name']}[/bold] ({detail.get('symbol', 'N/A')})\n"
        f"Category: {detail.get('category', 'N/A')}\n"
        f"Total TVL: [green]${detail.get('tvl', 0):,.0f}[/green]\n"
        f"Chains: {', '.join(detail.get('chains', []))}\n\n"
        f"{detail.get('description', '')[:200]}",
        title="Protocol Detail",
    ))

    if detail.get("chain_tvls"):
        table = Table(title="TVL by Chain")
        table.add_column("Chain", style="cyan")
        table.add_column("TVL", justify="right", style="green")
        table.add_column("% of Total", justify="right", style="yellow")

        total = sum(detail["chain_tvls"].values())
        for chain, tvl in sorted(detail["chain_tvls"].items(), key=lambda x: x[1], reverse=True):
            if tvl > 0:
                pct = (tvl / total * 100) if total else 0
                table.add_row(chain, f"${tvl:,.0f}", f"{pct:.1f}%")

        console.print(table)


@defi_app.command("dexes")
def defi_dexes(
    chain: str = typer.Option(None, help="Filter by chain (e.g. ethereum, base)"),
    top: int = typer.Option(20, help="Number of DEXes to show"),
):
    """DEX volume rankings — global or per-chain."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()

    if chain:
        with console.status(f"Fetching DEX volumes on {chain}..."):
            dexes = dl.dex_volume_by_chain(chain, top_n=top)
        title = f"DEX Volumes on {chain.title()}"
    else:
        with console.status("Fetching global DEX volumes..."):
            dexes = dl.dex_volumes(top_n=top)
        title = "Global DEX Volumes"

    table = Table(title=title)
    table.add_column("#", style="dim")
    table.add_column("DEX", style="cyan")
    table.add_column("24h Volume", justify="right", style="green")
    table.add_column("7d Volume", justify="right", style="dim")
    table.add_column("24h Change", justify="right")

    for i, d in enumerate(dexes, 1):
        vol24 = f"${d['volume_24h']:,.0f}" if d.get("volume_24h") else "N/A"
        vol7d = f"${d.get('volume_7d', 0):,.0f}" if d.get("volume_7d") else ""
        chg = d.get("change_1d")
        chg_str = f"[{'green' if chg and chg > 0 else 'red'}]{chg:+.1f}%[/]" if chg else ""
        table.add_row(str(i), d["name"], vol24, vol7d, chg_str)

    console.print(table)


@defi_app.command("chains")
def defi_chains():
    """All chains ranked by TVL."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status("Fetching chain TVL data..."):
        chains = dl.chains()

    table = Table(title="Chains by TVL")
    table.add_column("#", style="dim")
    table.add_column("Chain", style="cyan")
    table.add_column("TVL", justify="right", style="green")

    for i, c in enumerate(chains[:30], 1):
        table.add_row(str(i), c["name"], f"${c['tvl']:,.0f}")

    console.print(table)
    if len(chains) > 30:
        console.print(f"[dim]Showing 30 of {len(chains)} chains[/dim]")


@defi_app.command("stables")
def defi_stables(
    top: int = typer.Option(15, help="Number of stablecoins to show"),
):
    """Stablecoin market caps and peg mechanisms."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status("Fetching stablecoin data..."):
        stables = dl.stablecoins(top_n=top)

    table = Table(title=f"Top {top} Stablecoins")
    table.add_column("#", style="dim")
    table.add_column("Stablecoin", style="cyan")
    table.add_column("Symbol", style="dim")
    table.add_column("Circulating", justify="right", style="green")
    table.add_column("Mechanism", style="dim")
    table.add_column("Chains", style="dim", max_width=30)

    for i, s in enumerate(stables, 1):
        circ = f"${s['circulating']:,.0f}" if s.get("circulating") else "N/A"
        chains = ", ".join(s.get("chains", [])[:4])
        if len(s.get("chains", [])) > 4:
            chains += f" +{len(s['chains']) - 4}"
        table.add_row(str(i), s["name"], s.get("symbol", ""), circ, s.get("peg_mechanism", ""), chains)

    console.print(table)


@defi_app.command("yields")
def defi_yields(
    chain: str = typer.Option(None, help="Filter by chain"),
    project: str = typer.Option(None, help="Filter by project (e.g. aave, lido)"),
    top: int = typer.Option(25, help="Number of pools to show"),
    min_tvl: float = typer.Option(1_000_000, "--min-tvl", help="Minimum TVL in USD"),
):
    """Top yield opportunities across DeFi."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status("Fetching yield data..."):
        yields = dl.yields(chain=chain, project=project, top_n=top, min_tvl=min_tvl)

    filter_str = ""
    if chain:
        filter_str += f" on {chain.title()}"
    if project:
        filter_str += f" ({project})"

    table = Table(title=f"Top Yield Opportunities{filter_str} (TVL > ${min_tvl:,.0f})")
    table.add_column("#", style="dim")
    table.add_column("Pool", style="cyan")
    table.add_column("Chain", style="dim")
    table.add_column("Protocol", style="dim")
    table.add_column("APY", justify="right", style="green")
    table.add_column("Base APY", justify="right", style="dim")
    table.add_column("Reward APY", justify="right", style="dim")
    table.add_column("TVL", justify="right", style="yellow")

    for i, y in enumerate(yields, 1):
        apy = f"{y['apy']:.2f}%" if y.get("apy") else "N/A"
        base = f"{y['apy_base']:.2f}%" if y.get("apy_base") else ""
        reward = f"{y['apy_reward']:.2f}%" if y.get("apy_reward") else ""
        tvl = f"${y['tvl']:,.0f}" if y.get("tvl") else "N/A"
        table.add_row(str(i), y.get("symbol", ""), y.get("chain", ""), y.get("project", ""), apy, base, reward, tvl)

    console.print(table)


@defi_app.command("chain")
def defi_chain_dive(
    chain: str = typer.Argument(help="Chain name (e.g. ethereum, base, arbitrum)"),
):
    """Deep dive into a specific chain — DEX volumes and top yields."""
    from analytics.defillama import DefiLlamaAnalyzer

    dl = DefiLlamaAnalyzer()
    with console.status(f"Analyzing {chain}..."):
        data = dl.chain_deep_dive(chain)

    table = Table(title=f"DEX Volumes on {chain.title()}")
    table.add_column("DEX", style="cyan")
    table.add_column("24h Volume", justify="right", style="green")
    table.add_column("7d Volume", justify="right", style="dim")
    for d in data["dex_volumes"]:
        vol24 = f"${d['volume_24h']:,.0f}" if d.get("volume_24h") else "N/A"
        vol7d = f"${d.get('volume_7d', 0):,.0f}" if d.get("volume_7d") else ""
        table.add_row(d["name"], vol24, vol7d)
    console.print(table)

    console.print()
    table = Table(title=f"Top Yields on {chain.title()}")
    table.add_column("Pool", style="cyan")
    table.add_column("Protocol", style="dim")
    table.add_column("APY", justify="right", style="green")
    table.add_column("TVL", justify="right", style="yellow")
    for y in data["top_yields"]:
        apy = f"{y['apy']:.2f}%" if y.get("apy") else "N/A"
        tvl = f"${y['tvl']:,.0f}" if y.get("tvl") else "N/A"
        table.add_row(y.get("symbol", ""), y.get("project", ""), apy, tvl)
    console.print(table)


if __name__ == "__main__":
    app()
