import datetime as dt
import requests
import streamlit as st
from sletat_scraper import BASE, HEADERS, KEEP_COLUMNS, scrape, to_dataframe

st.set_page_config(page_title="Badawistaa", layout="wide")
st.title("Badawistaa")


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch(method, params):
    r = requests.get(f"{BASE}/{method}", params=dict(params), headers=HEADERS, timeout=30)
    r.raise_for_status()
    result = next(v for k, v in r.json().items() if k.endswith("Result"))
    return {str(x["Name"]): x["Id"] for x in result["Data"]}


def lookup(method, **params):
    """Returns {name: id}. Empty dict if the endpoint doesn't answer."""
    try:
        return _fetch(method, tuple(sorted(params.items())))
    except Exception:
        return {}


def pick_one(label, options, default_id):
    if options:
        names = list(options)
        idx = next((i for i, n in enumerate(names) if options[n] == default_id), 0)
        return options[st.selectbox(label, names, index=idx)]
    return int(st.text_input(f"{label} (ID)", str(default_id)))


def pick_many(label, options, default_ids=()):
    if options:
        defaults = [n for n, i in options.items() if i in default_ids]
        return [options[n] for n in st.multiselect(label, list(options), default=defaults)]
    txt = st.text_input(f"{label} (IDs, comma separated)", ",".join(map(str, default_ids)))
    return [int(x) for x in txt.split(",") if x.strip()]


with st.sidebar:
    st.header("Search")
    city_from = pick_one("From", lookup("GetDepartCities"), 832)
    country = pick_one("Country", lookup("GetCountries", townFromId=city_from), 40)
    resorts = pick_many("Resorts (empty = all)", lookup("GetCities", countryId=country))
    hotels = pick_many(
        "Hotels (empty = all)",
        lookup("GetHotels", countryId=country, towns=",".join(map(str, resorts)),
               stars="", filter="", all=-1),
    )
    operators = pick_many(
        "Operators (empty = all)",
        lookup("GetTourOperators", townFromId=city_from, countryId=country),
    )

    today = dt.date.today()
    date_from = st.date_input("Depart from", today + dt.timedelta(days=10))
    date_to = st.date_input("Depart to", today + dt.timedelta(days=18))
    c1, c2 = st.columns(2)
    nights_min = c1.number_input("Nights min", 1, 30, 7)
    nights_max = c2.number_input("Nights max", 1, 30, 7)
    adults = st.number_input("Adults", 1, 6, 2)
    currency = st.selectbox("Currency", ["USD", "EUR", "RUB"])
    mode = st.radio("Rows", ["One per hotel", "All tours"])
    go = st.button("Search", type="primary", use_container_width=True)

if go:
    search = {
        "country_id": country, "city_from_id": city_from,
        "resorts": resorts, "hotels": hotels, "operators": operators,
        "nights_min": int(nights_min), "nights_max": int(nights_max),
        "date_from": date_from.strftime("%d/%m/%Y"),
        "date_to": date_to.strftime("%d/%m/%Y"),
        "adults": int(adults), "kids": 0, "currency": currency,
        "group_by": "hotelsPopularity" if mode == "One per hotel" else "",
    }
    with st.spinner("Loading tours..."):
        try:
            st.session_state["df"] = to_dataframe(scrape(search), search)
        except Exception as e:
            st.error(f"Request failed: {e}")

df = st.session_state.get("df")
if df is None:
    st.info("Choose your filters on the left and press Search.")
elif df.empty:
    st.warning("No results for these filters.")
else:
    st.success(f"{len(df)} rows")
    cols = st.multiselect(
        "Columns (empty = all)", list(df.columns),
        default=[c for c in KEEP_COLUMNS if c in df.columns],
    )
    view = df[cols] if cols else df
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button(
        "Download CSV",
        view.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"sletat_{dt.datetime.now():%Y%m%d_%H%M}.csv",
        mime="text/csv",
    )

st.divider()
st.caption("Developed by Mo")
