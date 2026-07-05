import streamlit as st
import pandas as pd
import numpy as np
import random
import string
from datetime import datetime

st.set_page_config(page_title="SpiceJet Reclaim Dashboard", page_icon="✈️", layout="wide")

st.markdown("""<style>
.voucher-box{background:linear-gradient(135deg,#e63946,#c62e3b);border-radius:12px;padding:18px 22px;color:white;margin-bottom:10px;}
.voucher-code{font-size:20px;font-weight:800;letter-spacing:3px;font-family:monospace;}
.msg-box{background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:14px;font-size:13px;line-height:1.6;color:#14532d;}
</style>""", unsafe_allow_html=True)

TIER_LABELS = ["Low", "Medium", "High", "Very High"]
SEND_TIME = {"Very High":"8:00 AM","High":"9:00 AM","Medium":"11:00 AM","Low":"2:00 PM"}
TIER_BINS = [0, 0.05, 0.15, 0.30, 1.0]

def compute_score(row):
    lf = row.get("load_factor", 0.75)
    dbd = row.get("dbd", 10)
    fare = max(row.get("current_fare", 3000), 1)
    voucher = row.get("voucher_amt", 500)
    pclass = str(row.get("product_class", "E")).upper()
    score = 0.0
    if lf < 0.60: score += 0.35
    elif lf < 0.75: score += 0.25
    elif lf < 0.85: score += 0.15
    elif lf < 0.95: score += 0.08
    else: score += 0.03
    if 8 <= dbd <= 14: score += 0.30
    elif 3 <= dbd <= 7: score += 0.20
    elif 15 <= dbd <= 30: score += 0.15
    else: score += 0.05
    vr = voucher / fare
    if vr > 0.35: score += 0.20
    elif vr > 0.20: score += 0.12
    else: score += 0.05
    if pclass == "B": score += 0.10
    elif pclass == "S": score += 0.05
    score += random.uniform(-0.02, 0.02)
    return float(np.clip(score, 0, 1))

def tier_from_score(score):
    idx = np.digitize([score], TIER_BINS)[0] - 1
    return TIER_LABELS[max(0, min(idx, len(TIER_LABELS)-1))]

def gen_voucher_code(tier):
    prefix = {"Very High":"SJ-VH","High":"SJ-HI","Medium":"SJ-MD","Low":"SJ-LW"}[tier]
    return prefix + "-" + "".join(random.choices(string.ascii_uppercase+string.digits, k=5))

def generate_messages(row):
    fname = str(row["name"]).split()[0]
    route = str(row["departure_city"]) + " to " + str(row["arrival_city"])
    v = "Rs." + str(int(row["voucher_amt"]))
    code = row["voucher_code"]
    flight = row["flight"]
    date = row["departure_date"]
    urgency = "Limited-time offer!" if row.get("dbd",10) <= 5 else "Offer valid 48 hours only."
    wa = "SpiceJet Offer for " + fname + "! Flight " + str(flight) + " (" + route + ") on " + str(date) + " has a voluntary delay offer. Voucher: " + v + ". Code: " + code + ". " + urgency + " Reply YES: spicejet.com/reclaim"
    sms = "SpiceJet: Hi " + fname + ", flight " + str(flight) + " has voucher " + v + "! Code:" + code + ". Reply YES. spicejet.com/reclaim. 48hr offer."
    subj = "SpiceJet Voucher " + v + " for your flight on " + str(date)
    eml = "Dear " + fname + ",\n\nThank you for choosing SpiceJet for " + route + " on " + str(date) + ".\n\nVoucher: " + v + "\nCode: " + code + "\n\nAccept at spicejet.com/reclaim or call 1800-180-3333.\n\n" + urgency + "\n\nWarm regards,\nSpiceJet Revenue Team"
    call = "Hello " + fname + ", this is SpiceJet calling about flight " + str(flight) + " from " + str(row["departure_city"]) + " to " + str(row["arrival_city"]) + " on " + str(date) + ". We have a " + v + " voucher offer, code " + code + ". Would you like to accept?"
    return {"whatsapp":wa,"sms":sms,"email":eml,"subject":subj,"call":call}

