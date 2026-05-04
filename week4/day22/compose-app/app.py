from flask import Flask, jsonify
import psycopg2
import os
import socket

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )

@app.route('/')
def hello():
    return f"Hello from container {socket.gethostname()}\n"

@app.route('/init')
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS visits (
            id SERIAL PRIMARY KEY,
            visited_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()
    return "Table created\n"

@app.route('/visit')
def visit():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO visits DEFAULT VALUES RETURNING id, visited_at')
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": row[0], "visited_at": row[1].isoformat()})

@app.route('/visits')
def list_visits():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, visited_at FROM visits ORDER BY id DESC LIMIT 10')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "visited_at": r[1].isoformat()} for r in rows])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)