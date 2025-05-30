import sys
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import psutil
import requests
from datetime import datetime
import platform

class SystemMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SystemMonitorService"
    _svc_display_name_ = "System Monitor Service"
    _svc_description_ = "Monitors system metrics and reports to central server"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_alive = True
        self.SERVER_URL = "http://127.0.0.1:5000/report"  # Make this configurable


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
        # [Keep all your existing methods from the previous service code]
        # get_uptime(), get_disk_infos(), collect_metrics(), report_metrics(), etc.


def init():
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SystemMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SystemMonitorService)

if __name__ == '__main__':
    init()

#To generate exe file
#pyinstaller --onefile --windowed --name AgamaAgentService .\Agama_agent.py
#pyinstaller .\AgamaAgentService.spec
#pyinstaller --onefile --hidden-import win32timezone --hidden-import servicemanager --clean --name AgentService Agama_agent.py'''