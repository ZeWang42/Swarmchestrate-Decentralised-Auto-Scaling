import requests
import pandas as pd
from urllib.parse import quote

ARTICLES = [
    #"FIFA_World_Cup",
    "2026_FIFA_World_Cup",
    #"2022_FIFA_World_Cup",
]

START = "2026010100"
END = "2026082500"

headers = {
    "User-Agent": "world-cup-research/1.0 your-email@example.com"
}

frames = []

for article in ARTICLES:
    encoded_article = quote(article, safe="")

    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia.org/all-access/user/"
        f"{encoded_article}/daily/{START}/{END}"
    )

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    items = response.json()["items"]

    df = pd.DataFrame(items)

    df["date"] = pd.to_datetime(
        df["timestamp"].str[:8],
        format="%Y%m%d"
    )

    df["article"] = article

    frames.append(
        df[["date", "article", "views"]]
    )

result = pd.concat(frames, ignore_index=True)

print(result)

result.to_csv(
    "world_cup_wikipedia_pageviews.csv",
    index=False
)
