import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_mysqldb import MySQL
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Initialize
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

# ===== Socket.IO Setup with gevent =====
socketio = SocketIO(app,
                   cors_allowed_origins=os.getenv('FRONTEND_URL', 'http://localhost:5500'),
                   async_mode='gevent',
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
            animatronic_type VARCHAR(30) NULL,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            games_played INT DEFAULT 0,
            survived_nights INT DEFAULT 0
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            start_time DATETIME NOT NULL,
            end_time DATETIME NULL,
            night_number TINYINT NOT NULL,
            winner ENUM('guard', 'animatronics') NULL,
            duration_seconds INT NULL
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
        if data.get('role') == 'admin':
            if data.get('password') != os.getenv('ADMIN_PASSWORD'):
                emit('auth_error', {'message': 'Invalid admin password'})
                return

        cur = mysql.connection.cursor()
        cur.execute("""
        INSERT INTO players (id, username, role, animatronic_type)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            last_active=CURRENT_TIMESTAMP,
            username=VALUES(username),
            role=VALUES(role),
            animatronic_type=VALUES(animatronic_type)
        """, (request.sid, data.get('name'), data.get('role'), data.get('animatronic_type')))
        mysql.connection.commit()

        token = create_token(request.sid)
        emit('auth_success', {
            'token': token,
            'player_id': request.sid,
            'role': data.get('role'),
            'animatronic_type': data.get('animatronic_type'),
            'night': 1  # Starting night
        })

    except Exception as e:
        emit('auth_error', {'message': str(e)})

# ===== Game Events =====
@socketio.on('door_action')
def handle_door(data):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT role FROM players WHERE id = %s", (request.sid,))
        player = cur.fetchone()
        if not player or player['role'] != 'guard':
            raise Exception("Unauthorized door action")

        emit('door_update', data, broadcast=True, include_self=False)

        # Log to database
        cur.execute("""
        INSERT INTO door_events (session_id, player_id, door_side, action)
        VALUES (
            (SELECT id FROM game_sessions ORDER BY start_time DESC LIMIT 1),
            %s, %s, %s
        )
        """, (request.sid, data['side'], data['action']))
        mysql.connection.commit()

    except Exception as e:
        emit('error', {'message': str(e)})

# ===== API Endpoints =====
@app.route('/api/status')
def game_status():
    cur = mysql.connection.cursor()
    cur.execute("""
    SELECT 
        COUNT(*) as players_online,
        (SELECT night_number FROM game_sessions ORDER BY start_time DESC LIMIT 1) as current_night
    FROM players
    WHERE last_active > NOW() - INTERVAL 5 MINUTE
    """)
    result = cur.fetchone()
    return jsonify({
        'status': 'online',
        'players': result['players_online'],
        'current_night': result['current_night'] or 1,
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
