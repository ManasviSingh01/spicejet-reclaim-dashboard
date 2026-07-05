cd ~/Desktop/spicereclaim_app
nano app.pycd ~/Desktop/spicereclaim_app
nano app.py"""
SpiceJet Reclaim Program - Streamlit Dashboard
Upload passenger data -> auto tier -> auto generate vouchers + messages
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta

st.set_page_config(
    page_title="SpiceJet Reclaim Dashboard",
    page_icon="✈️",
    layout="wide",
)

# ────────────────────────────────────────────────────────────────────────────
# STYLING
# ────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.main-header {font-size: 28px; font-weight: 800; color: #e63946; margin-bottom: 0;}
.sub-header {font-size: 13px; color: #888; margin-top: 0;}
.tier-VH {background-color: #fee2e2; color: #991b1b; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 12px;}
.tier-H {background-color: #fef3c7; color: #92400e; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 12px;}
.tier-M {background-color: #dbeafe; color: #1e40af; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 12px;}
.tier-L {background-color: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 12px;}
.voucher-box {
    background: linear-gradient(135deg, #e63946 0%, #c62e3b 100%);
    border-radius: 12px; padding: 18px 22px; color: white; margin-bottom: 10px;
}
.voucher-code {font-size: 20px; font-weight: 800; letter-spacing: 3px; font-family: monospace;}
.msg-box {background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:14px; font-size:13px; line-height:1.6; color:#14532d;}
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# TIER / SCORING LOGIC  (mirrors spicereclaim_v3.py thresholds: 0.05/0.15/0.30)
# ────────────────────────────────────────────────────────────────────────────
TIER_BINS = [0, 0.05, 0.15, 0.30, 1.0]
TIER_LABELS = ["Low", "Medium", "High", "Very High"]
SEND_TIME = {"Very High": "8:00 AM", "High": "9:00 AM", "Medium": "11:00 AM", "Low": "2:00 PM"}
TIER_SHORT = {"Very High": "VH", "High": "H", "Medium": "M", "Low": "L"}


def compute_score(row):
    """Rule-based propensity score (stand-in for the trained XGBoost model).
    If you have the trained model.pkl from spicereclaim_v3.py, swap this
    function for model.predict_proba() — see USE_TRAINED_MODEL section below.
    """
    lf = row.get("load_factor", 0.75)
    dbd = row.get("dbd", 10)
    fare = max(row.get("current_fare", 3000), 1)
    voucher = row.get("voucher_amt", 500)
    pclass = str(row.get("product_class", "E")).upper()

    score = 0.0

    # load factor — lower load factor = higher acceptance (matches model finding: <60% LF -> 2.50%)
    if lf < 0.60:
        score += 0.35
    elif lf < 0.75:
        score += 0.25
    elif lf < 0.85:
        score += 0.15
    elif lf < 0.95:
        score += 0.08
    else:
        score += 0.03

    # dbd — best window 8-14 days (matches model finding: 1.60%)
    if 8 <= dbd <= 14:
        score += 0.30
    elif 3 <= dbd <= 7:
        score += 0.20
    elif 15 <= dbd <= 30:
        score += 0.15
    else:
        score += 0.05

    # voucher to fare ratio
    vr = voucher / fare
    if vr > 0.35:
        score += 0.20
    elif vr > 0.20:
        score += 0.12
    else:
        score += 0.05

    # class
    if pclass == "B":
        score += 0.10
    elif pclass == "S":
        score += 0.05

    score += random.uniform(-0.02, 0.02)
    return float(np.clip(score, 0, 1))


def tier_from_score(score):
    idx = np.digitize([score], TIER_BINS)[0] - 1
    idx = max(0, min(idx, len(TIER_LABELS) - 1))
    return TIER_LABELS[idx]


def gen_voucher_code(tier):
    prefix = {"Very High": "SJ-VH", "High": "SJ-HI", "Medium": "SJ-MD", "Low": "SJ-LW"}[tier]
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{prefix}-{rand}"


def generate_messages(row):
    fname = str(row["name"]).split(" ")[0]
    route = f"{row['departure_city']} to {row['arrival_city']}"
    v = f"₹{int(row['voucher_amt']):,}"
    code = row["voucher_code"]
    flight = row["flight"]
    date = row["departure_date"]
    urgency = "This is a limited-time offer!" if row.get("dbd", 10) <= 5 else "Offer valid for 48 hours only."

    whatsapp = (
        f"✈️ *SpiceJet Special Offer for {fname}!*\n\n"
        f"Your flight *{flight}* ({route}) on *{date}* has a voluntary delay offer.\n\n"
        f"💰 *Voucher Value: {v}*\n🎟 Code: `{code}`\n\n"
        f"Accept now and travel on the next available flight with a {v} SpiceJet voucher.\n\n"
        f"{urgency}\n\n"
        f"✅ To accept, reply *YES* or visit spicejet.com/reclaim\n"
        f"❌ To decline, reply *NO*\n\n_SpiceJet Revenue Optimisation Team_"
    )
    sms = (
        f"SpiceJet: Hi {fname}, your flight {flight} ({date}) has a special voucher "
        f"offer of {v}! Code: {code}. Reply YES to accept or visit spicejet.com/reclaim. "
        f"Offer expires in 48hrs. Opt-out: STOP"
    )
    subject = f"Special Offer: {v} Travel Voucher for Your {date} Flight"
    email = (
        f"Dear {fname},\n\nThank you for choosing SpiceJet for your journey from {route} "
        f"on {date} (Flight: {flight}).\n\nWe have a special offer for you today:\n\n"
        f"🎫 Voluntary Delay Voucher: {v}\n📋 Voucher Code: {code}\n\n"
        f"By accepting this offer, you agree to take the next available SpiceJet flight "
        f"to {row['arrival_city']} and receive a {v} credit valid for 30 days on any "
        f"SpiceJet booking.\n\nTo accept: Visit spicejet.com/reclaim and enter code {code}\n"
        f"Or call: 1800-180-3333\n\n{urgency}\n\nWarm regards,\nRevenue Optimisation Team\nSpiceJet Limited"
    )
    call_script = (
        f"Hello, may I speak with {fname}? ... Hi {fname}, this is [Agent Name] calling from "
        f"SpiceJet. I'm reaching out regarding your flight {flight} from {row['departure_city']} "
        f"to {row['arrival_city']} on {date}. We have a special voluntary delay offer for you "
        f"today — a {v} SpiceJet voucher, code {code}. Would you be open to considering this offer? "
        f"... [If yes] Great! I'll note your acceptance. You'll receive confirmation on your "
        f"registered number. ... [If no] No problem at all, {fname}. We appreciate your time."
    )
    return {"whatsapp": whatsapp, "sms": sms, "email": email, "subject": subject, "call": call_script}


OPTIONAL_DEFAULTS = {
    "email": "", "flight": "SG 000", "departure_city": "DEL", "arrival_city": "BOM",
    "departure_date": "2026-03-20", "current_fare": 3000, "voucher_amt": 800,
    "load_factor": 0.75, "dbd": 10, "product_class": "E",
}


def normalize_columns(df):
    """Map actual SpiceJet file column names + common variants to internal names."""
    rename_map = {}
    cols_lower = {c.lower().strip(): c for c in df.columns}
    aliases = {
        "name":            ["full_name", "name", "passenger_name", "passenger"],
        "phone":           ["phone", "mobile", "contact", "phone_number"],
        "email":           ["email", "email_id", "mail"],
        "flight":          ["flight_number", "flight", "flight_no"],
        "departure_city":  ["departure_city", "from", "origin", "dep_city"],
        "arrival_city":    ["arrival_city", "to", "destination", "arr_city"],
        "departure_date":  ["departure_date", "date", "travel_date"],
        "current_fare":    ["current_fare", "fare", "ticket_fare"],
        "voucher_amt":     ["voucher_amt_num", "voucher_amt", "voucher_amount", "voucher"],
        "load_factor":     ["load_factor", "lf"],
        "dbd":             ["dbd", "days_before_departure"],
        "product_class":   ["product_class", "rbd_clean", "class", "cabin_class"],
        # pre-scored columns from XGBoost model
        "score":           ["acceptance_score", "score", "propensity_score"],
        "tier":            ["propensity_tier", "tier"],
    }
    for canon, opts in aliases.items():
        for o in opts:
            if o in cols_lower:
                rename_map[cols_lower[o]] = canon
                break
    return df.rename(columns=rename_map)


def score_dataframe(df):
    df = normalize_columns(df.copy())

    # Fill missing optional cols with defaults
    for col, default in OPTIONAL_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)

    if "name" not in df.columns:
        df["name"] = [f"Passenger {i+1}" for i in range(len(df))]
    if "phone" not in df.columns:
        df["phone"] = ""

    df["current_fare"] = pd.to_numeric(df["current_fare"], errors="coerce").fillna(3000)
    df["voucher_amt"]  = pd.to_numeric(df["voucher_amt"],  errors="coerce").fillna(800)
    df["load_factor"]  = pd.to_numeric(df["load_factor"],  errors="coerce").fillna(0.75)
    df["dbd"]          = pd.to_numeric(df["dbd"],          errors="coerce").fillna(10)

    # ── Use pre-scored columns if file already has them (XGBoost output) ──
    has_score = "score" in df.columns and df["score"].notna().any()
    has_tier  = "tier"  in df.columns and df["tier"].notna().any()

    if has_score:
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df = df[df["score"].notna()].copy()
    else:
        df["score"] = df.apply(compute_score, axis=1)

    if has_tier:
        df["tier"] = df["tier"].fillna("Low")
    else:
        df["tier"] = df["score"].apply(tier_from_score)

    df["voucher_code"] = df["tier"].apply(gen_voucher_code)
    df["send_time"]    = df["tier"].map(SEND_TIME)
    return df


def sample_data():
    rows = [
        ("Priya Mehta", "9811001001", "priya@gmail.com", "SG 101", "Delhi", "Mumbai", "2026-03-15", 5200, 2000, 0.52, 12, "E"),
        ("Amit Verma", "9822002002", "amit@yahoo.com", "SG 102", "Mumbai", "Bangalore", "2026-03-16", 4800, 1800, 0.88, 5, "B"),
        ("Sunita Rao", "9833003003", "sunita@hotmail.com", "SG 201", "Bangalore", "Chennai", "2026-03-17", 3200, 900, 0.62, 10, "E"),
        ("Rohit Kumar", "9844004004", "rohit@gmail.com", "SG 301", "Chennai", "Hyderabad", "2026-03-18", 2900, 700, 0.91, 3, "E"),
        ("Kavya Singh", "9855005005", "kavya@gmail.com", "SG 401", "Delhi", "Kolkata", "2026-03-15", 6100, 2500, 0.48, 11, "B"),
        ("Rajan Nair", "9866006006", "rajan@gmail.com", "SG 501", "Kochi", "Delhi", "2026-03-19", 4500, 1400, 0.73, 8, "S"),
        ("Deepa Sharma", "9877007007", "deepa@outlook.com", "SG 101", "Delhi", "Mumbai", "2026-03-15", 5000, 1100, 0.82, 6, "E"),
        ("Vikram Joshi", "9888008008", "vikram@gmail.com", "SG 601", "Pune", "Goa", "2026-03-20", 3800, 1600, 0.55, 14, "E"),
        ("Ananya Iyer", "9899009009", "ananya@gmail.com", "SG 201", "Bangalore", "Chennai", "2026-03-17", 2800, 600, 0.95, 2, "E"),
        ("Suresh Pillai", "9810010010", "suresh@gmail.com", "SG 701", "Hyderabad", "Mumbai", "2026-03-21", 5500, 2200, 0.44, 13, "B"),
    ]
    cols = ["name", "phone", "email", "flight", "departure_city", "arrival_city",
            "departure_date", "current_fare", "voucher_amt", "load_factor", "dbd", "product_class"]
    return pd.DataFrame(rows, columns=cols)


# ────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ────────────────────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = None

# ────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAV
# ────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown('<p class="main-header">SpiceJet</p>', unsafe_allow_html=True)
st.sidebar.markdown('<p class="sub-header">Reclaim Dashboard</p>', unsafe_allow_html=True)
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Upload Data", "Overview", "Passengers", "Vouchers", "Messages", "Send Schedule", "Add Passenger"],
    label_visibility="collapsed",
)

if st.session_state.df is not None:
    st.sidebar.markdown("---")
    st.sidebar.metric("Passengers loaded", len(st.session_state.df))

# ────────────────────────────────────────────────────────────────────────────
# PAGE: UPLOAD DATA
# ────────────────────────────────────────────────────────────────────────────
if page == "Upload Data":
    st.title("📤 Upload passenger data")
    st.caption("Upload an Excel/CSV with passenger details. Columns are auto-detected (name, phone, flight, fare, voucher_amt, load_factor, dbd, etc).")

    uploaded = st.file_uploader("Drop your file here", type=["xlsx", "xls", "csv"])

    col1, col2 = st.columns([1, 1])
    with col1:
        if uploaded is not None:
            if uploaded.name.endswith(".csv"):
                raw = pd.read_csv(uploaded)
            else:
                raw = pd.read_excel(uploaded)
            st.session_state.df = score_dataframe(raw)
            st.success(f"✅ {len(st.session_state.df)} passengers loaded and scored!")
    with col2:
        if st.button("🧪 Load sample data (10 rows)"):
            st.session_state.df = score_dataframe(sample_data())
            st.success("✅ Sample data loaded and scored!")

    st.markdown("---")
    st.subheader("Column mapping guide")
    guide = pd.DataFrame({
        "Column": ["name", "phone", "email", "flight", "departure_city", "arrival_city",
                   "departure_date", "current_fare", "voucher_amt", "load_factor", "dbd", "product_class"],
        "Description": ["Passenger full name", "Mobile number", "Email address", "Flight number",
                        "From city", "To city", "Travel date", "Ticket fare (₹)", "Voucher offer amount (₹)",
                        "Flight load (0-1)", "Days before departure", "Class (E/B/S)"],
        "Example": ["Rahul Sharma", "9876543210", "rahul@example.com", "SG 101", "Delhi", "Mumbai",
                    "2026-03-15", "4500", "1200", "0.87", "10", "E"],
    })
    st.dataframe(guide, use_container_width=True, hide_index=True)

    if st.session_state.df is not None:
        st.markdown("---")
        st.subheader("Preview")
        st.dataframe(st.session_state.df.head(10), use_container_width=True)

# ────────────────────────────────────────────────────────────────────────────
# PAGE: OVERVIEW
# ────────────────────────────────────────────────────────────────────────────
elif page == "Overview":
    st.title("📊 Overview")
    if st.session_state.df is None:
        st.info("👉 Upload data first from the 'Upload Data' page.")
    else:
        df = st.session_state.df
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total passengers", len(df))
        c2.metric("Very High tier", (df["tier"] == "Very High").sum(), "→ Send 8 AM")
        c3.metric("High tier", (df["tier"] == "High").sum(), "→ Send 9 AM")
        c4.metric("Avg voucher", f"₹{df['voucher_amt'].mean():,.0f}")

        st.markdown("---")
        st.subheader("Propensity tier breakdown")
        tier_counts = df["tier"].value_counts().reindex(TIER_LABELS[::-1]).fillna(0).astype(int)
        cols = st.columns(4)
        for i, tier in enumerate(["Very High", "High", "Medium", "Low"]):
            with cols[i]:
                cnt = int(tier_counts.get(tier, 0))
                pct = (cnt / len(df) * 100) if len(df) else 0
                st.markdown(f"""
                <div style="border-radius:10px;padding:16px;border:1px solid #ddd;text-align:center;">
                    <div class="tier-{TIER_SHORT[tier]}">{tier.upper()}</div>
                    <div style="font-size:28px;font-weight:700;margin-top:8px;">{cnt}</div>
                    <div style="font-size:12px;color:#888;">{pct:.1f}% of total</div>
                    <div style="font-size:11px;color:#666;margin-top:6px;">Send at {SEND_TIME[tier]}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Load factor distribution")
            bins = pd.cut(df["load_factor"], bins=[0, 0.6, 0.75, 0.85, 0.95, 1.1],
                          labels=["<60%", "60-75%", "75-85%", "85-95%", ">95%"])
            st.bar_chart(bins.value_counts().sort_index())
        with col2:
            st.subheader("DBD window distribution")
            dbins = pd.cut(df["dbd"], bins=[0, 3, 7, 14, 30, 999],
                           labels=["0-3d", "4-7d", "8-14d", "15-30d", ">30d"])
            st.bar_chart(dbins.value_counts().sort_index())

        st.markdown("---")
        st.subheader("Tier-wise acceptance summary table")
        summary = df.groupby("tier", observed=True).agg(
            passengers=("score", "count"),
            avg_score=("score", "mean"),
            avg_voucher=("voucher_amt", "mean"),
        ).reindex(["Very High", "High", "Medium", "Low"]).dropna()
        summary["avg_score"] = (summary["avg_score"] * 100).round(1).astype(str) + "%"
        summary["avg_voucher"] = "₹" + summary["avg_voucher"].round(0).astype(int).astype(str)
        st.dataframe(summary, use_container_width=True)

