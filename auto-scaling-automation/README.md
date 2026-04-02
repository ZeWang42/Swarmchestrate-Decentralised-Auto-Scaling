This is an automation tool that enables hassle-free autoscaling experiments by eliminating the need for manual configuration. Additionally, it supports custom HPA integration.

# Bookinfo experiment setup

This bundle contains:

- `server/server.py`: FastAPI autoscaling experiment server
- `client/load.py`: client-side experiment orchestrator
- `client/config/exp_config.py`: experiment matrix and endpoints
- `client/load/book-info/wiki_locustfile.py`: Locust file using CSV-driven workload
- `server/requirements.txt`
- `client/requirements.txt`

## Server run
```bash
pip install -r server/requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```

## Client run
From inside the client folder:
```bash
pip install -r requirements.txt
python load.py
```

## Notes
- Update `SERVER_BASE_URL` and `BOOKINFO_HOST` in `client/config/exp_config.py`.
- The client expects workload files:
  - `load/book-info/workloads/constant-100.csv`
  - `load/book-info/workloads/constant-300.csv`
  - `load/book-info/workloads/constant-500.csv`
- The Locust file reads the workload path from the `CSV_PATH` environment variable.
