import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, date
import os

st.set_page_config(
    page_title="美股績效追蹤",
    page_icon="📈",
    layout="centered",
)

# 手機友善 CSS
st.markdown("""
<style>
    .block-container { padding: 3rem 1rem 3rem; }
    header[data-testid="stHeader"] { display: none; }
    [data-testid="metric-container"] {
        background: #f7f7f9;
        border-radius: 10px;
        padding: 8px 12px;
    }
    [data-testid="metric-container"] label { font-size: 13px !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 18px !important; }
    [data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 12px !important; }
    @media (prefers-color-scheme: dark) {
        [data-testid="metric-container"] { background: #1e1e2e; }
    }
    .pnl-pos { color: #00c853; font-weight: bold; }
    .pnl-neg { color: #ff1744; font-weight: bold; }
    h1 { font-size: 24px !important; margin-bottom: 0 !important; }
    .summary-box {
        background: linear-gradient(135deg, #1a237e, #283593);
        color: white;
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 12px;
        font-size: 13px;
    }
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


def load_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame(columns=["date", "portfolio", "cash", "total"])
    return pd.read_csv(HISTORY_FILE, parse_dates=["date"])


def append_history(portfolio_val: float, cash_val: float):
    try:
        today = date.today().isoformat()
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
        df.to_csv(HISTORY_FILE, index=False)
    except Exception:
        pass


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
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.title("📈 美股績效追蹤")
    st.caption(f"更新時間：{datetime.now().strftime('%m/%d %H:%M')}")
with col_refresh:
    if st.button("🔄", help="重新載入", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── 計算股票總市值（各 tab 共用）─────────────────────
portfolio_value = sum(
    prices[r["ticker"]]["price"] * float(r["shares"])
    for _, r in portfolio.iterrows() if r["ticker"] in prices
)
append_history(portfolio_value, cash)

# ── Tab ──────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["💼 我的持倉", "👀 追蹤清單", "📊 總資產"])

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
        chg_hex = "#27ae60" if change >= 0 else "#e74c3c"
        day_hex = "#27ae60" if daily_pnl >= 0 else "#e74c3c"
        tot_hex = "#27ae60" if total_pnl >= 0 else "#e74c3c"

        cards_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 2px;border-bottom:1px solid #e8e8e8;gap:4px;">'
            f'<div style="flex:1">'
            f'<div style="font-size:15px;font-weight:700">{ticker}</div>'
            f'<div style="font-size:22px;font-weight:700">${price:.2f}</div>'
            f'<div style="font-size:13px;color:{chg_hex};font-weight:600">{sign}{change:.2f} ({sign}{pct:.2f}%)</div>'
            f'</div>'
            f'<div style="flex:1;text-align:center;font-size:13px;color:#555;line-height:2">'
            f'<div>持股 {shares:g} 股</div>'
            f'<div style="color:{day_hex};font-weight:600">Today {d_sign}${abs(daily_pnl):,.0f}</div>'
            f'</div>'
            f'<div style="flex:1;text-align:right;font-size:13px;color:#555;line-height:2">'
            f'<div>每股成本 ${cost:.2f}</div>'
            f'<div style="color:{tot_hex};font-weight:600">總損益 {t_sign}${abs(total_pnl):,.0f}</div>'
            f'<div style="font-size:12px;color:{tot_hex}">{t_sign}{total_pnl_pct:.1f}%</div>'
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
            wl_items += f'<div style="background:#f7f7f9;border-radius:10px;padding:10px 12px;"><div style="font-size:13px;font-weight:700">{ticker}</div><div style="font-size:11px;color:#aaa">—</div></div>'
            continue
        p = prices[ticker]
        price = p["price"]
        change = p["change"]
        pct = p["pct"]
        sign = "+" if pct >= 0 else ""
        # 背景深淺：abs(pct) 0%=淡, 5%+=最深，上限 alpha=0.35
        intensity = min(abs(pct) / 5.0, 1.0) * 0.35
        if pct >= 0:
            bg = f"rgba(39,174,96,{intensity:.2f})"
            chg_hex = "#1a7a43"
        else:
            bg = f"rgba(231,76,60,{intensity:.2f})"
            chg_hex = "#a93226"
        wl_items += (
            f'<div style="background:{bg};border-radius:10px;padding:10px 12px;">'
            f'<div style="font-size:13px;font-weight:700">{ticker}</div>'
            f'<div style="font-size:18px;font-weight:700">${price:.2f}</div>'
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
        <div style="font-size:11px;opacity:0.8">總資產</div>
        <div style="font-size:26px;font-weight:bold">${total_assets:,.0f}</div>
    </div>
    <div style="display:flex;gap:10px;margin-bottom:14px;">
      <div style="flex:1;background:#f0f4ff;border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:#555">股票市值</div>
        <div style="font-size:17px;font-weight:700">${portfolio_value:,.0f}</div>
      </div>
      <div style="flex:1;background:#f0fff4;border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:#555">現金水位</div>
        <div style="font-size:17px;font-weight:700">${cash:,.2f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 更新現金（本機才顯示）
    if not IS_CLOUD:
        with st.expander("✏️ 更新現金水位"):
            new_cash = st.number_input("現金（USD）", value=cash, min_value=0.0, step=100.0, format="%.2f")
            if st.button("💾 儲存現金", use_container_width=True):
                save_cash(new_cash)
                st.success("已儲存！")
                st.rerun()

    # 歷史折線圖
    st.markdown("**總資產變化**")
    hist = load_history()
    if len(hist) >= 2:
        hist = hist.sort_values("date")
        st.line_chart(hist.set_index("date")[["total", "portfolio", "cash"]])
    elif len(hist) == 1:
        st.caption("資料只有一天，明天會開始顯示折線圖。")
    else:
        st.caption("尚無歷史資料。")

    # 歷史明細
    with st.expander("📋 歷史明細"):
        if not hist.empty:
            hist_display = hist.sort_values("date", ascending=False).copy()
            hist_display["date"] = hist_display["date"].astype(str)
            st.dataframe(hist_display, use_container_width=True, hide_index=True)
        else:
            st.caption("尚無資料")
