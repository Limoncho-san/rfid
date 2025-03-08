from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
import opcua
import rfid_reader

app = Flask(__name__)
app.secret_key = "supersecretkey"

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn



# Configure logging
logging.basicConfig(filename='warehouse_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --------- OPC UA Communication Logging ---------
def opcua_log(node_id, value, status):
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
    item_id = data.get("item_id")
    quantity = data.get("quantity")
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE rfid_tag = ?", (rfid_tag,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Unauthorized RFID"}), 401
    conn.execute("UPDATE products SET quantity = quantity + ? WHERE id = ?", (quantity, item_id))
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
    client = opcua.Client("opc.tcp://localhost:4840")
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