# ────────────────────────────────────────────────────────────────────────────
# PAGE: PASSENGERS
# ────────────────────────────────────────────────────────────────────────────
elif page == "Passengers":
    st.title("👥 Passengers")
    if st.session_state.df is None:
        st.info("👉 Upload data first from the 'Upload Data' page.")
    else:
        df = st.session_state.df.copy()
        c1, c2, c3 = st.columns(3)
        tier_filter = c1.selectbox("Filter by tier", ["All"] + TIER_LABELS[::-1])
        flight_filter = c2.text_input("Filter by flight")
        search = c3.text_input("Search name / phone")

        filtered = df.copy()
        if tier_filter != "All":
            filtered = filtered[filtered["tier"] == tier_filter]
        if flight_filter:
            filtered = filtered[filtered["flight"].astype(str).str.contains(flight_filter, case=False)]
        if search:
            filtered = filtered[
                filtered["name"].astype(str).str.contains(search, case=False)
                | filtered["phone"].astype(str).str.contains(search, case=False)
            ]

        display_cols = ["name", "phone", "flight", "departure_city", "arrival_city",
                        "departure_date", "current_fare", "voucher_amt", "load_factor",
                        "dbd", "score", "tier", "voucher_code", "send_time"]
        st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export filtered as CSV", csv, "spicejet_reclaim_tiered.csv", "text/csv")

