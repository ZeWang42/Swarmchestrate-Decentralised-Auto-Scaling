import os
import random
import numpy as np
import pandas as pd
from locust import HttpUser, LoadTestShape, TaskSet, between

# ---- CONFIG ----
PRODUCT_IDS = [
    "0PUK6V6EV0",
    "1YMWWN1N4O",
    "2ZYFJ3GM2N",
    "66VCHSJNUP",
    "6E92ZMYYFZ",
    "9SIQT8TOJO",
    "L9ECAV7KIM",
    "LS4PSXUNUM",
    "OLJCESPC7Z",
]

CURRENCIES = ["EUR", "USD", "JPY", "CAD"]

#CSV_PATH = os.getenv("CSV_PATH", "load/online-boutique/workloads/constant-200.csv")
CSV_PATH = os.getenv("CSV_PATH", "load/online-boutique/workloads/wiki_load.csv")
TIME_MINUTE = int(os.getenv("TIME_MINUTE", "60"))
SCALE_FACTOR = float(os.getenv("SCALE_FACTOR", "0.6"))
SPAWN_RATE = int(os.getenv("SPAWN_RATE", "20"))
LOAD_DIST = os.getenv("LOAD_DIST", "1")

TIME_LIMIT = TIME_MINUTE * 60
WINDOW_NUM = TIME_MINUTE
# ----------------


def index(l):
    l.client.get("/")


def set_currency(l):
    l.client.post(
        "/setCurrency",
        {"currency_code": random.choice(CURRENCIES)},
    )


def browse_product(l):
    l.client.get(f"/product/{random.choice(PRODUCT_IDS)}")


def view_cart(l):
    l.client.get("/cart")


def add_to_cart(l):
    product = random.choice(PRODUCT_IDS)

    l.client.get(f"/product/{product}")
    l.client.post(
        "/cart",
        {
            "product_id": product,
            "quantity": random.choice([1, 2, 3, 4, 5, 10]),
        },
    )


def checkout(l):
    add_to_cart(l)
    l.client.post(
        "/cart/checkout",
        {
            "email": "someone@example.com",
            "street_address": "1600 Amphitheatre Parkway",
            "zip_code": "94043",
            "city": "Mountain View",
            "state": "CA",
            "country": "United States",
            "credit_card_number": "4432-8015-6152-0454",
            "credit_card_expiration_month": "1",
            "credit_card_expiration_year": "2039",
            "credit_card_cvv": "672",
        },
    )


class UserBehavior(TaskSet):
    def on_start(self):
        index(self)

    if LOAD_DIST == "1":
        tasks = {
            index: 1,
            set_currency: 1,
            browse_product: 10,
            add_to_cart: 2,
            view_cart: 3,
            checkout: 1,
        }
    elif LOAD_DIST == "2":
        tasks = {
            index: 5,
            set_currency: 1,
            browse_product: 1,
            add_to_cart: 5,
            view_cart: 5,
            checkout: 5,
        }
    else:
        tasks = {
            index: 1,
            browse_product: 10,
            view_cart: 2,
        }


class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 5)


class StagesShapeFromCSV(LoadTestShape):
    wave_df = pd.read_csv(CSV_PATH)
    wave_list = wave_df["count"].tolist()

    window_size = TIME_LIMIT / WINDOW_NUM
    segm_len = max(1, int(len(wave_list) / WINDOW_NUM))

    stages = []
    for i in range(WINDOW_NUM):
        start = i * segm_len
        end = min((i + 1) * segm_len, len(wave_list))

        users = int(np.mean(wave_list[start:end]) * SCALE_FACTOR)
        users = max(users, 1)

        stages.append(
            {
                "duration": int((i + 1) * window_size),
                "users": users,
                "spawn_rate": SPAWN_RATE,
            }
        )

    def tick(self):
        run_time = round(self.get_run_time())

        for stage in self.stages:
            if run_time <= stage["duration"]:
                return (stage["users"], stage["spawn_rate"])

        return None
