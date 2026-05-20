import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
import os
import base64
import requests
import io

st.set_page_config(
    page_title="美股績效追蹤",
    page_icon="📈",
    layout="centered",
)

st.markdown("""
<style>
    /* ── 基礎 ── */
    .block-container { padding: 1.8rem 1rem 3rem; }
    header[data-testid="stHeader"] { display: none; }

    /* ── 數字字體：等寬，閱讀更精準 ── */
    .mono {
        font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace !important;
        letter-spacing: 0.5px;
    }

    /* ── Tab ── */
    [data-testid="stTabs"] button {
        font-size: 12px !important;
        padding: 6px 9px !important;
        letter-spacing: 0.4px;
        color: #4b5563 !important;
        text-transform: uppercase;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #00e5ff !important;
        font-weight: 700 !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"]::after {
        content: '';
        display: block;
        height: 2px;
        background: linear-gradient(90deg, #00e5ff, #006eff);
        border-radius: 2px;
        box-shadow: 0 0 8px rgba(0,229,255,0.6);
        margin-top: 4px;
    }

    /* ── Summary box ── */
    .summary-box {
        background: linear-gradient(135deg, #060d1f, #091428);
        border: 1px solid rgba(0,229,255,0.18);
        border-top: 2px solid rgba(0,229,255,0.7);
        box-shadow: 0 0 24px rgba(0,229,255,0.06), inset 0 0 30px rgba(0,0,0,0.4);
        color: #e2e8f0;
        border-radius: 12px;
        padding: 15px 18px;
        margin-bottom: 12px;
    }

    /* ── 活動指示燈動畫 ── */
    @keyframes pulse-dot {
        0%, 100% { opacity: 1; box-shadow: 0 0 4px #00e676, 0 0 8px #00e676; }
        50%       { opacity: 0.5; box-shadow: 0 0 2px #00e676; }
    }
    .live-dot {
        display: inline-block;
        width: 7px; height: 7px;
        border-radius: 50%;
        background: #00e676;
        animation: pulse-dot 2s ease-in-out infinite;
        vertical-align: middle;
        margin-right: 7px;
        margin-bottom: 2px;
    }

    /* ── 滾動條 ── */
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: #0a0e1a; }
    ::-webkit-scrollbar-thumb { background: rgba(0,229,255,0.2); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BASE_DIR, "portfolio.csv")
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.txt")
CASH_FILE = os.path.join(BASE_DIR, "cash.txt")
HISTORY_FILE = os.path.join(BASE_DIR, "history.csv")


def load_portfolio() -> pd.DataFrame:
    # 雲端：從 Streamlit Secrets 讀取
    if "portfolio" in st.secrets:
        p = st.secrets["portfolio"]
        df = pd.DataFrame({
            "ticker": p["tickers"].split(","),
            "shares": [float(x) for x in p["shares"].split(",")],
            "cost":   [float(x) for x in p["costs"].split(",")],
        })
    else:
        df = pd.read_csv(PORTFOLIO_FILE)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df


def load_watchlist() -> list[str]:
    if "watchlist" in st.secrets:
        return [t.strip().upper() for t in st.secrets["watchlist"]["tickers"].split(",")]
    with open(WATCHLIST_FILE) as f:
        return [line.strip().upper() for line in f if line.strip()]


def save_watchlist(tickers: list[str]):
    with open(WATCHLIST_FILE, "w") as f:
        f.write("\n".join(t.upper().strip() for t in tickers if t.strip()))


def save_portfolio(df: pd.DataFrame):
    df.to_csv(PORTFOLIO_FILE, index=False)


def load_cash() -> float:
    if "cash" in st.secrets:
        return float(st.secrets["cash"]["amount"])
    with open(CASH_FILE) as f:
        return float(f.read().strip())


def save_cash(val: float):
    with open(CASH_FILE, "w") as f:
        f.write(str(val))


def _gh_headers():
    if "github" not in st.secrets:
        return None, None
    token = st.secrets["github"]["token"]
    repo  = st.secrets["github"]["repo"]
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}, repo


def load_history() -> pd.DataFrame:
    empty = pd.DataFrame(columns=["date", "portfolio", "cash", "total"])
    headers, repo = _gh_headers()
    if headers is None:
        if os.path.exists(HISTORY_FILE):
            return pd.read_csv(HISTORY_FILE, parse_dates=["date"])
        return empty
    url = f"https://api.github.com/repos/{repo}/contents/history.csv"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return empty
    content = base64.b64decode(r.json()["content"]).decode()
    return pd.read_csv(io.StringIO(content), parse_dates=["date"])


def append_history(portfolio_val: float, cash_val: float):
    try:
        today = date.today().isoformat()
        headers, repo = _gh_headers()
        df = load_history()
        if today in df["date"].astype(str).values:
            return
        new_row = pd.DataFrame([{
            "date": today,
            "portfolio": round(portfolio_val, 2),
            "cash": round(cash_val, 2),
            "total": round(portfolio_val + cash_val, 2),
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        csv_str = df.to_csv(index=False)

        if headers is None:
            df.to_csv(HISTORY_FILE, index=False)
            return

        # 取得目前檔案的 SHA（更新用）
        url = f"https://api.github.com/repos/{repo}/contents/history.csv"
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None

        payload = {
            "message": f"history: {today}",
            "content": base64.b64encode(csv_str.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        requests.put(url, json=payload, headers=headers)
    except Exception:
        pass


# 出入金明細備用（Secrets 優先）
_TRANSACTIONS_FALLBACK = [
    ("2022-06-07",  5469.56),
    ("2022-12-02", -1030.00),
    ("2023-11-15", -2030.00),
    ("2025-06-05",  6178.00),
    ("2026-03-18", 10025.70),
    ("2026-05-18",  2510.00),
]
_SUB_START_FALLBACK = ("2025-06-05", 8857.84)


def load_transactions():
    try:
        if "transactions" in st.secrets:
            tx = st.secrets["transactions"]
            dates   = [d.strip() for d in str(tx["dates"]).split(",")]
            amounts = [float(a.strip()) for a in str(tx["amounts"]).split(",")]
            if len(dates) == len(amounts):
                return list(zip(dates, amounts))
    except Exception:
        pass
    return _TRANSACTIONS_FALLBACK


def load_sub_period():
    try:
        if "transactions" in st.secrets:
            tx = st.secrets["transactions"]
            sd = str(tx["sub_start_date"]).strip()
            sv = float(str(tx["sub_start_value"]).strip())
            return sd, sv
    except Exception:
        pass
    return _SUB_START_FALLBACK


def _tx_source() -> str:
    try:
        return "Secrets ✓" if ("transactions" in st.secrets and "dates" in st.secrets["transactions"]) else "備用資料"
    except Exception:
        return "備用資料"


def calc_irr(terminal_value: float, transactions=None) -> float | None:
    from datetime import datetime as dt
    txns = transactions if transactions is not None else _TRANSACTIONS_FALLBACK
    dates = [dt.strptime(d, "%Y-%m-%d") for d, _ in txns]
    t0 = dates[0]
    times = [(d - t0).days / 365.25 for d in dates]
    # 投資人視角：入金 = 負 CF，出金 = 正 CF
    cfs = [-amt for _, amt in txns]
    times.append((dt.today() - t0).days / 365.25)
    cfs.append(terminal_value)

    def npv(r):
        return sum(cf / (1 + r) ** t for cf, t in zip(cfs, times))

    lo, hi = -0.99, 20.0
    try:
        if npv(lo) * npv(hi) > 0:
            return None
        for _ in range(300):
            mid = (lo + hi) / 2
            if npv(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-9:
                break
        return (lo + hi) / 2
    except Exception:
        return None


@st.cache_data(ttl=3600)
def estimate_stock_value_at(date_str: str, tickers_shares: tuple) -> float:
    """用歷史收盤價估計某日的股票市值（假設持股數與現在相同）。"""
    tickers = [t for t, _ in tickers_shares]
    if not tickers:
        return 0.0
    try:
        start = (pd.Timestamp(date_str) - pd.DateOffset(days=10)).strftime("%Y-%m-%d")
        end   = (pd.Timestamp(date_str) + pd.DateOffset(days=3)).strftime("%Y-%m-%d")
        raw   = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
        closes = raw["Close"]
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(name=tickers[0])
        if isinstance(closes.columns, pd.MultiIndex):
            closes.columns = closes.columns.get_level_values(0)
        if closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)
        valid = closes[closes.index <= pd.Timestamp(date_str)]
        if valid.empty:
            return 0.0
        row = valid.iloc[-1]
        return round(sum(
            float(row[t]) * float(s)
            for t, s in tickers_shares
            if t in row.index and not pd.isna(row[t])
        ), 2)
    except Exception:
        return 0.0


@st.cache_data(ttl=3600)
def fetch_bench_data() -> pd.DataFrame:
    try:
        raw = yf.download(["SPY", "QQQ", "SOXX"], period="3y", auto_adjust=True, progress=False)
        df = raw["Close"].dropna(how="all")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_prices(tickers: tuple) -> dict:
    if not tickers:
        return {}
    result = {}
    try:
        raw = yf.download(list(tickers), period="5d", auto_adjust=True, progress=False, threads=True)
        close = raw["Close"]
        if isinstance(close, pd.Series):
            # 只有一支股票時是 Series
            close = close.to_frame(name=list(tickers)[0])
        for ticker in tickers:
            if ticker not in close.columns:
                continue
            series = close[ticker].dropna()
            if len(series) < 2:
                continue
            prev = float(series.iloc[-2])
            curr = float(series.iloc[-1])
            change = curr - prev
            pct = (change / prev) * 100
            result[ticker] = {
                "price": round(curr, 2),
                "change": round(change, 2),
                "pct": round(pct, 2),
            }
    except Exception as e:
        st.warning(f"資料抓取發生錯誤：{e}")
    return result


# ── 載入資料 ─────────────────────────────────────────
IS_CLOUD = "portfolio" in st.secrets  # 雲端版不顯示編輯功能
portfolio = load_portfolio()
watchlist = load_watchlist()
cash = load_cash()

# 合併所有 ticker 一次抓
all_tickers = tuple(set(portfolio["ticker"].tolist() + watchlist))
prices = fetch_prices(all_tickers)

# ── 標題列 ───────────────────────────────────────────
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.markdown(
        f'<div style="padding:4px 0 10px;">'
        f'<div style="font-size:17px;font-weight:800;letter-spacing:2px;'
        f'text-transform:uppercase;color:#e2e8f0;">'
        f'<span class="live-dot"></span>美股績效追蹤</div>'
        f'<div style="font-size:10px;color:#374151;letter-spacing:1px;margin-top:3px;'
        f'font-family:\'SF Mono\',monospace">'
        f'PORTFOLIO DASHBOARD &nbsp;·&nbsp; {datetime.now().strftime("%Y/%m/%d %H:%M")}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
with col_refresh:
    if st.button("↺", help="重新載入", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── 計算股票總市值（各 tab 共用）─────────────────────
portfolio_value = sum(
    prices[r["ticker"]]["price"] * float(r["shares"])
    for _, r in portfolio.iterrows() if r["ticker"] in prices
)
append_history(portfolio_value, cash)

# ── Tab ──────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["💼 我的持倉", "👀 追蹤清單", "📊 總資產", "💰 配置", "📈 績效"])

# ════════════════════════════════════════════════════
# Tab 1 — 持倉
# ════════════════════════════════════════════════════
with tab1:

    # 按總市值排序
    portfolio = portfolio.copy()
    portfolio["_mktval"] = portfolio.apply(
        lambda r: prices[r["ticker"]]["price"] * float(r["shares"]) if r["ticker"] in prices else 0,
        axis=1,
    )
    portfolio = portfolio.sort_values("_mktval", ascending=False).drop(columns=["_mktval"])

    # 今日總變動
    total_daily_pnl = 0.0
    total_value = 0.0
    for _, row in portfolio.iterrows():
        t = row["ticker"]
        if t in prices:
            total_daily_pnl += prices[t]["change"] * float(row["shares"])
            total_value += prices[t]["price"] * float(row["shares"])

    d_sign = "+" if total_daily_pnl >= 0 else ""
    d_arrow = "▲" if total_daily_pnl >= 0 else "▼"

    st.markdown(f"""
    <div class="summary-box">
        <div style="font-size:11px;opacity:0.8">今日變動</div>
        <div style="font-size:26px;font-weight:bold">{d_arrow} {d_sign}${abs(total_daily_pnl):,.0f}</div>
        <div style="font-size:12px;margin-top:4px;opacity:0.85">總市值 ${total_value:,.0f}</div>
    </div>
    """, unsafe_allow_html=True)

    # 各股卡片
    cards_html = ""
    for _, row in portfolio.iterrows():
        ticker = row["ticker"]
        shares = float(row["shares"])
        cost = float(row["cost"])

        if ticker not in prices:
            continue

        p = prices[ticker]
        price = p["price"]
        change = p["change"]
        pct = p["pct"]
        daily_pnl = change * shares
        total_pnl = (price - cost) * shares
        total_pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0

        sign = "+" if change >= 0 else ""
        d_sign = "+" if daily_pnl >= 0 else ""
        t_sign = "+" if total_pnl >= 0 else ""
        chg_hex = "#00e676" if change >= 0 else "#ff5252"
        day_hex = "#00e676" if daily_pnl >= 0 else "#ff5252"
        tot_hex = "#00e676" if total_pnl >= 0 else "#ff5252"
        bar_color = "#00e676" if daily_pnl >= 0 else "#ff5252"
        bg_tint = "rgba(0,230,118,0.04)" if daily_pnl >= 0 else "rgba(255,82,82,0.04)"

        cards_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:12px 10px 12px 14px;'
            f'border-bottom:1px solid rgba(255,255,255,0.06);'
            f'border-left:2px solid {bar_color};'
            f'background:linear-gradient(90deg,{bg_tint},transparent);'
            f'gap:4px;">'
            f'<div style="flex:1">'
            f'<div style="font-size:13px;font-weight:800;color:#e2e8f0;letter-spacing:1.5px;'
            f'font-family:\'SF Mono\',monospace">{ticker}</div>'
            f'<div style="font-size:21px;font-weight:700;color:#f8fafc;'
            f'font-family:\'SF Mono\',monospace;letter-spacing:-0.5px">${price:.2f}</div>'
            f'<div style="font-size:12px;color:{chg_hex};font-weight:600;'
            f'font-family:\'SF Mono\',monospace">{sign}{change:.2f}&nbsp;({sign}{pct:.2f}%)</div>'
            f'</div>'
            f'<div style="flex:1;text-align:center;font-size:12px;color:#64748b;line-height:2">'
            f'<div>{shares:g} 股</div>'
            f'<div style="color:{day_hex};font-weight:700;font-family:\'SF Mono\',monospace">'
            f'Today {d_sign}${abs(daily_pnl):,.0f}</div>'
            f'</div>'
            f'<div style="flex:1;text-align:right;font-size:12px;color:#64748b;line-height:2">'
            f'<div>成本 ${cost:.2f}</div>'
            f'<div style="color:{tot_hex};font-weight:700;font-family:\'SF Mono\',monospace">'
            f'{t_sign}${abs(total_pnl):,.0f}</div>'
            f'<div style="font-size:11px;color:{tot_hex};font-family:\'SF Mono\',monospace">'
            f'{t_sign}{total_pnl_pct:.1f}%</div>'
            f'</div>'
            f'</div>'
        )

    st.markdown(cards_html, unsafe_allow_html=True)

    # 編輯持倉（本機才顯示）
    if not IS_CLOUD:
        with st.expander("✏️ 編輯持倉"):
            edited = st.data_editor(
                portfolio,
                column_config={
                    "ticker": st.column_config.TextColumn("代號"),
                    "shares": st.column_config.NumberColumn("持股數", min_value=0, step=1),
                    "cost": st.column_config.NumberColumn("成本/股 ($)", min_value=0, format="%.2f"),
                },
                num_rows="dynamic",
                use_container_width=True,
                key="portfolio_editor",
            )
            if st.button("💾 儲存變更", use_container_width=True):
                edited["ticker"] = edited["ticker"].str.upper().str.strip()
                save_portfolio(edited)
                st.cache_data.clear()
                st.session_state.pop("portfolio_editor", None)
                st.rerun()

# ════════════════════════════════════════════════════
# Tab 2 — 追蹤清單
# ════════════════════════════════════════════════════
with tab2:
    # 編輯追蹤清單（本機才顯示）
    if not IS_CLOUD:
        with st.expander("✏️ 編輯追蹤清單"):
            wl_df = pd.DataFrame({"ticker": watchlist})
            edited_wl = st.data_editor(
                wl_df,
                column_config={"ticker": st.column_config.TextColumn("股票代號")},
                num_rows="dynamic",
                use_container_width=True,
                key="watchlist_editor",
            )
            if st.button("💾 儲存清單", use_container_width=True):
                new_wl = edited_wl["ticker"].dropna().tolist()
                save_watchlist(new_wl)
                st.cache_data.clear()
                st.session_state.pop("watchlist_editor", None)
                st.rerun()

    wl_items = ""
    for ticker in watchlist:
        if ticker not in prices:
            wl_items += (
                f'<div style="background:#111827;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:10px 12px;">'
                f'<div style="font-size:13px;font-weight:700;color:#e2e8f0">{ticker}</div>'
                f'<div style="font-size:11px;color:#4b5563">—</div></div>'
            )
            continue
        p = prices[ticker]
        price = p["price"]
        change = p["change"]
        pct = p["pct"]
        sign = "+" if pct >= 0 else ""
        intensity = min(abs(pct) / 5.0, 1.0) * 0.22
        if pct >= 0:
            bg = f"rgba(0,230,118,{intensity:.2f})"
            border = "rgba(0,230,118,0.3)"
            chg_hex = "#00e676"
        else:
            bg = f"rgba(255,82,82,{intensity:.2f})"
            border = "rgba(255,82,82,0.3)"
            chg_hex = "#ff5252"
        wl_items += (
            f'<div style="background:{bg};border:1px solid {border};border-radius:10px;padding:10px 12px;">'
            f'<div style="font-size:13px;font-weight:700;color:#e2e8f0">{ticker}</div>'
            f'<div style="font-size:18px;font-weight:700;color:#f8fafc">${price:.2f}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{chg_hex}">{sign}{pct:.2f}%&nbsp;&nbsp;{sign}${abs(change):.2f}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px;">{wl_items}</div>',
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════
# Tab 3 — 總資產
# ════════════════════════════════════════════════════
with tab3:
    total_assets = portfolio_value + cash

    st.markdown(f"""
    <div class="summary-box">
        <div style="font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase">Total Assets</div>
        <div style="font-size:28px;font-weight:700;color:#00e5ff;margin-top:2px">${total_assets:,.0f}</div>
    </div>
    <div style="display:flex;gap:10px;margin-bottom:14px;">
      <div style="flex:1;background:#0d1f3c;border:1px solid rgba(0,229,255,0.15);border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:#64748b;letter-spacing:0.5px">股票市值</div>
        <div style="font-size:17px;font-weight:700;color:#e2e8f0">${portfolio_value:,.0f}</div>
      </div>
      <div style="flex:1;background:#0d1f3c;border:1px solid rgba(248,196,113,0.2);border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:#64748b;letter-spacing:0.5px">現金水位</div>
        <div style="font-size:17px;font-weight:700;color:#f8c471">${cash:,.2f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Treemap：面積 = 市值，顏色 = 總損益%
    tm_labels = ["總資產"]
    tm_parents = [""]
    tm_values = [0]
    tm_colors = [0]
    tm_text = [""]

    for _, row in portfolio.iterrows():
        t = row["ticker"]
        if t not in prices:
            continue
        p = prices[t]
        val = p["price"] * float(row["shares"])
        daily_pnl = p["change"] * float(row["shares"])
        pct = p["pct"]
        sign = "+" if pct >= 0 else ""
        tm_labels.append(t)
        tm_parents.append("總資產")
        tm_values.append(val)
        tm_colors.append(pct)
        tm_text.append(f"${val:,.0f}<br>{sign}{pct:.2f}%")

    tm_labels.append("現金")
    tm_parents.append("總資產")
    tm_values.append(cash)
    tm_colors.append(0)
    tm_text.append(f"${cash:,.0f}")

    fig = go.Figure(go.Treemap(
        labels=tm_labels,
        parents=tm_parents,
        values=tm_values,
        customdata=tm_text,
        texttemplate="<b>%{label}</b><br>%{customdata}",
        hovertemplate="%{label}<br>市值 $%{value:,.0f}<extra></extra>",
        marker=dict(
            colors=tm_colors,
            colorscale=[[0, "#7f1d1d"], [0.5, "#1e293b"], [1, "#14532d"]],
            cmid=0,
            cmin=-3,
            cmax=3,
            line=dict(width=2, color="#0a0e1a"),
        ),
        textfont=dict(size=13, color="#e2e8f0"),
        pathbar=dict(visible=False),
    ))
    fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0),
        height=360,
        paper_bgcolor="#0a0e1a",
    )
    fig.data[0].marker.colors = [
        "#2d3748" if l == "現金" else c
        for l, c in zip(tm_labels, tm_colors)
    ]
    st.plotly_chart(fig, use_container_width=True)

    # 更新現金（本機才顯示）
    if not IS_CLOUD:
        with st.expander("✏️ 更新現金水位"):
            new_cash = st.number_input("現金（USD）", value=cash, min_value=0.0, step=100.0, format="%.2f")
            if st.button("💾 儲存現金", use_container_width=True):
                save_cash(new_cash)
                st.success("已儲存！")
                st.rerun()

    # 歷史明細
    hist = load_history()
    with st.expander("📋 歷史明細"):
        if not hist.empty:
            hist_display = hist.sort_values("date", ascending=False).copy()
            hist_display["date"] = hist_display["date"].astype(str)
            st.dataframe(hist_display, use_container_width=True, hide_index=True)
        else:
            st.caption("尚無資料")

