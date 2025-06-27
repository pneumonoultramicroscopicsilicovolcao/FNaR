import os
import ssl
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_mysqldb import MySQL
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Fix for Render.com SSL context
ssl.PROTOCOL_TLS = ssl.PROTOCOL_TLSv1_2

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# MySQL Config
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
mysql = MySQL(app)

# Socket.IO with threading for Render
socketio = SocketIO(app,
                   cors_allowed_origins=os.getenv('FRONTEND_URL'),
                   async_mode='threading')

@app.route('/')
def home():
    return "FNaR Server Running"

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    socketio.run(app,
                 host='0.0.0.0',
                 port=port,
                 debug=False)  # Debug must be False in production
