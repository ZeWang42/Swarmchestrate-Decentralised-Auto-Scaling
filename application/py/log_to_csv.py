import csv
import re

input_file = "monitorResults.log"
output_file = "monitorResults_wiki.csv"

# Regular expressions
timestamp_pattern = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
data_line_pattern = re.compile(r"^([a-zA-Z0-9\-]+)\s+([\d\.]+)\s+(\S+)\s+([\d\.]+)\s+([\d\.nan]+)\s+([\d\.]+)\s+([\d\.nan]+)\s+(\S+)$")

rows = []
current_ts = None

with open(input_file, "r") as f:
    for line in f:
        line = line.strip()

        # Extract timestamp
        ts_match = timestamp_pattern.match(line)
        if ts_match:
            current_ts = ts_match.group(1)
            continue

        # Skip separators and headers
        if not line or line.startswith("POD") or line.startswith("-"):
            continue

        # Parse data line
        parts = line.split()
        if len(parts) >= 8 and current_ts:
            pod = parts[0]
            ip = parts[1]
            node = parts[2]
            rpm_http = parts[3]
            lat_http = parts[4]
            rpm_grpc = parts[5]
            lat_grpc = parts[6]
            cpu_mem = parts[7]

            # Split CPU/MEM field (e.g., "5m/47Mi")
            cpu, mem = (cpu_mem.split("/") + ["", ""])[:2]

            rows.append({
                "timestamp": current_ts,
                "pod": pod,
                "ip": ip,
                "node": node,
                "rpm_http": rpm_http,
                "lat_http_ms": lat_http,
                "rpm_grpc": rpm_grpc,
                "lat_grpc_ms": lat_grpc,
                "cpu": cpu,
                "mem": mem
            })

# Write to CSV
with open(output_file, "w", newline="") as csvfile:
    fieldnames = ["timestamp", "pod", "ip", "node",
                  "rpm_http", "lat_http_ms", "rpm_grpc", "lat_grpc_ms",
                  "cpu", "mem"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"✅ Converted {len(rows)} rows → {output_file}")

