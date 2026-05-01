from flask import Flask
import socket
import os

app = Flask(__name__)
@app.route('/')
def hello():
    hostname = socket.gethostname()
    version = os.environ.get('APP_VERSION', 'unknown')
    return f"Greetings from container {hostname}, app version {version}\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)