def normalize_and_score(df):
    df = df.copy()
    cl = {c.lower().strip():c for c in df.columns}
    aliases = {
        "name":["full_name","name","passenger_name"],
        "phone":["phone","mobile","contact"],
        "email":["email","email_id"],
        "flight":["flight_number","flight","flight_no"],
        "departure_city":["departure_city","from","origin"],
        "arrival_city":["arrival_city","to","destination"],
        "departure_date":["departure_date","date","travel_date"],
        "current_fare":["current_fare","fare"],
        "voucher_amt":["voucher_amt_num","voucher_amt","voucher_amount","voucher"],
        "load_factor":["load_factor","lf"],
        "dbd":["dbd","days_before_departure"],
        "product_class":["product_class","rbd_clean","class"],
        "score":["acceptance_score","score"],
        "tier":["propensity_tier","tier"],
    }
    rename = {}
    for canon, opts in aliases.items():
        for o in opts:
            if o in cl:
                rename[cl[o]] = canon
                break
    df = df.rename(columns=rename)
    defaults = {"email":"","flight":"SG000","departure_city":"DEL","arrival_city":"BOM",
                "departure_date":"2026-03-20","current_fare":3000,"voucher_amt":800,
                "load_factor":0.75,"dbd":10,"product_class":"E"}
    for col, val in defaults.items():
        if col not in df.columns: df[col] = val
        df[col] = df[col].fillna(val)
    if "name" not in df.columns: df["name"] = ["Passenger "+str(i+1) for i in range(len(df))]
    if "phone" not in df.columns: df["phone"] = ""
    for col in ["current_fare","voucher_amt","load_factor","dbd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(defaults[col])
    if "score" in df.columns and df["score"].notna().any():
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df = df[df["score"].notna()].copy()
    else:
        df["score"] = df.apply(compute_score, axis=1)
    if "tier" in df.columns and df["tier"].notna().any():
        df["tier"] = df["tier"].fillna("Low")
    else:
        df["tier"] = df["score"].apply(tier_from_score)
    df["voucher_code"] = df["tier"].apply(gen_voucher_code)
    df["send_time"] = df["tier"].map(SEND_TIME)
    return df

def sample_data():
    rows = [
        ("Priya Mehta","9811001001","priya@gmail.com","SG 101","Delhi","Mumbai","2026-03-15",5200,2000,0.52,12,"E",0.82,"Very High"),
        ("Amit Verma","9822002002","amit@yahoo.com","SG 102","Mumbai","Bangalore","2026-03-16",4800,1800,0.88,5,"B",0.31,"High"),
        ("Sunita Rao","9833003003","sunita@gmail.com","SG 201","Bangalore","Chennai","2026-03-17",3200,900,0.62,10,"E",0.18,"Medium"),
        ("Rohit Kumar","9844004004","rohit@gmail.com","SG 301","Chennai","Hyderabad","2026-03-18",2900,700,0.91,3,"E",0.03,"Low"),
        ("Kavya Singh","9855005005","kavya@gmail.com","SG 401","Delhi","Kolkata","2026-03-15",6100,2500,0.48,11,"B",0.91,"Very High"),
        ("Rajan Nair","9866006006","rajan@gmail.com","SG 501","Kochi","Delhi","2026-03-19",4500,1400,0.73,8,"S",0.44,"High"),
        ("Deepa Sharma","9877007007","deepa@gmail.com","SG 101","Delhi","Mumbai","2026-03-15",5000,1100,0.82,6,"E",0.12,"Medium"),
        ("Vikram Joshi","9888008008","vikram@gmail.com","SG 601","Pune","Goa","2026-03-20",3800,1600,0.55,14,"E",0.78,"Very High"),
        ("Ananya Iyer","9899009009","ananya@gmail.com","SG 201","Bangalore","Chennai","2026-03-17",2800,600,0.95,2,"E",0.01,"Low"),
        ("Suresh Pillai","9810010010","suresh@gmail.com","SG 701","Hyderabad","Mumbai","2026-03-21",5500,2200,0.44,13,"B",0.88,"Very High"),
    ]
    cols = ["name","phone","email","flight","departure_city","arrival_city","departure_date","current_fare","voucher_amt","load_factor","dbd","product_class","score","tier"]
    return pd.DataFrame(rows, columns=cols)

if "df" not in st.session_state:
    st.session_state.df = None

st.sidebar.markdown("## SpiceJet Reclaim")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigate", ["Upload Data","Overview","Passengers","Vouchers","Messages","Send Schedule","Add Passenger"], label_visibility="collapsed")
if st.session_state.df is not None:
    st.sidebar.markdown("---")
    st.sidebar.metric("Loaded", len(st.session_state.df))

if page == "Upload Data":
    st.title("Upload Passenger Data")
    uploaded = st.file_uploader("Drop Excel or CSV", type=["xlsx","xls","csv"])
    if uploaded:
        raw = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        st.session_state.df = normalize_and_score(raw)
        st.success("Loaded " + str(len(st.session_state.df)) + " passengers!")
    if st.button("Load sample data"):
        st.session_state.df = normalize_and_score(sample_data())
        st.success("Sample data loaded!")
    if st.session_state.df is not None:
        st.dataframe(st.session_state.df.head(5), use_container_width=True)

elif page == "Overview":
    st.title("Overview")
    if st.session_state.df is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.df
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Very High", int((df["tier"]=="Very High").sum()), "8 AM")
        c3.metric("High", int((df["tier"]=="High").sum()), "9 AM")
        c4.metric("Avg Voucher", "Rs."+str(int(df["voucher_amt"].mean())))
        st.markdown("---")
        cols = st.columns(4)
        for i,t in enumerate(["Very High","High","Medium","Low"]):
            cnt = int((df["tier"]==t).sum())
            pct = round(cnt/len(df)*100,1)
            with cols[i]:
                st.markdown("<div style=\"text-align:center;border:1px solid #ddd;border-radius:10px;padding:16px\"><b>"+t+"</b><div style=\"font-size:28px;font-weight:700\">"+str(cnt)+"</div><div style=\"color:#888;font-size:12px\">"+str(pct)+"%</div><div style=\"font-size:11px\">"+SEND_TIME[t]+"</div></div>", unsafe_allow_html=True)
        st.markdown("---")
        c1,c2 = st.columns(2)
        with c1:
            st.subheader("Load Factor")
            bins = pd.cut(df["load_factor"],[0,0.6,0.75,0.85,0.95,2],labels=["<60%","60-75%","75-85%","85-95%",">95%"])
            st.bar_chart(bins.value_counts().sort_index())
        with c2:
            st.subheader("DBD Distribution")
            dbins = pd.cut(df["dbd"],[0,3,7,14,30,999],labels=["0-3d","4-7d","8-14d","15-30d",">30d"])
            st.bar_chart(dbins.value_counts().sort_index())

elif page == "Passengers":
    st.title("Passengers")
    if st.session_state.df is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.df.copy()
        c1,c2,c3 = st.columns(3)
        tf = c1.selectbox("Tier", ["All"]+TIER_LABELS[::-1])
        ff = c2.text_input("Flight")
        sf = c3.text_input("Search")
        if tf != "All": df = df[df["tier"]==tf]
        if ff: df = df[df["flight"].astype(str).str.contains(ff, case=False)]
        if sf: df = df[df["name"].astype(str).str.contains(sf, case=False)|df["phone"].astype(str).str.contains(sf)]
        show = [c for c in ["name","phone","flight","departure_city","arrival_city","departure_date","current_fare","voucher_amt","load_factor","dbd","score","tier","voucher_code","send_time"] if c in df.columns]
        st.dataframe(df[show], use_container_width=True, hide_index=True)
        st.download_button("Export CSV", df.to_csv(index=False).encode(), "passengers.csv","text/csv")

elif page == "Vouchers":
    st.title("Vouchers")
    if st.session_state.df is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.df
        c1,c2 = st.columns([2,1])
        tf = c1.selectbox("Tier", ["All"]+TIER_LABELS[::-1], key="vt")
        if c2.button("Regenerate codes"):
            st.session_state.df["voucher_code"] = st.session_state.df["tier"].apply(gen_voucher_code)
            df = st.session_state.df
            st.success("Done!")
        view = df if tf=="All" else df[df["tier"]==tf]
        exp_cols = [c for c in ["name","phone","email","flight","voucher_amt","voucher_code","tier"] if c in view.columns]
        st.download_button("Export vouchers CSV", view[exp_cols].to_csv(index=False).encode(), "vouchers.csv","text/csv")
        st.markdown("---")
        for _,row in view.head(30).iterrows():
            dep = str(row["departure_city"]); arr = str(row["arrival_city"])
            fl = str(row["flight"]); dt = str(row["departure_date"])
            nm = str(row["name"]); vc = str(row["voucher_code"]); va = str(int(row["voucher_amt"]))
            st.markdown("<div class=\"voucher-box\"><div style=\"font-size:11px;opacity:.85\">"+dep+" to "+arr+" · "+fl+" · "+dt+"</div><div style=\"font-size:14px;font-weight:600;margin:6px 0\">"+nm+"</div><div class=\"voucher-code\">"+vc+"</div><div style=\"font-size:11px;opacity:.8;margin-top:6px\">Valid 30 days · Rs."+va+"</div></div>", unsafe_allow_html=True)

elif page == "Messages":
    st.title("Messages")
    if st.session_state.df is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.df
        channel = st.radio("Channel", ["WhatsApp","SMS","Email","Call Script"], horizontal=True)
        names = df["name"].astype(str)+" · "+df["tier"].astype(str)+" · "+df["flight"].astype(str)
        choice = st.selectbox("Passenger", names)
        idx = names[names==choice].index[0]
        row = df.loc[idx]
        msgs = generate_messages(row)
        st.markdown("**"+str(row["name"])+"** · "+str(row.get("phone",""))+" · Tier: **"+str(row["tier"])+"**")
        key_map = {"WhatsApp":"whatsapp","SMS":"sms","Email":"email","Call Script":"call"}
        text = msgs[key_map[channel]]
        if channel=="Email": st.caption("Subject: "+msgs["subject"])
        st.code(text, language=None)
        if st.button("Simulate send to ALL via "+channel):
            st.success("Simulated: "+str(len(df))+" messages queued!")

elif page == "Send Schedule":
    st.title("Send Schedule")
    if st.session_state.df is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.df
        for time, label, desc, cnt in [
            ("8:00 AM","Very High tier","Highest acceptance - Send first!",(df["tier"]=="Very High").sum()),
            ("9:00 AM","High tier","Good acceptance - Send second",(df["tier"]=="High").sum()),
            ("10:00 AM","AVOID","Lowest acceptance rate 0.69%",None),
            ("11:00 AM","Medium tier","Moderate acceptance",(df["tier"]=="Medium").sum()),
            ("2:00 PM","Low tier","Low - Optional",(df["tier"]=="Low").sum()),
        ]:
            c1,c2,c3 = st.columns([1,4,1])
            c1.markdown("### "+time)
            c2.markdown("**"+label+"**  \n"+desc)
            c3.markdown("**"+str(cnt if cnt is not None else "-")+"**")
            st.markdown("---")
        c1,c2 = st.columns(2)
        c1.metric("Best DBD","8-14 days","1.60% acceptance")
        c1.metric("Peak hour","8 AM","Highest response")
        c2.metric("Best load factor","< 60%","2.50% acceptance")
        c2.metric("Model lift","up to 4x","vs baseline")

elif page == "Add Passenger":
    st.title("Add Passenger")
    with st.form("mf"):
        c1,c2 = st.columns(2)
        name=c1.text_input("Full name"); phone=c2.text_input("Phone")
        email=c1.text_input("Email"); flight=c2.text_input("Flight",value="SG 101")
        dep=c1.text_input("From",value="Delhi"); arr=c2.text_input("To",value="Mumbai")
        date=c1.date_input("Date",value=datetime(2026,3,20))
        fare=c2.number_input("Fare",value=4500,step=100)
        voucher=c1.number_input("Voucher",value=1200,step=100)
        lf=c2.number_input("Load factor",value=0.75,min_value=0.0,max_value=1.5,step=0.01)
        dbd=c1.number_input("DBD",value=10,step=1)
        pclass=c2.selectbox("Class",["E","B","S"])
        sub=st.form_submit_button("Add and Score")
    if sub:
        if not name or not phone:
            st.error("Name and phone required.")
        else:
            nr = pd.DataFrame([{"name":name,"phone":phone,"email":email,"flight":flight,"departure_city":dep,"arrival_city":arr,"departure_date":date.strftime("%Y-%m-%d"),"current_fare":fare,"voucher_amt":voucher,"load_factor":lf,"dbd":dbd,"product_class":pclass}])
            scored = normalize_and_score(nr)
            st.session_state.df = scored if st.session_state.df is None else pd.concat([st.session_state.df,scored],ignore_index=True)
            r = scored.iloc[0]
            st.success("Added: "+str(r["name"])+" - Tier: "+str(r["tier"]))
            c1,c2,c3 = st.columns(3)
            c1.metric("Score",str(round(r["score"]*100,1))+"%")
            c2.metric("Tier",r["tier"])
            c3.metric("Code",r["voucher_code"])
            st.code(msgs["whatsapp"] if "msgs" in dir() else generate_messages(r)["whatsapp"])