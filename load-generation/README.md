# Load generation

Use locust to generate load to application's frontend gateway

## Prerequisite

install locust 
```sh
# Create the environment
python3 -m venv venv

# Activate it (you must do this every time you open a new terminal)
source venv/bin/activate

# Install locust inside the environment
pip install -r requirements.txt

```
## Step 1: configure frontend gateway entry

```sh
cd config
vim exp_config.py
```
edit 'entry': 'http://<public_ip>:8080/' with your k3s's master node's public ip

## (optional) Step 2: configure loads and user behaviour patterns

Inside the /load folder, you can edit wiki_locustfile.py to configure loads by modifying: 

```sh
wave_df = pd.read_csv('load/online-boutique/workloads/wiki_train.csv')
``` 

You can also edit user behavirour by editing tasks in:

```sh
class UserBehavior(TaskSet):
```

## Step 3: run load generation script

```sh
./run-load-generation.sh
```
