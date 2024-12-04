# from flask import Flask, request, jsonify, render_template
# from flask_socketio import SocketIO
# from threading import Lock
# import logging

# app = Flask(__name__)
# app.config['SECRET_KEY'] = 'secret!'
# socketio = SocketIO(app, cors_allowed_origins="*")

# # Store the latest POST request data for each hostname
# lock = Lock()
# post_requests = {}

# @app.route("/report", methods=["POST"])
# def report_metrics():
#     """
#     Endpoint for agents to report system metrics.
#     """
#     global post_requests
#     data = request.json

#     if not data or "hostname" not in data or "data" not in data:
#         return jsonify({"error": "Invalid payload"}), 400

#     hostname = data["hostname"]

#     # Add or update the latest data for this hostname
#     with lock:
#         post_requests[hostname] = data["data"]

#     # Emit the latest data to all connected clients
#     socketio.emit("newPostRequest", {hostname: data["data"]})

#     return jsonify({"message": "Data received"}), 200

# @app.route("/")
# def index():
#     """
#     Serve the HTML page for the frontend.
#     """
#     return render_template("index.html")

# if __name__ == "__main__":
#     socketio.run(app, host="0.0.0.0", port=5000, debug=True)


from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from threading import Lock, Thread
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

lock = Lock()
post_requests = {}
agent_last_seen = {}
offline_timeout = 5  # Seconds after which an agent is considered offline

def check_agent_status():
    """
    Background thread to check if agents have gone offline.
    """
    while True:
        with lock:
            current_time = time.time()
            for hostname in list(agent_last_seen.keys()):
                if current_time - agent_last_seen[hostname] > offline_timeout:
                    socketio.emit('agentStatus', {hostname: 'offline'})
                    del agent_last_seen[hostname]  # Remove offline agents from tracking

        time.sleep(5)  # Check every 5 seconds

@app.route("/report", methods=["POST"])
def report_metrics():
    """
    Endpoint for agents to report system metrics.
    """
    global post_requests, agent_last_seen
    data = request.json

    if not data or "hostname" not in data or "data" not in data:
        return jsonify({"error": "Invalid payload"}), 400

    hostname = data["hostname"]
    with lock:
        post_requests[hostname] = data["data"]
        agent_last_seen[hostname] = time.time()

    socketio.emit("newPostRequest", {hostname: data["data"]})
    socketio.emit('agentStatus', {hostname: 'online'})  # Notify frontend that agent is online

    return jsonify({"message": "Data received"}), 200

@app.route("/")
def index():
    """
    Serve the HTML page for the frontend.
    """
    return render_template("index.html")

if __name__ == "__main__":
    thread = Thread(target=check_agent_status)
    thread.daemon = True
    thread.start()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
