import psutil
import requests
import time
import socket
import platform
import win32serviceutil
import win32service
import win32event
import servicemanager
import sys
import logging
from logging.handlers import RotatingFileHandler

# Configuration
SERVER_URL = "http://127.0.0.1:5000/report"  # Update with your server URL
REPORT_INTERVAL = 5  # Seconds between reports
LOG_FILE = "C:\\ProgramData\\AgentMonitor\\agent_service.log"  # Standard Windows log location

class AgentMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AgentMonitorService"
    _svc_display_name_ = "System Agent Monitoring Service"
    _svc_description_ = "Monitors system metrics and reports to central server"

    def __init__(self, args):
        # Create log directory if needed
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        except Exception as e:
            pass  # Will fall back to current directory
        
        # Configure logging
        self.configure_logging()
        
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True
        self.logger = logging.getLogger('AgentMonitor')

    def configure_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(
                    LOG_FILE,
                    maxBytes=1024*1024,  # 1MB
                    backupCount=5
                )
            ]
        )

    def SvcStop(self):
        self.logger.info("Service stopping...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False

    def SvcDoRun(self):
        self.logger.info("Service starting")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def get_uptime(self):
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}D {hours}H {minutes}M {seconds}S"

    def get_disk_infos(self):
        disk_info = {}
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info[partition.device] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent
                }
            except Exception as e:
                self.logger.warning(f"Disk {partition.device} error: {e}")
        return disk_info

    def collect_metrics(self):
        return {
            "hostname": platform.node(),
            "data": {
                "ip_address": socket.gethostbyname(socket.gethostname()),
                "cpu_usage": psutil.cpu_percent(interval=1),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": self.get_disk_infos(),
                "network_io": {
                    "bytes_sent": psutil.net_io_counters().bytes_sent,
                    "bytes_received": psutil.net_io_counters().bytes_recv
                },
                "uptime": self.get_uptime()
            }
        }

    def report_metrics(self):
        while self.is_alive:
            try:
                data = self.collect_metrics()
                response = requests.post(SERVER_URL, json=data, timeout=10)
                if not response.ok:
                    self.logger.warning(f"Server response: {response.status_code}")
            except Exception as e:
                self.logger.error(f"Reporting error: {e}")
            
            # Check for stop signal every 0.5 seconds
            for _ in range(REPORT_INTERVAL * 2):
                if not self.is_alive:
                    return
                time.sleep(0.5)

    def main(self):
        try:
            self.report_metrics()
        except Exception as e:
            self.logger.critical(f"Service failed: {e}")
        finally:
            self.logger.info("Service stopped")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AgentMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(AgentMonitorService)
        
#To generate exe file
#pyinstaller --onefile --windowed --name AgamaAgentService .\Agama_agent.py
#pyinstaller .\AgamaAgentService.spec
#pyinstaller --onefile --hidden-import win32timezone --hidden-import servicemanager --clean --name AgentService Agama_agent.py'''