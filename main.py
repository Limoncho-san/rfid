from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
import opcua
import logging
import shutil
import time
import threading
import os
from opcua import Server

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
# app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# Configure logging
logging.basicConfig(filename='warehouse_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure backup directory exists
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

# Function to backup the database
def backup_database():
    backup_file = os.path.join(BACKUP_DIR, f"backup_{time.strftime('%Y%m%d%H%M%S')}.db")
    shutil.copy("database.db", backup_file)
    logging.info(f"Database backup created: {backup_file}")

# Function to schedule automatic database backups every 24 hours
def schedule_backup():
    while True:
        time.sleep(86400)  # 24 hours in seconds
        backup_database()

# Start the backup thread
database_backup_thread = threading.Thread(target=schedule_backup, daemon=True)
database_backup_thread.start()


# Initialize OPC UA Server
opcua_server = Server()
opcua_server.set_endpoint("opc.tcp://0.0.0.0:4840")  # Allow connections from any client
opcua_namespace = opcua_server.register_namespace("Warehouse")

# Create an OPC UA object for warehouse management
warehouse_obj = opcua_server.nodes.objects.add_object(opcua_namespace, "Warehouse")

# Create variables for inventory management
item_count = warehouse_obj.add_variable(opcua_namespace, "ItemCount", 0)
traffic_light_status = warehouse_obj.add_variable(opcua_namespace, "TrafficLightStatus", "OFF")
HMI_command = warehouse_obj.add_variable(opcua_namespace, "HMICommand", "NONE")
HMI_status = warehouse_obj.add_variable(opcua_namespace, "HMIStatus", "IDLE")

# Define possible HMI commands
HMI_COMMANDS = ["START", "STOP", "RESET", "EMERGENCY_STOP", "LOAD", "UNLOAD", "MAINTENANCE_MODE"]

# Allow PLC and HMI clients to modify these variables
item_count.set_writable()
traffic_light_status.set_writable()
HMI_command.set_writable()
HMI_status.set_writable()

# Start OPC UA server in a separate thread
def start_opcua_server():
    opcua_server.start()
    logging.info("OPC UA Server started at opc.tcp://0.0.0.0:4840")

t = threading.Thread(target=start_opcua_server, daemon=True)
t.start()

# API route to get item count from OPC UA
@app.route("/opcua/get-item-count", methods=["GET"])
def get_item_count():
    return jsonify({"item_count": item_count.get_value()})

# API route to set item count from OPC UA
@app.route("/opcua/set-item-count", methods=["POST"])
def set_item_count():
    data = request.json
    new_count = data.get("item_count")
    if isinstance(new_count, int):
        item_count.set_value(new_count)
        return jsonify({"message": "Item count updated successfully"})
    return jsonify({"error": "Invalid item count"}), 400

# API route to get traffic light status from OPC UA
@app.route("/opcua/get-traffic-light", methods=["GET"])
def get_traffic_light_status():
    return jsonify({"traffic_light_status": traffic_light_status.get_value()})

# API route to set traffic light status from OPC UA
@app.route("/opcua/set-traffic-light", methods=["POST"])
def set_traffic_light_status():
    data = request.json
    new_status = data.get("traffic_light_status")
    if new_status in ["RED", "YELLOW", "GREEN", "OFF"]:
        traffic_light_status.set_value(new_status)
        return jsonify({"message": "Traffic light status updated successfully"})
    return jsonify({"error": "Invalid status"}), 400

# API route to get HMI status
@app.route("/opcua/get-hmi-status", methods=["GET"])
def get_hmi_status():
    return jsonify({"hmi_status": HMI_status.get_value()})

# API route to set HMI command
@app.route("/opcua/set-hmi-command", methods=["POST"])
def set_hmi_command():
    data = request.json
    new_command = data.get("hmi_command")
    if isinstance(new_command, str) and new_command in HMI_COMMANDS:
        HMI_command.set_value(new_command)
        return jsonify({"message": "HMI command updated successfully"})
    return jsonify({"error": "Invalid HMI command"}), 400

# API route to trigger manual backup
@app.route("/backup-now", methods=["POST"])
def manual_backup():
    backup_database()
    return jsonify({"message": "Manual database backup completed successfully."})

# Function to connect to SQLite database
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# Function to initialize the database
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rfid_tag TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create roles table for user permissions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create user roles mapping table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER,
            role_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            PRIMARY KEY (user_id, role_id)
        )
    ''')
    
    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
    ''')
    
    # Create products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            barcode TEXT UNIQUE NOT NULL,
            category_id INTEGER,
            rfid_tag TEXT UNIQUE NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    ''')
    
    # Create cabinets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cabinets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create shelves table (linked to cabinets)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cabinet_id INTEGER,
            name TEXT NOT NULL,
            allows_multiple_categories BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (cabinet_id) REFERENCES cabinets(id)
        )
    ''')
    
    # Create shelf categories (for multiple categories in a shelf)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_categories (
            shelf_id INTEGER,
            category_id INTEGER,
            FOREIGN KEY (shelf_id) REFERENCES shelves(id),
            FOREIGN KEY (category_id) REFERENCES categories(id),
            PRIMARY KEY (shelf_id, category_id)
        )
    ''')
    
    # Create transactions table (logs all stock movements)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            transaction_type TEXT CHECK( transaction_type IN ('load', 'get') ),
            shelf_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (shelf_id) REFERENCES shelves(id)
        )
    ''')
    
    # Create URFID tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urfid_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            rfid_tag TEXT UNIQUE NOT NULL,
            product_id INTEGER,
            shelf_id INTEGER,
            status TEXT CHECK( status IN ('added', 'removed', 'moved') ),
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (shelf_id) REFERENCES shelves(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

# Initialize the database on startup
initialize_database()

# Route to manually reset the database
@app.route("/reset-database", methods=["POST"])
def reset_db_route():
    initialize_database()
    return jsonify({"message": "Database has been reset and reinitialized."})


# Function to connect to Siemens PLC with retry logic
def connect_opcua(retries=3, delay=2):
    for attempt in range(retries):
        try:
            client = opcua.Client(PLC_OPC_UA_URL)
            client.connect()
            logging.info("Connected to Siemens PLC OPC UA server.")
            return client
        except Exception as e:
            logging.error(f"Attempt {attempt + 1}: Failed to connect to Siemens PLC: {str(e)}")
            time.sleep(delay)
    return None

# Function to check PLC connection
def check_plc_connection():
    client = connect_opcua()
    if client:
        client.disconnect()
        return {"status": "Connected"}
    return {"status": "Disconnected", "error": "Cannot connect to Siemens PLC"}

# --------- PLC Connection Health Check Route ---------
@app.route("/opcua/status", methods=["GET"])
def opcua_status():
    return jsonify(check_plc_connection())

# Function to read value from PLC

def read_plc_value(node_id):
    client = connect_opcua()
    if not client:
        return {"error": "Cannot connect to Siemens PLC"}
    try:
        node = client.get_node(node_id)
        value = node.get_value()
        client.disconnect()
        logging.info(f"Read from PLC - Node: {node_id}, Value: {value}")
        return value
    except Exception as e:
        logging.error(f"Failed to read PLC node {node_id}: {str(e)}")
        return {"error": str(e)}

# Function to write value to PLC

def write_plc_value(node_id, value):
    client = connect_opcua()
    if not client:
        return {"error": "Cannot connect to Siemens PLC"}
    try:
        node = client.get_node(node_id)
        node.set_value(value)
        client.disconnect()
        logging.info(f"Write to PLC - Node: {node_id}, Value: {value}")
        return {"message": "Value written successfully"}
    except Exception as e:
        logging.error(f"Failed to write PLC node {node_id}: {str(e)}")
        return {"error": str(e)}

# --------- Traffic Light Control for Siemens PLC ---------
@app.route("/traffic-light", methods=["POST"])
def traffic_light_control():
    data = request.json
    cabinet_id = data.get("cabinet_id")
    status = data.get("status")  # green, yellow, red
    node_id = f"ns=2;s=TrafficLight_{cabinet_id}"
    return write_plc_value(node_id, status)

# --------- OPC UA Read and Write Routes ---------
@app.route("/opcua/read", methods=["POST"])
def opcua_read():
    data = request.json
    node_id = data.get("node_id")
    return jsonify({"value": read_plc_value(node_id)})

@app.route("/opcua/write", methods=["POST"])
def opcua_write():
    data = request.json
    node_id = data.get("node_id")
    value = data.get("value")
    return jsonify(write_plc_value(node_id, value))


# --------- OPC UA Communication Logging ---------
def opcua_log(node_id, value, status, error=None):
    if error:
        logging.error(f"OPC UA Failed - Node: {node_id}, Value: {value}, Status: {status}, Error: {error}")
    else:
        logging.info(f"OPC UA Update - Node: {node_id}, Value: {value}, Status: {status}")



# --------- Error Alerting ---------
@app.route("/error", methods=["POST"])
def error_alert():
    data = request.json
    error_message = data.get("error_message")
    logging.error(f"System alert: {error_message}")
    return jsonify({"message": "Error logged"})

# --------- Authentication ---------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        return "Invalid Credentials", 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --------- RFID Authentication ---------
@app.route("/rfid/auth", methods=["POST"])
def rfid_auth():
    data = request.json
    rfid_tag = data.get("rfid_tag")
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE rfid_tag = ?", (rfid_tag,)).fetchone()
    conn.close()
    if user:
        return jsonify({"message": "RFID authenticated", "user_id": user["id"]})
    return jsonify({"error": "Unauthorized RFID"}), 401

# --------- Product Management ---------
@app.route("/products", methods=["GET", "POST"])
def manage_products():
    conn = get_db_connection()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    if request.method == "POST":
        name = request.form["name"]
        barcode = request.form["barcode"]
        category_id = request.form["category_id"]
        conn.execute("INSERT INTO products (name, barcode, category_id) VALUES (?, ?, ?)", (name, barcode, category_id))
        conn.commit()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template("products.html", products=products, categories=categories)

# --------- Category Management ---------
@app.route("/categories", methods=["GET", "POST"])
def manage_categories():
    conn = get_db_connection()
    if request.method == "POST":
        position = request.form["position"]
        description = request.form["description"]
        conn.execute("INSERT INTO categories (position, description) VALUES (?, ?)", (position, description))
        conn.commit()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template("categories.html", categories=categories)

# --------- Cabinet Categorization ---------
@app.route("/cabinets", methods=["GET", "POST"])
def categorize_cabinets():
    conn = get_db_connection()
    cabinets = conn.execute("SELECT * FROM cabinets").fetchall()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    if request.method == "POST":
        cabinet_id = request.form["cabinet_id"]
        category_mode = request.form["category_mode"]
        conn.execute("UPDATE cabinets SET category_mode = ? WHERE id = ?", (category_mode, cabinet_id))
        conn.commit()
    conn.close()
    return render_template("cabinets.html", cabinets=cabinets, categories=categories)

# --------- Traffic Light Control with Logging ---------
@app.route("/traffic-light", methods=["POST"])
def traffic_light_control():
    data = request.json
    cabinet_id = data.get("cabinet_id")
    status = data.get("status")  # green, yellow, red
    client = opcua.Client("opc.tcp://localhost:4840")
    try:
        client.connect()
        node = client.get_node(f"ns=2;s=TrafficLight_{cabinet_id}")
        node.set_value(status)
        client.disconnect()
        opcua_log(f"TrafficLight_{cabinet_id}", status, "Success")
        return jsonify({"message": f"Traffic light for cabinet {cabinet_id} set to {status}"})
    except Exception as e:
        opcua_log(f"TrafficLight_{cabinet_id}", status, f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

# --------- Loading and Getting Items with RFID ---------
@app.route("/load", methods=["POST"])
def load_items():
    data = request.json
    rfid_tag = data.get("rfid_tag")
    quantity = data.get("quantity")
    
    conn = get_db_connection()
    product = conn.execute("SELECT id FROM products WHERE rfid_tag = ?", (rfid_tag,)).fetchone()
    
    if not product:
        conn.close()
        return jsonify({"error": "RFID tag not found"}), 404  # Грешка, ако частта не е намерена
    
    conn.execute("UPDATE products SET quantity = quantity + ? WHERE id = ?", (quantity, product["id"]))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Item loaded successfully"})


@app.route("/get", methods=["POST"])
def get_items():
    data = request.json
    rfid_tag = data.get("rfid_tag")
    item_id = data.get("item_id")
    quantity = data.get("quantity")
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE rfid_tag = ?", (rfid_tag,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Unauthorized RFID"}), 401
    current_quantity = conn.execute("SELECT quantity FROM products WHERE id = ?", (item_id,)).fetchone()["quantity"]
    if current_quantity >= quantity:
        conn.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?", (quantity, item_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Item retrieved successfully"})
    conn.close()
    return jsonify({"error": "Not enough stock"}), 400

# --------- OPC UA Integration for Warehouse Control with Logging ---------
@app.route("/opcua/update", methods=["POST"])
def opcua_update():
    data = request.json
    node_id = data.get("node_id")
    value = data.get("value")

    if not node_id or not value:
        return jsonify({"error": "Invalid node_id or value"}), 400  # Грешка ако липсват данни

    client = opcua.Client(PLC_OPC_UA_URL)
    try:
        client.connect()
        node = client.get_node(node_id)
        node.set_value(value)
        client.disconnect()
        opcua_log(node_id, value, "Success")
        return jsonify({"message": "OPC UA updated successfully"})
    except Exception as e:
        opcua_log(node_id, value, f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
