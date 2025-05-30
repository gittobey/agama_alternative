import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from threading import Lock, Thread, Event
import time
import os
from datetime import datetime
import json
import win32serviceutil
import win32service
import win32event
import servicemanager
import sys

class FlaskMonitoringService(win32serviceutil.ServiceFramework):
    _svc_name_ = "FlaskMonitoringService"
    _svc_display_name_ = "Agent Monitoring Server"
    _svc_description_ = "Flask-based server for receiving agent metrics"

    def __init__(self, args):
        # Initialize directories
        os.makedirs('logs', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
            handlers=[
                RotatingFileHandler('logs/server.log', maxBytes=1000000, backupCount=5),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = False
        self.app = None
        self.socketio = None
        self.server_thread = None

    def SvcStop(self):
        self.logger.info("Stopping service...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.is_running = False
        if self.socketio:
            self.socketio.stop()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.logger.info("Starting service")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.is_running = True
        self.start_flask_server()

    def start_flask_server(self):
        """Initialize and start the Flask server"""
        try:
            # Thread-safe data storage
            self.lock = Lock()
            self.post_requests = {}
            self.agent_last_seen = {}
            self.offline_timeout = 5  # Seconds

            # Create Flask app
            self.app = Flask(__name__)
            self.app.config['SECRET_KEY'] = 'secret!'
            self.socketio = SocketIO(self.app, cors_allowed_origins="*", logger=True, engineio_logger=True)

            # Register routes
            self.register_routes()
            
            # Start status monitoring thread
            self.status_thread = Thread(target=self.check_agent_status, name="AgentStatusThread")
            self.status_thread.daemon = True
            self.status_thread.start()

            self.logger.info("Starting SocketIO server on 0.0.0.0:5000")
            self.socketio.run(self.app, host="0.0.0.0", port=5000, debug=False)

        except Exception as e:
            self.logger.critical(f"Failed to start server: {e}", exc_info=True)
            raise

    def register_routes(self):
        """Register all Flask routes"""
        @self.app.route("/report", methods=["POST"])
        def report_metrics():
            try:
                data = request.json
                self.logger.info(f"Received data from agent: {str(data)[:200]}...")

                if not data or "hostname" not in data or "data" not in data:
                    self.logger.error("Invalid payload received")
                    return jsonify({"error": "Invalid payload"}), 400

                hostname = data["hostname"]
                metrics = data["data"]
                
                with self.lock:
                    self.post_requests[hostname] = metrics
                    self.agent_last_seen[hostname] = time.time()
                    self.logger.info(f"Updated data for {hostname}")

                self.save_agent_data(hostname, data)
                self.socketio.emit("newPostRequest", {hostname: metrics})
                self.socketio.emit('agentStatus', {hostname: 'online'})
                
                return jsonify({"message": "Data received"}), 200

            except Exception as e:
                self.logger.error(f"Error in report_metrics: {str(e)}", exc_info=True)
                return jsonify({"error": "Internal server error"}), 500

        @self.app.route("/agents", methods=["GET"])
        def list_agents():
            try:
                with self.lock:
                    agents = list(self.agent_last_seen.keys())
                    self.logger.info(f"Listing {len(agents)} active agents")
                    return jsonify({
                        "active_agents": agents,
                        "count": len(agents)
                    }), 200
            except Exception as e:
                self.logger.error(f"Error in list_agents: {str(e)}")
                return jsonify({"error": "Internal server error"}), 500

        @self.app.route("/")
        def index():
            try:
                self.logger.info("Serving index page")
                return render_template("index.html")
            except Exception as e:
                self.logger.error(f"Error serving index page: {str(e)}")
                return "Internal Server Error", 500

    def save_agent_data(self, hostname, data):
        """Save agent data to a file with timestamp"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"data/{hostname}_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(data, f)
            self.logger.info(f"Saved data for {hostname} to {filename}")
        except Exception as e:
            self.logger.error(f"Error saving data for {hostname}: {str(e)}")

    def check_agent_status(self):
        """Background thread to check agent status"""
        self.logger.info("Starting agent status monitoring thread")
        while self.is_running:
            try:
                with self.lock:
                    current_time = time.time()
                    offline_agents = []
                    
                    for hostname, last_seen in self.agent_last_seen.items():
                        if current_time - last_seen > self.offline_timeout:
                            self.logger.warning(f"Agent {hostname} marked as offline")
                            self.socketio.emit('agentStatus', {hostname: 'offline'})
                            offline_agents.append(hostname)
                    
                    # Remove offline agents
                    for hostname in offline_agents:
                        del self.agent_last_seen[hostname]
                        if hostname in self.post_requests:
                            del self.post_requests[hostname]

            except Exception as e:
                self.logger.error(f"Error in agent status check: {str(e)}")
            
            time.sleep(5)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(FlaskMonitoringService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(FlaskMonitoringService)