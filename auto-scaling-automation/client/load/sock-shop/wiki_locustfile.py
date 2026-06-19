import os
import random
import numpy as np
import pandas as pd
from locust import HttpUser, TaskSet, between, LoadTestShape

# ---- CONFIG ----
CSV_PATH = os.getenv("CSV_PATH", "load/sock-shop/workloads/constant.csv")
TIME_MINUTE = int(os.getenv("TIME_MINUTE", "3"))
SCALE_FACTOR = float(os.getenv("SCALE_FACTOR", "1"))
SPAWN_RATE = int(os.getenv("SPAWN_RATE", "20"))

TIME_LIMIT = TIME_MINUTE * 60
WINDOW_NUM = TIME_MINUTE
# ----------------

# Sock Shop endpoints
ITEM_IDS = [
    "3395a43e-2d88-40de-b95f-e00e1502085b",
    "510a0d7e-8e83-4193-b483-e27e09ddc34d",
    "837ab141-399e-4c1f-9abc-bace40296bac",
]


def home(l):
    l.client.get("/")


def catalogue(l):
    l.client.get("/catalogue")


def view_item(l):
    item = random.choice(ITEM_IDS)
    l.client.get(f"/catalogue/{item}")


def add_to_cart(l):
    item = random.choice(ITEM_IDS)
    l.client.post("/cart", json={"id": item, "quantity": 1})


def view_cart(l):
    l.client.get("/cart")


def login(l):
    l.client.post("/login", json={
        "username": "user",
        "password": "password"
    })


def checkout(l):
    l.client.post("/orders")


class UserBehavior(TaskSet):
    def on_start(self):
        home(self)

    tasks = {
        home: 2,
        catalogue: 3,
        view_item: 5,
        add_to_cart: 2,
        view_cart: 2,
        login: 1,
        checkout: 1,
    }


class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 1)


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

        stages.append({
            "duration": int((i + 1) * window_size),
            "users": users,
            "spawn_rate": SPAWN_RATE,
        })

    def tick(self):
        run_time = round(self.get_run_time())
        for stage in self.stages:
            if run_time <= stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None
