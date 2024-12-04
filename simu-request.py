import requests
import json
import time
import threading
import random

SERVER_URL = "http://127.0.0.1:5000/report"  # Update with your actual server URL

# Function to simulate a single agent sending POST requests
def simulate_agent(hostname, interval):
    while True:
        payload = {
            "hostname": hostname,
            "data": {
                "ip_address": f"192.168.1.{hostname.split('-')[-1]}",  # Simulate different IPs
                "cpu_usage": random.randint(5, 95),
                "memory_usage": random.randint(5, 95),
                "uptime": f"{hash(hostname) % 1000} hours",
                "network_io": {
                    "bytes_sent": hash(hostname) % 10000,
                    "bytes_received": hash(hostname) % 20000
                },
                "disk_usage": {
                    "/": {
                        "disk_label": "Root",
                        "disk_usage": random.randint(5, 95)  # Random disk usage between 5 and 95
                    }
                }
            }
        }

        try:
            response = requests.post(SERVER_URL, json=payload)
            print(f"[{hostname}] Response: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"[{hostname}] Error: {e}")

        time.sleep(interval)

# Simulate multiple agents
def main():
    agent_threads = []
    num_agents = 10  # Number of agents to simulate
    interval = 2  # Interval between requests (in seconds)

    for i in range(num_agents):
        hostname = f"agent-{i+1}"
        thread = threading.Thread(target=simulate_agent, args=(hostname, interval))
        agent_threads.append(thread)
        thread.start()

    for thread in agent_threads:
        thread.join()

if __name__ == "__main__":
    main()
