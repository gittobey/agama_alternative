import psutil
import requests
import time
from datetime import datetime
import socket
import platform

SERVER_URL = "http://127.0.0.1:5000/report"  #local server for test and monitoring serverip during deplyment

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
    partitions = psutil.disk_partitions(all=False)  # If all=False, it will return only physical disks
    for idx, partition in enumerate(partitions, start=1):
        disk_usage = psutil.disk_usage(partition.mountpoint)
        disk_info[idx] = {
            "disk_label": partition.device,
            "disk_usage": disk_usage.percent
        }
    return disk_info

def collect_metrics():
    computer_name = platform.node()
    ip_address = socket.gethostbyname(socket.gethostname())
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent # RAM
    disk_usage = get_disk_infos() 
    network_io = psutil.net_io_counters()
    uptime = get_uptime()
    return {
        "hostname": computer_name,
        "data" : {
            "ip_address" : ip_address,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "disk_usage": disk_usage,
            # "network_io": {
            #     "bytes_sent": network_io.bytes_sent,
            #     "bytes_received": network_io.bytes_recv
            # },
            "uptime": uptime
        }
    }


def report_metrics():
    while True:
        try:
            data = collect_metrics()
            requests.post(SERVER_URL, json=data)
        except Exception as e:
            print(f"Error reporting metrics: {e}")
        time.sleep(1)  # Report every 2 seconds

if __name__ == "__main__":
    report_metrics()
