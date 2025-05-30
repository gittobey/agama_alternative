import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from threading import Lock, Thread
import time
import os
from datetime import datetime

# Setup directories
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
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Thread-safe data storage
lock = Lock()
post_requests = {}
agent_last_seen = {}
offline_timeout = 5  # Seconds after which an agent is considered offline

def save_agent_data(hostname, data):
    """Save agent data to a file with timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"data/{hostname}_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(data, f)
        logger.info(f"Saved data for {hostname} to {filename}")
    except Exception as e:
        logger.error(f"Error saving data for {hostname}: {str(e)}")

def check_agent_status():
    """
    Background thread to check if agents have gone offline.
    """
    logger.info("Starting agent status monitoring thread")
    while True:
        try:
            with lock:
                current_time = time.time()
                offline_agents = []
                
                for hostname, last_seen in agent_last_seen.items():
                    if current_time - last_seen > offline_timeout:
                        logger.warning(f"Agent {hostname} marked as offline")
                        socketio.emit('agentStatus', {hostname: 'offline'})
                        offline_agents.append(hostname)
                
                #Remove offline agents do not remove offline agents
                for hostname in offline_agents:
                    del agent_last_seen[hostname]
                    if hostname in post_requests:
                        del post_requests[hostname]

        except Exception as e:
            logger.error(f"Error in agent status check: {str(e)}")
        
        time.sleep(5)  # Check every 5 seconds

@app.route("/report", methods=["POST"])
def report_metrics():
    """
    Endpoint for agents to report system metrics.
    """
    global post_requests, agent_last_seen
    
    try:
        data = request.json
        logger.info(f"Received data from agent: {str(data)[:200]}...")  # Log first 200 chars

        if not data or "hostname" not in data or "data" not in data:
            logger.error("Invalid payload received")
            return jsonify({"error": "Invalid payload"}), 400

        hostname = data["hostname"]
        metrics = data["data"]
        
        with lock:
            post_requests[hostname] = metrics
            agent_last_seen[hostname] = time.time()
            logger.info(f"Updated data for {hostname}")

        # Save the data to disk
        save_agent_data(hostname, data)
        
        # Emit events
        socketio.emit("newPostRequest", {hostname: metrics})
        socketio.emit('agentStatus', {hostname: 'online'})
        logger.debug(f"Emitted events for {hostname}")

        return jsonify({"message": "Data received"}), 200

    except Exception as e:
        logger.error(f"Error in report_metrics: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/agents", methods=["GET"])
def list_agents():
    """
    Endpoint to list all active agents.
    """
    try:
        with lock:
            agents = list(agent_last_seen.keys())
            logger.info(f"Listing {len(agents)} active agents")
            return jsonify({
                "active_agents": agents,
                "count": len(agents)
            }), 200
    except Exception as e:
        logger.error(f"Error in list_agents: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/")
def index():
    """
    Serve the HTML page for the frontend.
    """
    try:
        logger.info("Serving index page")
        return render_template("index.html")
    except Exception as e:
        logger.error(f"Error serving index page: {str(e)}")
        return "Internal Server Error", 500

def run_server():
    """Run the server with proper error handling"""
    try:
        logger.info("Starting server threads")
        thread = Thread(target=check_agent_status, name="AgentStatusThread")
        thread.daemon = True
        thread.start()
        
        logger.info("Starting SocketIO server")
        socketio.run(app, host="0.0.0.0", port=5000, debug=False)
    except Exception as e:
        logger.critical(f"Server crashed: {str(e)}", exc_info=True)
    finally:
        logger.info("Server shutting down")

if __name__ == "__main__":
    run_server()