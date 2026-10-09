import datetime as dt
import pandas as pd
import requests
import streamlit as st
from sletat_scraper import BASE, HEADERS, KEEP_COLUMNS, scrape, to_dataframe

st.set_page_config(page_title="Competitors PKG’S Analysis", layout="wide")
st.title("Competitors PKG’S Analysis")


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


def tourists_label(s):
    label = f"{s['adults']} adult{'s' if s['adults'] > 1 else ''}"
    if s["kids"]:
        label += " + children " + ", ".join(map(str, s["kids_ages"]))
    return label


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
    # tourists picker, like sletat.ru: adults counter + tap an age to add a child
    st.session_state.setdefault("adults", 2)
    kids_ages = st.session_state.setdefault("kids_ages", [])
    adults = st.session_state["adults"]
    label = f"{adults} adult{'s' if adults > 1 else ''}"
    if kids_ages:
        label += f", {len(kids_ages)} child{'ren' if len(kids_ages) > 1 else ''}"
    with st.popover(f"Tourists: {label}", width="stretch"):
        st.number_input("Adults", 1, 6, key="adults")
        for i, age in enumerate(kids_ages):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.write(f"Child {i + 1}: {age} {'year' if age == 1 else 'years'}")
            c2.button("✕", key=f"del_kid_{i}", on_click=kids_ages.pop, args=(i,))
        if len(kids_ages) < 3:
            st.markdown("**Add child** — choose age")
            grid = st.columns(2)
            for age in range(18):
                grid[age % 2].button(
                    f"{age} {'year' if age == 1 else 'years'}", key=f"add_kid_{age}",
                    on_click=kids_ages.append, args=(age,), width="stretch",
                )
    kids = len(kids_ages)
    currency = st.selectbox("Currency", ["USD", "EUR", "RUB"])
    mode = st.radio("Rows", ["One per hotel", "All tours"])
    compare = st.checkbox(
        "Compare without / with children", disabled=not kids_ages,
        help="Runs the search twice: adults only, and adults with the children above.",
    )
    go = st.button("Search", type="primary", width="stretch")

if go:
    search = {
        "country_id": country, "city_from_id": city_from,
        "resorts": resorts, "hotels": hotels, "operators": operators,
        "nights_min": int(nights_min), "nights_max": int(nights_max),
        "date_from": date_from.strftime("%d/%m/%Y"),
        "date_to": date_to.strftime("%d/%m/%Y"),
        "adults": int(adults), "kids": int(kids), "kids_ages": [int(x) for x in kids_ages], "currency": currency,
        "group_by": "hotelsPopularity" if mode == "One per hotel" else "",
    }
    searches = {"With children" if kids else "Results": search}
    if compare and kids:
        searches = {"Without children": {**search, "kids": 0, "kids_ages": []},
                    "With children": search}
    results = {}
    try:
        for name, s in searches.items():
            with st.spinner(f"Loading tours: {name.lower()}..."):
                df = to_dataframe(scrape(s), s)
            if not df.empty:
                df.insert(0, "tourists", tourists_label(s))
            results[name] = df
        st.session_state["results"] = results
    except Exception as e:
        st.error(f"Request failed: {e}")

results = st.session_state.get("results")
if results is None:
    st.info("Choose your filters on the left and press Search.")
elif all(df.empty for df in results.values()):
    st.warning("No results for these filters.")
else:
    full = {n: df for n, df in results.items() if not df.empty}
    first = next(iter(full.values()))
    dates = f"{first['depart_from'].iloc[0]}_{first['depart_to'].iloc[0]}"
    all_cols = list(dict.fromkeys(c for df in full.values() for c in df.columns))
    defaults = (["tourists"] if len(results) > 1 else []) + KEEP_COLUMNS
    cols = st.multiselect(
        "Columns (empty = all)", all_cols,
        default=[c for c in defaults if c in all_cols],
    )
    views = {n: df[[c for c in cols if c in df.columns]] if cols else df
             for n, df in full.items()}
    if len(views) > 1:
        views["Together"] = pd.concat(views.values(), ignore_index=True)

    # download buttons at the top: each data set alone, or all together
    for col, (name, view) in zip(st.columns(len(views)), views.items()):
        col.download_button(
            f"Download {name.lower()} ({len(view)} rows)",
            view.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"Competitors_PKGS_Analysis_{name.replace(' ', '_')}_{dates}.csv",
            mime="text/csv", width="stretch",
        )

    for name, df in results.items():
        if df.empty:
            st.warning(f"No results: {name.lower()}.")
    tabs = st.tabs(list(views) + (["Price comparison"] if len(full) > 1 else []))
    for tab, view in zip(tabs, views.values()):
        tab.dataframe(view, width="stretch", hide_index=True)
    if len(full) > 1:
        # cheapest price per hotel + room + meal in each data set, side by side;
        # only rooms found in both data sets are compared
        keys = ["hotel_name", "room", "meal"]
        prices = pd.concat(
            [df.groupby(keys)["price"].min().rename(f"price {n.lower()}")
             for n, df in full.items()], axis=1, join="inner",
        )
        prices["difference"] = prices.iloc[:, -1] - prices.iloc[:, 0]
        with tabs[-1]:
            if prices.empty:
                st.info("No room appears in both data sets. "
                        "Try Rows = All tours to get every room of each hotel.")
            else:
                st.caption(f"{len(prices)} rooms found in both data sets")
                st.dataframe(prices.reset_index(), width="stretch", hide_index=True)

st.divider()
st.caption("Developed by Mo")
