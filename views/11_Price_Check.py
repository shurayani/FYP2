"""Price Check (patch #23): compare what you paid for an item at different shops, using the items read from
your receipts. Matching is forgiving: every word you type must appear in the item name (small spelling
differences are allowed), so 'milo' also finds 'NESTLE MILO ACTIV-GO 1KG'."""
import difflib
import re

import pandas as pd
import streamlit as st

from src import db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(t("Price Check"))
st.caption(t("Search for something you have bought before to see what you paid at each shop and where it was cheapest."))

items = db.get_item_history(uid)
if not items:
    st.info(t("No receipt items saved yet. Scan receipts that list their items, then come back here."))
    st.stop()

query = st.text_input(t("Item"), placeholder="Milo", key="pc_query")
if not query.strip():
    common = pd.Series([i["item_name"].strip().upper() for i in items]).value_counts().head(8)
    if len(common):
        st.caption(t("Bought most often: {items}", items=", ".join(n.title() for n in common.index)))
    st.stop()

tokens = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1] or [query.lower().strip()]


def _matches(name: str) -> bool:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return all(any(tok in w or difflib.SequenceMatcher(None, tok, w).ratio() >= 0.8 for w in words) for tok in tokens)


found = [i for i in items if _matches(i["item_name"])]
if not found:
    st.info(t("Nothing on your receipts matches '{q}'. Try a shorter word, like the brand name.", q=query))
    st.stop()

df = pd.DataFrame(found)
df["amount"] = df["amount"].astype(float).round(2)
df["product"] = df["item_name"].str.strip().str.upper()
products = sorted(df["product"].unique())
if len(products) > 1:                              # e.g. 'MILO 1KG' and 'MILO 3IN1 18S' are different products
    chosen = st.multiselect(t("Products found"), products, default=products, key="pc_products",
                            help=t("Remove products that are not the same item (another size or pack) to compare like with like."))
    df = df[df["product"].isin(chosen)]
    if df.empty:
        st.info(t("Choose at least one product."))
        st.stop()
cheapest = df.loc[df["amount"].idxmin()]
dearest = df.loc[df["amount"].idxmax()]

k = st.columns(3)
k[0].metric(t("Cheapest"), ui.money(cheapest["amount"]))
k[1].metric(t("Most expensive"), ui.money(dearest["amount"]))
k[2].metric(t("Times bought"), len(df))
st.success(t("Cheapest at {shop} on {d}: {p}.", shop=cheapest["merchant"], d=cheapest["date"],
             p=ui.money(cheapest["amount"])))

st.subheader(t("Lowest price at each shop"), anchor=False)
per_shop = (df.sort_values("date", ascending=False)
              .groupby("merchant", as_index=False)
              .agg(low=("amount", "min"), last=("date", "first"), n=("amount", "size"))
              .sort_values("low"))
st.dataframe(pd.DataFrame({t("Shop"): per_shop["merchant"], t("Lowest price"): per_shop["low"].map(ui.money),
                           t("Last bought"): per_shop["last"], t("Times bought"): per_shop["n"]}),
             width="stretch", hide_index=True)

with st.expander(t("Every purchase ({n})", n=len(df))):
    st.dataframe(pd.DataFrame({t("Item as printed"): df["item_name"], t("Shop"): df["merchant"],
                               t("Date"): df["date"], "RM": df["amount"]}), width="stretch", hide_index=True)
st.caption(t("Prices are the line totals printed on the receipt. If you bought more than one, the price covers all of them, and different sizes are listed separately by name."))
