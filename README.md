# SpiceJet Reclaim Dashboard (Streamlit)

Streamlit app that loads passenger data, auto-tiers passengers
(Very High / High / Medium / Low), and auto-generates voucher codes
plus WhatsApp / SMS / Email / Call-script messages for each tier.

## 1. Install (one time)

Open terminal / cmd in this folder and run:

```bash
pip install -r requirements.txt
```

If you're on Mac and `pip` doesn't work, try `pip3` instead.

## 2. Run the app

```bash
streamlit run app.py
```

This opens automatically in your browser at `http://localhost:8501`.
If it doesn't open automatically, copy that URL into your browser.

## 3. Using it

1. Go to **Upload Data** in the sidebar → upload your `.xlsx` / `.csv`
   passenger file, or click **Load sample data** to try it instantly.
2. **Overview** → see tier breakdown, load factor / DBD charts.
3. **Passengers** → filterable table, export tiered CSV.
4. **Vouchers** → auto-generated voucher codes per passenger, export CSV.
5. **Messages** → preview WhatsApp/SMS/Email/Call script per passenger,
   "Send to all" button (currently simulated — see note below).
6. **Send Schedule** → recommended daily send times by tier.
7. **Add Passenger** → manually add one passenger and see it scored instantly.

## Column names your file should have (any of these aliases work)

| Canonical name   | Accepted aliases                              |
|-------------------|-----------------------------------------------|
| name              | full_name, passenger_name, passenger          |
| phone             | mobile, contact, phone_number                 |
| email             | email_id, mail                                |
| flight            | flight_number, flight_no                      |
| departure_city    | from, origin, dep_city                        |
| arrival_city      | to, destination, arr_city                     |
| departure_date    | date, travel_date                              |
| current_fare      | fare, ticket_fare                              |
| voucher_amt       | voucher_amount, voucher                        |
| load_factor       | lf                                             |
| dbd               | days_before_departure                          |
| product_class     | class, cabin_class                             |

Missing columns get sensible defaults so the app won't crash on a
partial file — but tier accuracy improves with more real columns.

## Using your trained XGBoost model instead of the rule-based score

Right now `compute_score()` in `app.py` is a simple rule-based stand-in
(load factor + DBD + voucher ratio + class), tuned to match the same
tier thresholds (0.05 / 0.15 / 0.30) as `spicereclaim_v3.py`.

To use the actual trained model:

1. In `spicereclaim_v3.py`, after training, save the model:
   ```python
   import pickle
   with open("model.pkl", "wb") as f:
       pickle.dump({"model": model, "label_encoders": label_encoders, "features": FEATURES}, f)
   ```
2. Put `model.pkl` next to `app.py`.
3. Replace `compute_score()` with model loading + `model.predict_proba()`,
   reusing the same feature engineering (load_factor, dbd_bin, etc.) and
   label encoders from training.

## Connecting real sending (WhatsApp / SMS / Email)

The "Send to all" buttons currently just simulate sending. To make them
real:

- **WhatsApp**: use the WhatsApp Business Cloud API (Meta) or a provider
  like Gupshup / Twilio WhatsApp API. You'll need a verified business
  number and an approved message template.
- **SMS**: Twilio, MSG91, or any Indian SMS gateway (look for DLT
  registration requirements for promotional SMS in India).
- **Email**: `smtplib` + your SMTP provider, or SendGrid / AWS SES.
- **Call**: this would need a dialer/IVR integration (e.g. Exotel,
  Knowlarity) — the call script tab just gives agents a script to read.

Wire these into the `sendAll` button logic in the Messages page once
you have API keys.
