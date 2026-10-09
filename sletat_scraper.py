import time
import requests
import pandas as pd

BASE = "https://module.sletat.ru/slt/Main.svc"
HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://sletat.ru",
    "referer": "https://sletat.ru/search/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
}

# ---------- EDIT YOUR SEARCH HERE ----------
SEARCH = {
    "country_id": 40,                 # Egypt
    "city_from_id": 832,              # Moscow
    "resorts": [7086, 7087, 7088, 7089, 7090, 1642],
    "hotels": [109930, 34112, 130500, 38573, 30038],
    "operators": [7],                 # Biblio Globus
    "nights_min": 7, "nights_max": 7,
    "date_from": "17/10/2026", "date_to": "25/10/2026",
    "adults": 2, "kids": 0,
    "kids_ages": [],                  # one age per child, e.g. [5, 9]
    "currency": "USD",
    "group_by": "hotelsPopularity",   # one row per hotel; try "" for all tours
}
PAGE_SIZE = 20
OUTPUT = "sletat_tours.csv"
# columns to keep in the output (empty list = keep all)
KEEP_COLUMNS = [
    "hotel_name", "stars", "room", "meal", "depart_from", "depart_to",
    "depart_date", "return_date", "nights",
    "price", "currency", "operator_name", "hotel_url",
]
# -------------------------------------------

# aaData column order (first 19 taken from the API response)
COLUMNS = [
    "offer_id", "operator_id", "hotel_url", "hotel_id", "col_4", "resort_id",
    "tour_name", "hotel_name", "stars", "room", "meal", "accommodation",
    "depart_date", "return_date", "nights", "price_raw", "adults", "kids",
    "operator_name",
]


def csv(xs):
    return ",".join(map(str, xs))


def build_params(s, request_id=0, page=1):
    return {
        "requestId": request_id, "pageSize": PAGE_SIZE, "pageNumber": page,
        "countryId": s["country_id"], "cityFromId": s["city_from_id"],
        "cities": csv(s["resorts"]), "meals": "", "stars": "", "features": "",
        "s_nightsMin": s["nights_min"], "s_nightsMax": s["nights_max"],
        "currencyAlias": s["currency"], "groupBy": s["group_by"],
        "includeDescriptions": 1, "includeOilTaxesAndVisa": 0,
        "minHotelRating": 0, "s_showcase": "false", "templateName": "",
        "filterToursForType": 0, "excludeToursForType": 0,
        "filterToursForTransportType": 0, "yandexId": "", "googleId": "",
        "beachLines": "", "f_to_id": "",
        "s_hotelIsNotInStop": "true", "s_hasTickets": "true",
        "s_ticketsIncluded": "true", "updateResult": 1,
        "visibleOperators": csv(s["operators"]), "hotels": csv(s["hotels"]),
        "s_adults": s["adults"], "s_kids": s["kids"],
        "s_kids_ages": csv(s.get("kids_ages", [])),
        "s_departFrom": s["date_from"], "s_departTo": s["date_to"],
        "s_priceMin": 0, "s_priceMax": 0,
        "calcFullPrice": 1, "showHotelFacilities": 1, "requestSource": 1,
    }


def get_tours(session, s, request_id=0, page=1):
    r = session.get(BASE + "/GetTours", params=build_params(s, request_id, page), timeout=60)
    r.raise_for_status()
    res = r.json()["GetToursResult"]
    if res.get("IsError"):
        raise RuntimeError(res.get("ErrorMessage"))
    return res["Data"]


def wait_until_loaded(session, request_id, max_wait=90):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = session.get(BASE + "/GetLoadState", params={"requestId": request_id}, timeout=30)
            states = r.json()["GetLoadStateResult"]["Data"]
            if states and all(x.get("IsProcessed") for x in states):
                return
        except Exception:
            time.sleep(15)
            return
        time.sleep(2)


def scrape(s):
    session = requests.Session()
    session.headers.update(HEADERS)

    first = get_tours(session, s)          # requestId=0 starts a new search
    request_id = first.get("requestId") or 0
    print("requestId:", request_id)
    if request_id:
        wait_until_loaded(session, request_id)

    rows, page = [], 1
    while True:
        data = get_tours(session, s, request_id, page)
        batch = data.get("aaData") or []
        rows.extend(batch)
        print("page", page, "->", len(batch), "rows")
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(1)
    return rows


def to_dataframe(rows, s=None):
    if not rows:
        return pd.DataFrame()
    width = max(len(r) for r in rows)
    names = COLUMNS + ["col_%d" % i for i in range(len(COLUMNS), width)]
    df = pd.DataFrame([list(r) + [None] * (width - len(r)) for r in rows], columns=names[:width])
    price = df["price_raw"].astype(str).str.extract(r"([\d\s.,]+)\s*(\w+)?")
    df["price"] = pd.to_numeric(price[0].str.replace(r"[\s,]", "", regex=True), errors="coerce")
    df["currency"] = price[1]
    df["hotel_url"] = "https://sletat.ru" + df["hotel_url"].astype(str)
    if s:  # the search window, dd.mm.yyyy like depart_date
        df["depart_from"] = s["date_from"].replace("/", ".")
        df["depart_to"] = s["date_to"].replace("/", ".")
    return df


if __name__ == "__main__":
    df = to_dataframe(scrape(SEARCH), SEARCH)
    if df.empty:
        print("No results - check the SEARCH settings.")
    else:
        df = df[[c for c in KEEP_COLUMNS if c in df.columns] or list(df.columns)]
        df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
        print(df)
        print("Saved", len(df), "rows to", OUTPUT)
