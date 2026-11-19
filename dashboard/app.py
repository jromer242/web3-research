"""
Web3 Research Dashboard — live on-chain analytics via DefiLlama.

Run: streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analytics.defillama import DefiLlamaAnalyzer

st.set_page_config(
    page_title="Web3 Research Dashboard",
    page_icon="📊",
    layout="wide",
)


CHAIN_COLORS = {
    "Ethereum": "#627EEA",
    "Base": "#0052FF",
    "Solana": "#9945FF",
    "BSC": "#F0B90B",
    "Arbitrum": "#28A0F0",
    "Polygon": "#8247E5",
    "Avalanche": "#E84142",
    "Tron": "#FF0013",
    "Optimism": "#FF0420",
    "Bitcoin": "#F7931A",
}


@st.cache_resource
def get_analyzer():
    return DefiLlamaAnalyzer()


@st.cache_data(ttl=300)
def fetch_chains():
    return get_analyzer().chains()


@st.cache_data(ttl=300)
def fetch_protocols(n):
    return get_analyzer().protocols(top_n=n)


@st.cache_data(ttl=300)
def fetch_dex_volumes(n):
    return get_analyzer().dex_volumes(top_n=n)


@st.cache_data(ttl=300)
def fetch_dex_volumes_chain(chain, n):
    return get_analyzer().dex_volume_by_chain(chain, top_n=n)


@st.cache_data(ttl=300)
def fetch_stablecoins(n):
    return get_analyzer().stablecoins(top_n=n)


@st.cache_data(ttl=300)
def fetch_yields(chain, project, n, min_tvl):
    return get_analyzer().yields(chain=chain, project=project, top_n=n, min_tvl=min_tvl)


@st.cache_data(ttl=300)
def fetch_protocol_detail(slug):
    return get_analyzer().protocol_detail(slug)


@st.cache_data(ttl=600)
def fetch_price_history(chain, address, days):
    return get_analyzer().price_history(chain, address, days=days)


# ── Sidebar ─────────────────────────────────────────────────────────

st.sidebar.title("Web3 Research")
st.sidebar.caption("Live data from DefiLlama — no API key required")

page = st.sidebar.radio(
    "Navigate",
    ["Market Overview", "Protocol Deep Dive", "DEX Volumes", "Yield Explorer", "Price Tracker"],
)


# ── Market Overview ─────────────────────────────────────────────────

if page == "Market Overview":
    st.title("Market Overview")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Chain TVL Rankings")
        chains = fetch_chains()
        df_chains = pd.DataFrame(chains[:20])
        df_chains["tvl_b"] = df_chains["tvl"] / 1e9

        fig = px.bar(
            df_chains,
            x="tvl_b",
            y="name",
            orientation="h",
            labels={"tvl_b": "TVL (Billions USD)", "name": ""},
            color="name",
            color_discrete_map=CHAIN_COLORS,
        )
        fig.update_layout(showlegend=False, height=500, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Top Stablecoins")
        stables = fetch_stablecoins(15)
        df_stables = pd.DataFrame(stables)
        df_stables["circ_b"] = df_stables["circulating"].fillna(0) / 1e9

        fig = px.bar(
            df_stables,
            x="circ_b",
            y="name",
            orientation="h",
            labels={"circ_b": "Circulating (Billions USD)", "name": ""},
            color="peg_mechanism",
            color_discrete_map={
                "fiat-backed": "#2ecc71",
                "crypto-backed": "#3498db",
                "algorithmic": "#e74c3c",
            },
        )
        fig.update_layout(height=500, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top Protocols by TVL")
    protocols = fetch_protocols(30)
    df_protocols = pd.DataFrame(protocols)
    df_protocols["tvl_display"] = df_protocols["tvl"].apply(
        lambda x: f"${x / 1e9:.2f}B" if x and x >= 1e9 else f"${x / 1e6:.0f}M" if x else "N/A"
    )
    df_protocols["change_1d_display"] = df_protocols["change_1d"].apply(
        lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A"
    )
    df_protocols["change_7d_display"] = df_protocols["change_7d"].apply(
        lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A"
    )

    st.dataframe(
        df_protocols[["name", "category", "tvl_display", "change_1d_display", "change_7d_display"]].rename(
            columns={
                "name": "Protocol",
                "category": "Category",
                "tvl_display": "TVL",
                "change_1d_display": "1d Change",
                "change_7d_display": "7d Change",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# ── Protocol Deep Dive ──────────────────────────────────────────────

elif page == "Protocol Deep Dive":
    st.title("Protocol Deep Dive")

    protocols = fetch_protocols(50)
    protocol_slugs = {p["name"]: p["slug"] for p in protocols}

    selected = st.selectbox("Select Protocol", list(protocol_slugs.keys()))

    if selected:
        slug = protocol_slugs[selected]
        try:
            with st.spinner(f"Loading {selected}..."):
                detail = fetch_protocol_detail(slug)
        except Exception as e:
            st.error(f"Could not load protocol: {e}")
            st.stop()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total TVL", f"${detail.get('tvl', 0) / 1e9:.2f}B")
        col2.metric("Category", detail.get("category", "N/A"))
        col3.metric("Chains", str(len(detail.get("chains", []))))

        if detail.get("description"):
            st.caption(detail["description"][:300])

        chain_tvls = detail.get("chain_tvls", {})
        if chain_tvls:
            st.subheader("TVL by Chain")
            df_chain = pd.DataFrame(
                [{"Chain": k, "TVL": v} for k, v in chain_tvls.items() if v > 0]
            ).sort_values("TVL", ascending=False)

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    df_chain.head(15),
                    x="TVL",
                    y="Chain",
                    orientation="h",
                    labels={"TVL": "TVL (USD)"},
                    color="Chain",
                    color_discrete_map=CHAIN_COLORS,
                )
                fig.update_layout(showlegend=False, yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                top_5 = df_chain.head(5).copy()
                others = pd.DataFrame([{"Chain": "Others", "TVL": df_chain.iloc[5:]["TVL"].sum()}])
                pie_data = pd.concat([top_5, others]) if len(df_chain) > 5 else top_5
                fig = px.pie(pie_data, values="TVL", names="Chain", hole=0.4)
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)


# ── DEX Volumes ─────────────────────────────────────────────────────

elif page == "DEX Volumes":
    st.title("DEX Volume Analysis")

    view = st.radio("View", ["Global", "By Chain"], horizontal=True)

    if view == "Global":
        dexes = fetch_dex_volumes(25)
        df = pd.DataFrame(dexes)

        col1, col2, col3 = st.columns(3)
        total_24h = sum(d.get("volume_24h", 0) or 0 for d in dexes)
        total_7d = sum(d.get("volume_7d", 0) or 0 for d in dexes)
        col1.metric("Total 24h Volume (Top 25)", f"${total_24h / 1e9:.2f}B")
        col2.metric("Total 7d Volume (Top 25)", f"${total_7d / 1e9:.2f}B")
        col3.metric("DEXes Tracked", str(len(dexes)))

        df["vol_24h"] = df["volume_24h"].fillna(0)
        fig = px.bar(
            df.head(15),
            x="vol_24h",
            y="name",
            orientation="h",
            labels={"vol_24h": "24h Volume (USD)", "name": ""},
        )
        fig.update_layout(yaxis=dict(autorange="reversed"), height=500)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            df[["name", "volume_24h", "volume_7d", "change_1d"]],
            column_config={
                "name": "DEX",
                "volume_24h": st.column_config.NumberColumn("24h Volume", format="$%,.0f"),
                "volume_7d": st.column_config.NumberColumn("7d Volume", format="$%,.0f"),
                "change_1d": st.column_config.NumberColumn("24h Change %", format="%.1f%%"),
            },
            use_container_width=True,
            hide_index=True,
        )

    else:
        chain = st.selectbox(
            "Chain",
            ["ethereum", "base", "arbitrum", "polygon", "bsc", "solana", "avalanche", "optimism"],
        )
        dexes = fetch_dex_volumes_chain(chain, 20)
        df = pd.DataFrame(dexes)

        if df.empty:
            st.warning(f"No DEX data for {chain}")
        else:
            df["vol_24h"] = df["volume_24h"].fillna(0)
            fig = px.bar(
                df.head(10),
                x="vol_24h",
                y="name",
                orientation="h",
                labels={"vol_24h": "24h Volume (USD)", "name": ""},
                title=f"DEX Volumes on {chain.title()}",
            )
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                df[["name", "volume_24h", "volume_7d", "change_1d"]],
                column_config={
                    "name": "DEX",
                    "volume_24h": st.column_config.NumberColumn("24h Volume", format="$%,.0f"),
                    "volume_7d": st.column_config.NumberColumn("7d Volume", format="$%,.0f"),
                    "change_1d": st.column_config.NumberColumn("24h Change %", format="%.1f%%"),
                },
                use_container_width=True,
                hide_index=True,
            )


# ── Yield Explorer ──────────────────────────────────────────────────

elif page == "Yield Explorer":
    st.title("DeFi Yield Explorer")

    col1, col2, col3 = st.columns(3)
    with col1:
        chain_filter = st.selectbox(
            "Chain",
            [None, "ethereum", "base", "arbitrum", "polygon", "bsc", "solana", "avalanche"],
            format_func=lambda x: "All Chains" if x is None else x.title(),
        )
    with col2:
        project_filter = st.text_input("Protocol filter", placeholder="e.g. aave, lido, uniswap")
    with col3:
        min_tvl = st.number_input("Min TVL ($)", value=1_000_000, step=500_000, format="%d")

    yields = fetch_yields(
        chain=chain_filter,
        project=project_filter if project_filter else None,
        n=50,
        min_tvl=min_tvl,
    )
    df = pd.DataFrame(yields)

    if df.empty:
        st.info("No pools match the filters")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Pools Found", str(len(df)))
        col2.metric("Median APY", f"{df['apy'].median():.2f}%")
        col3.metric("Total TVL", f"${df['tvl'].sum() / 1e9:.2f}B")

        fig = px.scatter(
            df,
            x="tvl",
            y="apy",
            color="chain",
            hover_name="symbol",
            hover_data=["project", "apy_base", "apy_reward"],
            labels={"tvl": "TVL (USD)", "apy": "APY %", "chain": "Chain"},
            log_x=True,
            title="APY vs TVL (log scale)",
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            df[["symbol", "chain", "project", "apy", "apy_base", "apy_reward", "tvl"]],
            column_config={
                "symbol": "Pool",
                "chain": "Chain",
                "project": "Protocol",
                "apy": st.column_config.NumberColumn("APY %", format="%.2f%%"),
                "apy_base": st.column_config.NumberColumn("Base APY %", format="%.2f%%"),
                "apy_reward": st.column_config.NumberColumn("Reward APY %", format="%.2f%%"),
                "tvl": st.column_config.NumberColumn("TVL", format="$%,.0f"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ── Price Tracker ───────────────────────────────────────────────────

elif page == "Price Tracker":
    st.title("Token Price Tracker")

    PRESETS = {
        "WETH": ("ethereum", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
        "WBTC": ("ethereum", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),
        "USDC": ("ethereum", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
        "USDT": ("ethereum", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
        "LINK": ("ethereum", "0x514910771AF9Ca656af840dff83E8264EcF986CA"),
        "UNI": ("ethereum", "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"),
        "AAVE": ("ethereum", "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"),
        "Custom": None,
    }

    col1, col2 = st.columns([1, 2])
    with col1:
        token_choice = st.selectbox("Token", list(PRESETS.keys()))
        days = st.slider("Days", min_value=7, max_value=365, value=30)

    if token_choice == "Custom":
        with col2:
            chain = st.text_input("Chain", value="ethereum")
            address = st.text_input("Contract address", placeholder="0x...")
    else:
        chain, address = PRESETS[token_choice]

    if address:
        with st.spinner("Fetching price data..."):
            history = fetch_price_history(chain, address, days)

        if not history:
            st.warning("No price data returned")
        else:
            df = pd.DataFrame(history)
            df["date"] = pd.to_datetime(df["timestamp"], unit="s")

            current = df.iloc[-1]["price"]
            start = df.iloc[0]["price"]
            change_pct = ((current - start) / start) * 100
            high = df["price"].max()
            low = df["price"].min()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current", f"${current:,.2f}")
            col2.metric(f"{days}d Change", f"{change_pct:+.1f}%")
            col3.metric("High", f"${high:,.2f}")
            col4.metric("Low", f"${low:,.2f}")

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["date"],
                y=df["price"],
                mode="lines",
                name=token_choice,
                line=dict(color="#627EEA", width=2),
                fill="tozeroy",
                fillcolor="rgba(98, 126, 234, 0.1)",
            ))
            fig.update_layout(
                title=f"{token_choice} Price ({days}d)",
                xaxis_title="Date",
                yaxis_title="Price (USD)",
                height=450,
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
