import psutil
import requests
import time
from datetime import datetime
import socket
import platform

SERVER_URL = "http://127.0.0.1:5000/report"  # Change to your server IP in production


def get_uptime():
    boot_time = psutil.boot_time()
    current_time = time.time()
    uptime_seconds = int(current_time - boot_time)

    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{days}D {hours}H {minutes}M {seconds}S"


def get_disk_infos():
    disk_info = {}
    partitions = psutil.disk_partitions(all=False)
    for idx, partition in enumerate(partitions, start=1):
        try:
            disk_usage = psutil.disk_usage(partition.mountpoint)
            disk_info[partition.mountpoint] = {
                "disk_label": partition.device,
                "disk_usage": disk_usage.percent
            }
        except PermissionError:
            # Skip partitions that are not accessible
            continue
    return disk_info


def collect_metrics():
    computer_name = platform.node()
    try:
        ip_address = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        ip_address = "0.0.0.0"

    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = get_disk_infos()
    network_io = psutil.net_io_counters()
    uptime = get_uptime()

    return {
        "hostname": computer_name,
        "data": {
            "ip_address": ip_address,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "uptime": uptime,
            "network_io": {
                "bytes_sent": network_io.bytes_sent,
                "bytes_received": network_io.bytes_recv
            },
            "disk_usage": disk_usage
        }
    }


def report_metrics():
    while True:
        try:
            payload = collect_metrics()
            response = requests.post(SERVER_URL, json=payload, timeout=5)
            if response.status_code != 200:
                print(f"Failed to post metrics: {response.status_code}")
        except Exception as e:
            print(f"[{datetime.now()}] Error reporting metrics: {e}")

        time.sleep(5)  # Adjust as needed (e.g., every 5 seconds)


if __name__ == "__main__":
    report_metrics()
