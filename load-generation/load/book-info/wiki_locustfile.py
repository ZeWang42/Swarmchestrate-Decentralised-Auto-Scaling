import random
import numpy as np
import pandas as pd
from locust import HttpUser, LoadTestShape, TaskSet, between
from locust import task, constant_throughput

# ---- CONFIG ----
BOOK_IDS = ["0"]
CSV_PATH = "load/book-info/workloads/constant-300.csv"     # put CSV in same folder
#CSV_PATH = "load/book-info/workloads/linear.csv"     # put CSV in same folder
TIME_MINUTE = 3
SCALE_FACTOR = 1
SPAWN_RATE = 20
TIME_LIMIT = TIME_MINUTE * 60
WINDOW_NUM = TIME_MINUTE
# ----------------

def productpage(l):
    l.client.get("/productpage")

def list_products(l):
    l.client.get("/api/v1/products")

def details(l):
    l.client.get(f"/api/v1/products/{random.choice(BOOK_IDS)}")

def reviews(l):
    l.client.get(f"/api/v1/products/{random.choice(BOOK_IDS)}/reviews")

def ratings(l):
    l.client.get(f"/api/v1/products/{random.choice(BOOK_IDS)}/ratings")


class UserBehavior(TaskSet):

    def on_start(self):
        productpage(self)

    # Behavior pattern (edit weights to change traffic mix)
    tasks = {
        productpage: 0,
        reviews: 0,
        details: 0,
        ratings: 1,
        list_products: 0,
    }
"""
    tasks = {
        productpage: 2,
        reviews: 1,
        details: 3,
        ratings: 1,
        list_products: 3,
    }
"""
class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 1)
#    wait_time = constant_throughput(300)

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
            "spawn_rate": SPAWN_RATE
        })

    def tick(self):
        run_time = round(self.get_run_time())
        for stage in self.stages:
            if run_time <= stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None
