import os
import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        database=os.environ.get("DB_NAME", "appdb"),
        user=os.environ.get("DB_USER", "appuser"),
        password=os.environ.get("DB_PASSWORD")
    )

@app.route("/health")
def health():
    return jsonify(status="ok")

@app.route("/visits")
def visits():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS visits (id SERIAL PRIMARY KEY, ts TIMESTAMP DEFAULT NOW());")
    cur.execute("INSERT INTO visits DEFAULT VALUES;")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM visits;")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return jsonify(total_visits=count)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