# ════════════════════════════════════════════════════
# Tab 4 — 配置
# ════════════════════════════════════════════════════
with tab4:
    total_assets4 = portfolio_value + cash

    # ── 計算各股市值 ────────────────────────────────
    _port = portfolio.copy()
    _port["_val"] = _port.apply(
        lambda r: prices[r["ticker"]]["price"] * float(r["shares"]) if r["ticker"] in prices else 0,
        axis=1,
    )
    stock_vals = dict(zip(_port["ticker"], _port["_val"]))

    # 分類定義：(成員list, 顏色)
    CATS = {
        "AI / 半導體": (["NVDA", "AMD", "INTC", "SMCI", "ALAB"], "#00e5ff"),
        "科技大型股":  (["AAPL", "AMZN", "META", "TSLA", "GOOG"],  "#c084fc"),
        "太空 / 新興": (["ASTS", "PLTR", "PATH", "PACB"],          "#00e676"),
        "槓桿 ETF":   (["SOXL", "TQQQ", "TECL", "UPRO", "SPXL",
                        "FNGU", "TSLL", "NVDL", "LABU", "WEBL",
                        "TNA",  "NAIL", "DFEN", "WANT", "RETL"], "#fb923c"),
        "ETF":        (["VOO", "QQQ", "SPY", "IWM", "VTI"],       "#f8c471"),
        "其他":       (["CCL", "DJT"],                             "#94a3b8"),
        "現金":       ([],                                          "#2d3748"),
    }

    # 各類別總市值（過濾掉 0 值的類別，現金除外）
    cat_vals = {}
    for cat, (tickers, color) in CATS.items():
        val = cash if cat == "現金" else sum(stock_vals.get(t, 0) for t in tickers)
        if val > 0 or cat == "現金":
            cat_vals[cat] = (val, color)

    # ── 圓餅圖 ──────────────────────────────────────
    fig_pie = go.Figure(go.Pie(
        labels=list(cat_vals.keys()),
        values=[v for v, _ in cat_vals.values()],
        hole=0.52,
        marker=dict(
            colors=[c for _, c in cat_vals.values()],
            line=dict(color="#0a0e1a", width=3),
        ),
        textinfo="label+percent",
        textfont=dict(size=12, color="#e2e8f0"),
        hovertemplate="%{label}<br>$%{value:,.0f} (%{percent})<extra></extra>",
        sort=False,
    ))
    fig_pie.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        height=290,
        paper_bgcolor="#0a0e1a",
        showlegend=False,
        annotations=[dict(
            text=f"<b>${total_assets4:,.0f}</b><br>總資產",
            x=0.5, y=0.5,
            font=dict(size=13, color="#e2e8f0"),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    # ── 分類細項 ────────────────────────────────────
    detail_html = ""
    for cat, (tickers, color) in CATS.items():
        val, _ = cat_vals[cat]
        pct = val / total_assets4 * 100 if total_assets4 > 0 else 0
        if cat == "現金":
            detail = f"${cash:,.0f}"
        else:
            parts = [f"{t}&nbsp;${stock_vals.get(t,0):,.0f}" for t in tickers if stock_vals.get(t, 0) > 0]
            detail = "&ensp;·&ensp;".join(parts) if parts else "—"
        detail_html += (
            f'<div style="padding:8px 2px 6px;border-bottom:1px solid rgba(255,255,255,0.06);">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<div style="width:9px;height:9px;border-radius:50%;background:{color};flex-shrink:0;box-shadow:0 0 6px {color}88"></div>'
            f'<div style="flex:1;font-size:13px;font-weight:600;color:#e2e8f0">{cat}</div>'
            f'<div style="font-size:12px;color:#64748b;margin-right:8px">{pct:.1f}%</div>'
            f'<div style="font-size:13px;font-weight:600;color:#e2e8f0">${val:,.0f}</div>'
            f'</div>'
            f'<div style="font-size:11px;color:#4b5563;margin-top:3px;padding-left:19px">{detail}</div>'
            f'</div>'
        )
    st.markdown(detail_html, unsafe_allow_html=True)

# ════════════════════════════════════════════════════
# Tab 5 — 績效
# ════════════════════════════════════════════════════
with tab5:
    # ── 載入出入金資料 ──────────────────────────────
    txns = load_transactions()
    sub_start_date, sub_start_value = load_sub_period()

    # ── IRR 全期 ─────────────────────────────────────
    total_assets5 = portfolio_value + cash
    irr = calc_irr(total_assets5, transactions=txns)
    total_deposited = sum(amt for _, amt in txns if amt > 0)
    total_withdrawn = sum(-amt for _, amt in txns if amt < 0)
    moic = (total_assets5 + total_withdrawn) / total_deposited if total_deposited > 0 else 0

    if irr is not None:
        irr_pct = irr * 100
        irr_color = "#00e676" if irr >= 0 else "#ff5252"
        irr_sign = "+" if irr >= 0 else ""
        irr_str = f"{irr_sign}{irr_pct:.1f}%"
    else:
        irr_str, irr_color = "—", "#64748b"

    st.markdown(
        f'<div class="summary-box">'
        f'<div style="font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase">年化報酬率（IRR / MWR）</div>'
        f'<div style="font-size:32px;font-weight:700;color:{irr_color};margin-top:4px">{irr_str}</div>'
        f'<div style="display:flex;gap:16px;margin-top:10px;font-size:12px;color:#64748b;">'
        f'<div>總投入 <b style="color:#e2e8f0">${total_deposited:,.0f}</b></div>'
        f'<div>已出金 <b style="color:#e2e8f0">${total_withdrawn:,.0f}</b></div>'
        f'<div>現值 <b style="color:#00e5ff">${total_assets5:,.0f}</b></div>'
        f'<div>MOIC <b style="color:#e2e8f0">{moic:.2f}x</b></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── IRR 子期間 ───────────────────────────────────
    txns_recent = [(sub_start_date, sub_start_value)] + [
        (d, amt) for d, amt in txns if d >= sub_start_date
    ]
    irr2 = calc_irr(total_assets5, transactions=txns_recent)
    dep2 = sum(amt for _, amt in txns_recent if amt > 0)
    wth2 = sum(-amt for _, amt in txns_recent if amt < 0)
    moic2 = total_assets5 / (dep2 - wth2) if (dep2 - wth2) > 0 else 0
    sub_label = sub_start_date.replace("-", "/")[:7]  # e.g. "2025/06"

    if irr2 is not None:
        irr2_pct = irr2 * 100
        irr2_color = "#00e676" if irr2 >= 0 else "#ff5252"
        irr2_sign = "+" if irr2 >= 0 else ""
        irr2_str = f"{irr2_sign}{irr2_pct:.1f}%"
    else:
        irr2_str, irr2_color = "—", "#64748b"

    st.markdown(
        f'<div style="background:linear-gradient(135deg,#0d2a1a,#0a3a1f);border:1px solid rgba(0,230,118,0.2);'
        f'border-radius:14px;padding:14px 18px;margin-bottom:12px;">'
        f'<div style="font-size:11px;color:#64748b;letter-spacing:1px;text-transform:uppercase">年化報酬（{sub_label} 起）</div>'
        f'<div style="font-size:28px;font-weight:700;color:{irr2_color};margin-top:4px">{irr2_str}</div>'
        f'<div style="display:flex;gap:12px;margin-top:8px;font-size:12px;color:#64748b;flex-wrap:wrap;">'
        f'<div>起始餘額 <b style="color:#e2e8f0">${sub_start_value:,.0f}</b></div>'
        f'<div>後續入金 <b style="color:#e2e8f0">${sum(amt for d,amt in txns if d>=sub_start_date and amt>0):,.0f}</b></div>'
        f'<div>現值 <b style="color:#00e5ff">${total_assets5:,.0f}</b></div>'
        f'<div>MOIC <b style="color:#e2e8f0">{moic2:.2f}x</b></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 出入金明細 ──────────────────────────────────
    src = _tx_source()
    src_color = "#00e676" if "✓" in src else "#f8c471"
    tx_html = (
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin:14px 0 8px;">'
        f'<div style="font-size:12px;font-weight:600;color:#64748b;letter-spacing:0.5px">出入金明細</div>'
        f'<div style="font-size:10px;color:{src_color};font-family:monospace">{src}</div>'
        f'</div>'
    )
    tx_html += '<div style="background:#111827;border-radius:10px;overflow:hidden;">'
    for d, amt in txns:
        is_in = amt > 0
        label = "入金" if is_in else "出金"
        color = "#00e676" if is_in else "#ff5252"
        sign = "+" if is_in else ""
        tx_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:9px 14px;border-bottom:1px solid rgba(255,255,255,0.05);font-size:13px;">'
            f'<div style="color:#94a3b8">{d}</div>'
            f'<div style="color:{color};font-weight:600;font-size:11px;'
            f'background:rgba({"0,230,118" if is_in else "255,82,82"},0.12);'
            f'padding:2px 8px;border-radius:4px">{label}</div>'
            f'<div style="color:{color};font-weight:700">{sign}${abs(amt):,.2f}</div>'
            f'</div>'
        )
    tx_html += '</div>'
    st.markdown(tx_html, unsafe_allow_html=True)

    # ── 指數比較表 ──────────────────────────────────
    bench_df = fetch_bench_data()
    today_ts = pd.Timestamp.today().normalize()
    BENCH = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("SOXX", "費城半導體")]

    def _fmt_pct(v):
        if v is None:
            return '<div style="text-align:right;color:#4b5563">—</div>'
        c = "#00e676" if v >= 0 else "#ff5252"
        sign = "+" if v >= 0 else ""
        return f'<div style="text-align:right;color:{c};font-weight:600">{sign}{v:.1f}%</div>'

    if not bench_df.empty:
        tbl = (
            '<div style="font-size:12px;font-weight:600;color:#64748b;margin:14px 0 8px;letter-spacing:0.5px">美股指數比較</div>'
            '<div style="background:#111827;border-radius:10px;overflow:hidden;">'
            '<div style="display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;padding:8px 12px;'
            'font-size:11px;color:#4b5563;border-bottom:1px solid rgba(255,255,255,0.06)">'
            '<div>指數</div><div style="text-align:right">YTD</div>'
            '<div style="text-align:right">近1年</div><div style="text-align:right">近3年(年化)</div>'
            '</div>'
        )
        for sym, name in BENCH:
            if sym not in bench_df.columns:
                continue
            s = bench_df[sym].dropna()
            curr = float(s.iloc[-1])
            ytd_s = s[s.index.year == today_ts.year]
            r_ytd = (curr / float(ytd_s.iloc[0]) - 1) * 100 if not ytd_s.empty else None
            i1y = s.index.searchsorted(today_ts - pd.DateOffset(years=1))
            r1y = (curr / float(s.iloc[i1y]) - 1) * 100 if i1y < len(s) else None
            i3y = s.index.searchsorted(today_ts - pd.DateOffset(years=3))
            r3y = ((curr / float(s.iloc[i3y])) ** (1/3) - 1) * 100 if i3y < len(s) else None
            tbl += (
                f'<div style="display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;'
                f'padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px;">'
                f'<div style="color:#e2e8f0">{name}'
                f'<br><span style="font-size:10px;color:#4b5563">{sym}</span></div>'
                f'{_fmt_pct(r_ytd)}{_fmt_pct(r1y)}{_fmt_pct(r3y)}'
                f'</div>'
            )
        tbl += '</div>'
        st.markdown(tbl, unsafe_allow_html=True)

        # ── 走勢對照圖 ──────────────────────────────
        hist5 = load_history()
        if len(hist5) >= 2:
            hist5 = hist5.sort_values("date")
            start_ts = pd.Timestamp(hist5["date"].min()).normalize()
            bench_trim = bench_df[bench_df.index >= start_ts]

            if not bench_trim.empty:
                fig_b = go.Figure()
                first_total = float(hist5["total"].iloc[0])
                fig_b.add_trace(go.Scatter(
                    x=hist5["date"], y=hist5["total"] / first_total * 100,
                    name="我的投資組合", mode="lines+markers",
                    line=dict(color="#00e5ff", width=2.5),
                    marker=dict(size=5),
                ))
                bench_styles = {
                    "SPY":  ("#c084fc", "S&P 500"),
                    "QQQ":  ("#00e676", "Nasdaq 100"),
                    "SOXX": ("#f8c471", "費城半導體"),
                }
                for sym, (color, label) in bench_styles.items():
                    if sym not in bench_trim.columns:
                        continue
                    s = bench_trim[sym].dropna()
                    if s.empty:
                        continue
                    fig_b.add_trace(go.Scatter(
                        x=s.index, y=s / float(s.iloc[0]) * 100,
                        name=label, mode="lines",
                        line=dict(color=color, width=1.5, dash="dot"),
                    ))
                fig_b.update_layout(
                    margin=dict(t=20, b=10, l=0, r=0),
                    height=250,
                    paper_bgcolor="#0a0e1a",
                    plot_bgcolor="#0a0e1a",
                    legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center",
                                font=dict(size=11, color="#94a3b8"), bgcolor="rgba(0,0,0,0)"),
                    xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#64748b"),
                               tickformat="%m/%d", rangebreaks=[dict(bounds=["sat", "mon"])],
                               linecolor="rgba(255,255,255,0.08)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)",
                               tickfont=dict(size=10, color="#64748b"), ticksuffix=""),
                    hovermode="x unified",
                    annotations=[dict(
                        text="基準 = 100（從第一筆歷史記錄起算）",
                        x=0, y=1.06, xref="paper", yref="paper",
                        font=dict(size=10, color="#4b5563"), showarrow=False,
                    )],
                )
                st.plotly_chart(fig_b, use_container_width=True)
        else:
            st.caption("歷史記錄不足兩筆，無法繪製走勢對照圖。")


    # ── 股東權益 ────────────────────────────────────
    dad_val = total_assets4 * 0.40
    mom_val = total_assets4 * 0.40
    bro_val = total_assets4 * 0.20
    dad_cost, mom_cost, bro_cost = 10000, 10000, 5000

    def _pnl_color(val, cost):
        return "#27ae60" if val >= cost else "#e74c3c"

    def _pnl_str(val, cost):
        diff = val - cost
        sign = "+" if diff >= 0 else ""
        return f'{sign}${abs(diff):,.0f}'

    sh_html = (
        '<div style="font-size:14px;font-weight:600;margin:10px 0 10px;color:#94a3b8;letter-spacing:0.5px">👥 股東權益</div>'
        '<div style="display:flex;gap:10px;">'
        '<div style="flex:1;background:linear-gradient(160deg,#0d1f3c,#0a2a4a);border:1px solid rgba(0,229,255,0.2);border-radius:14px;padding:14px 8px;text-align:center;">'
        '<div style="font-size:32px">👨</div>'
        '<div style="font-size:14px;font-weight:700;margin-top:4px;color:#e2e8f0">爸爸</div>'
        '<div style="font-size:12px;color:#64748b">40%</div>'
        f'<div style="font-size:15px;font-weight:700;color:#00e5ff;margin-top:6px">${dad_val:,.0f}</div>'
        f'<div style="font-size:11px;color:{_pnl_color(dad_val,dad_cost)};margin-top:3px">{_pnl_str(dad_val,dad_cost)}</div>'
        f'<div style="font-size:10px;color:#475569;margin-top:1px">成本 ${dad_cost:,}</div>'
        '</div>'
        '<div style="flex:1;background:linear-gradient(160deg,#1f0d2a,#2a0a3a);border:1px solid rgba(200,100,255,0.2);border-radius:14px;padding:14px 8px;text-align:center;">'
        '<div style="font-size:32px">👩</div>'
        '<div style="font-size:14px;font-weight:700;margin-top:4px;color:#e2e8f0">媽媽</div>'
        '<div style="font-size:12px;color:#64748b">40%</div>'
        f'<div style="font-size:15px;font-weight:700;color:#c084fc;margin-top:6px">${mom_val:,.0f}</div>'
        f'<div style="font-size:11px;color:{_pnl_color(mom_val,mom_cost)};margin-top:3px">{_pnl_str(mom_val,mom_cost)}</div>'
        f'<div style="font-size:10px;color:#475569;margin-top:1px">成本 ${mom_cost:,}</div>'
        '</div>'
        '<div style="flex:1;background:linear-gradient(160deg,#0d2a1a,#0a3a1f);border:1px solid rgba(0,230,118,0.2);border-radius:14px;padding:14px 8px;text-align:center;">'
        '<div style="font-size:32px">👦</div>'
        '<div style="font-size:14px;font-weight:700;margin-top:4px;color:#e2e8f0">哥哥</div>'
        '<div style="font-size:12px;color:#64748b">20%</div>'
        f'<div style="font-size:15px;font-weight:700;color:#00e676;margin-top:6px">${bro_val:,.0f}</div>'
        f'<div style="font-size:11px;color:{_pnl_color(bro_val,bro_cost)};margin-top:3px">{_pnl_str(bro_val,bro_cost)}</div>'
        f'<div style="font-size:10px;color:#475569;margin-top:1px">成本 ${bro_cost:,}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(sh_html, unsafe_allow_html=True)
