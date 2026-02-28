import re
import csv

input_file = "monitor.log"
output_file = "frontend.csv"

pattern = re.compile(
    r"^\[(.*?)\]\s+(frontend-[^\s]+)\s+([^\s]+)\s+([^\s]+)\s+(\d+|nan)\s+([^\s]+)\s+(\d+|nan)\s+([^\s]+)\s+([^\s]+)"
)

rows = []
with open(input_file) as f:
    for line in f:
        m = pattern.match(line)
        if m:
            timestamp, pod, ip, node, rpm, lat, inflight, cpu, mem = m.groups()
            rows.append([
                timestamp, pod, ip, node, rpm, lat, inflight,
                cpu.replace("m", ""), mem.replace("Mi", "")
            ])

with open(output_file, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["timestamp", "pod", "ip", "node", "rpm", "lat_ms", "inflight", "cpu_m", "mem_mi"])
    writer.writerows(rows)

print(f"✅ Extracted {len(rows)} frontend entries into {output_file}")

