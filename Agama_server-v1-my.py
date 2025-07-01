import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from threading import Lock, Thread, Event
import time
import os
import json
import mysql.connector
from datetime import datetime
from flask_cors import cross_origin
from flask_cors import CORS


# === Configuration ===
DB_CONFIG = {
    'host': 'localhost',
    'user': 'User',
    'password': 'P@$$w0rd',
    'database': 'agamadb'
}

AGENT_STATE_TABLE = "agents"
# Cache to hold metrics for interval writing
cached_metrics = {}
stop_event = Event()

# === Setup ===
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)

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
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Allow all origins
	"methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
	"allow_headers": ["Content-Type", "Authorization"]
	}
})

app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

lock = Lock()
post_requests = {}
agent_last_seen = {}
offline_timeout = 5

# === DB Helpers ===
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def upsert_agent_status(hostname, status, timestamp):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {AGENT_STATE_TABLE} (hostname, status, last_seen)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                last_seen = VALUES(last_seen)
        """, (hostname, status, timestamp))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"MySQL upsert error for {hostname}: {str(e)}", exc_info=True)

def load_all_agents_from_db():
    agents = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT hostname, status, UNIX_TIMESTAMP(last_seen) as last_seen FROM {AGENT_STATE_TABLE}")
        for row in cursor.fetchall():
            agents[row['hostname']] = {
                "status": row["status"],
                "last_seen": float(row["last_seen"])
            }
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error loading agents from DB: {str(e)}", exc_info=True)
    return agents

# === Utility ===
def save_agent_data(hostname, data):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"data/{hostname}_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(data, f)
        logger.info(f"Saved data for {hostname} to {filename}")
    except Exception as e:
        logger.error(f"Error saving data for {hostname}: {str(e)}")

# === Threads ===
def check_agent_status():
    logger.info("Starting agent status monitoring thread")
    while True:
        try:
            with lock:
                current_time = time.time()
                for hostname, info in agent_last_seen.items():
                    if info['status'] == 'online' and current_time - info['last_seen'] > offline_timeout:
                        logger.warning(f"Agent {hostname} marked as offline")
                        agent_last_seen[hostname]['status'] = 'offline'
                        upsert_agent_status(hostname, 'offline', datetime.fromtimestamp(current_time))
                        socketio.emit('agentStatus', {hostname: 'offline'})
        except Exception as e:
            logger.error(f"Error in agent status check: {str(e)}")
        time.sleep(5)

# def log_to_mysql_snapshot():
#     logger.info("Started full-snapshot MySQL logger thread")
#     while True:
#         try:
#             with lock:
#                 if post_requests:
#                     snapshot = [{hostname: metrics} for hostname, metrics in post_requests.items()]
#                     combined_json = json.dumps(snapshot)
#                     timestamp = datetime.now()
#
#                     conn = get_db_connection()
#                     cursor = conn.cursor()
#                     cursor.execute("""
#                         INSERT INTO metricstable (metricsdata, created_at)
#                         VALUES (%s, %s)
#                     """, (combined_json, timestamp))
#                     conn.commit()
#                     cursor.close()
#                     conn.close()
#
#                     logger.info(f"Logged snapshot of {len(snapshot)} agents to database")
#         except Exception as e:
#             logger.error(f"MySQL snapshot logging error: {str(e)}", exc_info=True)
#             time.sleep(5)


# === Endpoints ===

def log_metrics_to_db():
    while not stop_event.is_set():
        try:
            with lock:
                timestamp = datetime.now()
                if not cached_metrics:
                    time.sleep(5)
                    continue

                # Format as list of {"agent-name": data}
                payload = [{host: data} for host, data in cached_metrics.items()]
                payload_json = json.dumps(payload)

            # Insert into MySQL
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO metricstable (metricsdata, created_at) VALUES (%s, %s)",
                (payload_json, timestamp)
            )
            conn.commit()
            cursor.close()
            conn.close()

            logger.info("Logged metrics to database.")

        except Exception as e:
            logger.error(f"Error logging metrics to DB: {str(e)}", exc_info=True)

        time.sleep(5)  # Interval



@app.route("/report", methods=["POST"])
def report_metrics():
    try:
        data = request.json
        logger.info(f"Received data from agent: {str(data)[:200]}...")

        if not data or "hostname" not in data or "data" not in data:
            return jsonify({"error": "Invalid payload"}), 400

        hostname = data["hostname"]
        metrics = data["data"]

        with lock:
            post_requests[hostname] = metrics
            cached_metrics[hostname] = metrics
            now = time.time()
            agent_last_seen[hostname] = {"last_seen": now, "status": "online"}
            upsert_agent_status(hostname, 'online', datetime.fromtimestamp(now))

        save_agent_data(hostname, data)
        socketio.emit("newPostRequest", {hostname: metrics})
        socketio.emit('agentStatus', {hostname: 'online'})

        return jsonify({"message": "Data received"}), 200

    except Exception as e:
        logger.error(f"Error in report_metrics: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/agents", methods=["GET"])
def list_agents():
    try:
        result = []
        with lock:
            for hostname, info in agent_last_seen.items():
                result.append({
                    "hostname": hostname,
                    "status": info["status"],
                    "last_seen": datetime.fromtimestamp(info["last_seen"]).strftime("%Y-%m-%d %H:%M:%S")
                })
        return jsonify({"agents": result, "count": len(result)}), 200
    except Exception as e:
        logger.error(f"Error in list_agents: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/")
def index():
    try:
        logger.info("Serving index page")
        return render_template("index.html")
    except Exception as e:
        logger.error(f"Error serving index page: {str(e)}")
        return "Internal Server Error", 500

# === Server Runner ===
def run_server():
    global agent_last_seen
    agent_last_seen = load_all_agents_from_db()

    Thread(target=check_agent_status, name="AgentStatusThread", daemon=True).start()
    Thread(target=log_metrics_to_db, name="MySQLLoggerThread", daemon=True).start()

    socketio.run(app, host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    run_server()