# ────────────────────────────────────────────────────────────────────────────
# PAGE: VOUCHERS
# ────────────────────────────────────────────────────────────────────────────
elif page == "Vouchers":
    st.title("🎫 Vouchers")
    if st.session_state.df is None:
        st.info("👉 Upload data first from the 'Upload Data' page.")
    else:
        df = st.session_state.df
        c1, c2 = st.columns([2, 1])
        tier_filter = c1.selectbox("Filter by tier", ["All"] + TIER_LABELS[::-1], key="vtier")
        if c2.button("🔄 Regenerate all voucher codes"):
            df["voucher_code"] = df["tier"].apply(gen_voucher_code)
            st.session_state.df = df
            st.success("Voucher codes regenerated!")

        view = df if tier_filter == "All" else df[df["tier"] == tier_filter]

        csv = view[["name", "phone", "email", "flight", "voucher_amt", "voucher_code", "tier"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export vouchers as CSV", csv, "spicejet_vouchers.csv", "text/csv")

        st.markdown("---")
        for _, row in view.head(50).iterrows():
            st.markdown(f"""
            <div class="voucher-box">
                <div style="font-size:11px;opacity:0.85;">{row['departure_city']} → {row['arrival_city']} · {row['flight']} · {row['departure_date']}</div>
                <div style="font-size:14px;font-weight:600;margin:6px 0;">{row['name']}</div>
                <div class="voucher-code">{row['voucher_code']}</div>
                <div style="font-size:11px;opacity:0.8;margin-top:6px;">Valid 30 days · SpiceJet Reclaim Offer · ₹{int(row['voucher_amt']):,}</div>
            </div>
            """, unsafe_allow_html=True)
        if len(view) > 50:
            st.caption(f"Showing 50 of {len(view)} vouchers. Export CSV for the full list.")

# ────────────────────────────────────────────────────────────────────────────
# PAGE: MESSAGES
# ────────────────────────────────────────────────────────────────────────────
elif page == "Messages":
    st.title("💬 Messages")
    if st.session_state.df is None:
        st.info("👉 Upload data first from the 'Upload Data' page.")
    else:
        df = st.session_state.df
        channel = st.radio("Channel", ["WhatsApp", "SMS", "Email", "Call Script"], horizontal=True)
        names = df["name"] + " · " + df["tier"] + " · " + df["flight"].astype(str)
        choice = st.selectbox("Select a passenger", names)
        idx = names[names == choice].index[0]
        row = df.loc[idx]
        msgs = generate_messages(row)

        st.markdown(f"**{row['name']}** · {row['phone']} · {row.get('email','') or 'no email'} · Tier: **{row['tier']}**")

        key_map = {"WhatsApp": "whatsapp", "SMS": "sms", "Email": "email", "Call Script": "call"}
        text = msgs[key_map[channel]]
        if channel == "Email":
            st.caption(f"Subject: {msgs['subject']}")
        st.markdown(f'<div class="msg-box">{text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        st.code(text, language=None)

        st.markdown("---")
        if st.button(f"📨 Send to ALL passengers via {channel} (simulated)"):
            st.success(f"✅ Simulated: {len(df)} messages queued via {channel}!")
            st.caption("Hook this up to a real WhatsApp Business API / Twilio / SMTP to actually send — see notes at bottom of this app's code.")

# ────────────────────────────────────────────────────────────────────────────
# PAGE: SEND SCHEDULE
# ────────────────────────────────────────────────────────────────────────────
elif page == "Send Schedule":
    st.title("⏰ Today's recommended send schedule")
    if st.session_state.df is None:
        st.info("👉 Upload data first from the 'Upload Data' page.")
    else:
        df = st.session_state.df
        schedule = [
            ("8:00 AM", "Very High tier", "Highest acceptance probability → Send first!", (df["tier"] == "Very High").sum()),
            ("9:00 AM", "High tier", "Good acceptance probability → Send second", (df["tier"] == "High").sum()),
            ("10:00 AM", "Avoid", "Lowest acceptance rate (0.69%)", None),
            ("11:00 AM", "Medium tier", "Moderate probability → Worth sending", (df["tier"] == "Medium").sum()),
            ("2:00 PM", "Low tier", "Low probability → Optional / skip", (df["tier"] == "Low").sum()),
        ]
        for time, label, desc, count in schedule:
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.markdown(f"### {time}")
            c2.markdown(f"**{label}**  \n<span style='color:#888;font-size:13px'>{desc}</span>", unsafe_allow_html=True)
            c3.markdown(f"**{count if count is not None else '—'}**" + (" passengers" if count is not None else ""))
            st.markdown("---")

        st.subheader("Best targeting windows (model findings)")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Best DBD window", "8-14 days", "1.60% acceptance")
            st.metric("Peak send hour", "8 AM", "Highest daily response")
        with c2:
            st.metric("Best load factor", "< 60%", "2.50% acceptance")
            st.metric("Model lift (VH vs baseline)", "up to 4x", "better acceptance")

# ────────────────────────────────────────────────────────────────────────────
# PAGE: ADD PASSENGER
# ────────────────────────────────────────────────────────────────────────────
elif page == "Add Passenger":
    st.title("➕ Add passenger manually")
    with st.form("manual_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name *")
        phone = c2.text_input("Phone *")
        email = c1.text_input("Email")
        flight = c2.text_input("Flight number", value="SG 101")
        dep = c1.text_input("Departure city", value="Delhi")
        arr = c2.text_input("Arrival city", value="Mumbai")
        date = c1.date_input("Departure date", value=datetime(2026, 3, 20))
        fare = c2.number_input("Current fare (₹)", value=4500, step=100)
        voucher = c1.number_input("Voucher amount (₹)", value=1200, step=100)
        lf = c2.number_input("Load factor (0-1)", value=0.75, min_value=0.0, max_value=1.5, step=0.01)
        dbd = c1.number_input("Days before departure", value=10, step=1)
        pclass = c2.selectbox("Product class", ["E", "B", "S"])
        submitted = st.form_submit_button("Add & score passenger")

    if submitted:
        if not name or not phone:
            st.error("Name and phone are required.")
        else:
            new_row = pd.DataFrame([{
                "name": name, "phone": phone, "email": email, "flight": flight,
                "departure_city": dep, "arrival_city": arr,
                "departure_date": date.strftime("%Y-%m-%d"),
                "current_fare": fare, "voucher_amt": voucher,
                "load_factor": lf, "dbd": dbd, "product_class": pclass,
            }])
            scored = score_dataframe(new_row)
            if st.session_state.df is None:
                st.session_state.df = scored
            else:
                st.session_state.df = pd.concat([st.session_state.df, scored], ignore_index=True)

            row = scored.iloc[0]
            st.success(f"✅ {row['name']} added — Tier: {row['tier']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Score", f"{row['score']*100:.1f}%")
            c2.metric("Tier", row["tier"])
            c3.metric("Voucher code", row["voucher_code"])

            msgs = generate_messages(row)
            st.markdown("**Preview WhatsApp message:**")
            st.markdown(f'<div class="msg-box">{msgs["whatsapp"].replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
