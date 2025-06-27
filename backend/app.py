import os
import eventlet
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_mysqldb import MySQL
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Initialize
eventlet.monkey_patch()
load_dotenv()  # Load .env file

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# ===== MySQL Configuration =====
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'fnar_user')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'fnar_game')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
mysql = MySQL(app)

# ===== Socket.IO Setup =====
socketio = SocketIO(app,
                   cors_allowed_origins=os.getenv('FRONTEND_URL', 'http://localhost:5500'),
                   async_mode='eventlet',
                   logger=True)

# ===== Database Models =====
def init_db():
    with app.app_context():
        cur = mysql.connection.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            role ENUM('guard', 'animatronic', 'admin') NOT NULL,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            night_number INT NOT NULL
        )
        """)
        mysql.connection.commit()

# ===== Authentication =====
def create_token(player_id):
    return jwt.encode({
        'player_id': player_id,
        'exp': datetime.utcnow() + timedelta(hours=12)
    }, app.config['SECRET_KEY'], algorithm='HS256')

# ===== Socket.IO Events =====
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('authenticate')
def handle_auth(data):
    try:
        # Verify admin password if needed
        if data.get('role') == 'admin':
            if data.get('password') != os.getenv('ADMIN_PASSWORD'):
                emit('auth_error', {'message': 'Invalid admin password'})
                return

        # Store player in MySQL
        cur = mysql.connection.cursor()
        cur.execute("""
        INSERT INTO players (id, username, role)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE last_active=CURRENT_TIMESTAMP
        """, (request.sid, data.get('name'), data.get('role')))
        mysql.connection.commit()

        # Send success response
        token = create_token(request.sid)
        emit('auth_success', {
            'token': token,
            'role': data.get('role'),
            'night': 1  # Starting night
        })

    except Exception as e:
        emit('auth_error', {'message': str(e)})

# ===== Game Events =====
@socketio.on('door_action')
def handle_door(data):
    try:
        # Verify valid session
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM players WHERE id = %s", (request.sid,))
        if not cur.fetchone():
            raise Exception("Invalid session")

        # Process door action
        emit('door_update', data, broadcast=True, include_self=False)

        # Log to database
        cur.execute("""
        INSERT INTO door_events (player_id, door_side, action)
        VALUES (%s, %s, %s)
        """, (request.sid, data['side'], data['action']))
        mysql.connection.commit()

    except Exception as e:
        emit('error', {'message': str(e)})

# ===== API Endpoints =====
@app.route('/api/status')
def game_status():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) as players_online FROM players")
    result = cur.fetchone()
    return jsonify({
        'status': 'online',
        'players': result['players_online'],
        'version': '1.0'
    })

# ===== Startup =====
if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 10000))
    socketio.run(app,
                 host='0.0.0.0',
                 port=port,
                 debug=os.getenv('DEBUG', 'false').lower() == 'true')
