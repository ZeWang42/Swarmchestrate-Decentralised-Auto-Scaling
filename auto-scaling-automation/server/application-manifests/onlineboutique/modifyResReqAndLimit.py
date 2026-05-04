import yaml

input_file = "onlineboutique.yaml"
output_file = "onlineboutique-with-resources.yaml"

frontend_resources = {
    "requests": {
        "cpu": "200m",
        "memory": "128Mi",
    },
    "limits": {
        "cpu": "400m",
        "memory": "512Mi",
    },
}

default_resources = {
    "requests": {
        "cpu": "100m",
        "memory": "64Mi",
    },
    "limits": {
        "cpu": "200m",
        "memory": "256Mi",
    },
}

with open(input_file, "r") as f:
    docs = list(yaml.safe_load_all(f))

for doc in docs:
    if not doc or doc.get("kind") != "Deployment":
        continue

    name = doc["metadata"]["name"]
    containers = doc["spec"]["template"]["spec"]["containers"]

    for container in containers:
        if name == "frontend":
            container["resources"] = frontend_resources
        else:
            container["resources"] = default_resources

with open(output_file, "w") as f:
    yaml.safe_dump_all(docs, f, sort_keys=False)

print(f"Written: {output_file}")
