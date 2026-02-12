import csv
import re
from collections import defaultdict

input_file = "monitorResults_wiki.csv"
output_file = "microservice_summary_wiki.csv"

def parse_cpu(value):
    """Convert CPU string (e.g. '5m') → float millicores"""
    if isinstance(value, str) and value.endswith("m"):
        try:
            return float(value[:-1])
        except ValueError:
            return 0.0
    try:
        return float(value)
    except:
        return 0.0

def parse_mem(value):
    """Convert MEM string (e.g. '47Mi') → float MiB"""
    if isinstance(value, str) and value.endswith("Mi"):
        try:
            return float(value[:-2])
        except ValueError:
            return 0.0
    try:
        return float(value)
    except:
        return 0.0

def to_float(x):
    """Safely convert strings to float, treating 'nan' or invalid as 0"""
    try:
        if str(x).lower() == "nan":
            return 0.0
        return float(x)
    except:
        return 0.0

# --- Read and aggregate ---
aggregates = defaultdict(lambda: {
    "rpm_http_sum": 0.0,
    "lat_http_sum": 0.0,
    "lat_http_count": 0,
    "rpm_grpc_sum": 0.0,
    "lat_grpc_sum": 0.0,
    "lat_grpc_count": 0,
    "cpu_sum": 0.0,
    "mem_sum": 0.0,
})

with open(input_file, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        timestamp = row["timestamp"]
        pod = row["pod"]

        # Extract microservice name from pod name
        match = re.match(r"^([a-zA-Z0-9\-]+?)-[a-z0-9]{5,}$", pod)
        service = match.group(1) if match else pod

        key = (timestamp, service)

        # Convert and aggregate
        rpm_http = to_float(row.get("rpm_http", 0))
        lat_http = to_float(row.get("lat_http_ms", 0))
        rpm_grpc = to_float(row.get("rpm_grpc", 0))
        lat_grpc = to_float(row.get("lat_grpc_ms", 0))
        cpu = parse_cpu(row.get("cpu", 0))
        mem = parse_mem(row.get("mem", 0))

        aggregates[key]["rpm_http_sum"] += rpm_http
        if lat_http > 0:
            aggregates[key]["lat_http_sum"] += lat_http
            aggregates[key]["lat_http_count"] += 1

        aggregates[key]["rpm_grpc_sum"] += rpm_grpc
        if lat_grpc > 0:
            aggregates[key]["lat_grpc_sum"] += lat_grpc
            aggregates[key]["lat_grpc_count"] += 1

        aggregates[key]["cpu_sum"] += cpu
        aggregates[key]["mem_sum"] += mem

# --- Write aggregated results ---
with open(output_file, "w", newline="") as csvfile:
    fieldnames = [
        "timestamp",
        "service",
        "rpm_http",
        "lat_http_ms",
        "rpm_grpc",
        "lat_grpc_ms",
        "cpu",
        "mem",
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    for (timestamp, service), vals in sorted(aggregates.items()):
        lat_http_avg = (
            vals["lat_http_sum"] / vals["lat_http_count"]
            if vals["lat_http_count"] > 0
            else 0.0
        )
        lat_grpc_avg = (
            vals["lat_grpc_sum"] / vals["lat_grpc_count"]
            if vals["lat_grpc_count"] > 0
            else 0.0
        )

        writer.writerow({
            "timestamp": timestamp,
            "service": service,
            "rpm_http": round(vals["rpm_http_sum"], 2),
            "lat_http_ms": round(lat_http_avg, 2),
            "rpm_grpc": round(vals["rpm_grpc_sum"], 2),
            "lat_grpc_ms": round(lat_grpc_avg, 2),
            "cpu": round(vals["cpu_sum"], 2),
            "mem": round(vals["mem_sum"], 2),
        })

print(f"✅ Aggregated results written to {output_file}")

