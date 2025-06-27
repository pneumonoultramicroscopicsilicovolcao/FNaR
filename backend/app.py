import os
import eventlet
from flask import Flask, request
from flask_socketio import SocketIO, emit, disconnect
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

# Initialize
eventlet.monkey_patch()
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret_123')

# MySQL Configuration
def get_db():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'fnar_user'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'fnar_game')
    )

socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=True,
                   engineio_logger=True)

# Game State
class GameState:
    def __init__(self):
        self.players = {}
        self.admin_sid = None
        self.game_active = False
        self.current_night = 1
        self.energy = 100
        self.start_time = None
        self.doors = {'left': False, 'right': False}
        self.animatronics = {
            'arseny': {'position': 'vent', 'visible': False},
            'iskander': {'position': 'room1', 'visible': False}
        }

game_state = GameState()

# Database Operations
def log_player(sid, name, role):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO players (id, username, role, last_active)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE last_active=NOW()
        """, (sid, name, role))
        db.commit()
    except Exception as e:
        print(f"Database error: {e}")

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('authenticate')
def handle_auth(data):
    role = data.get('role')
    name = data.get('name', f"Player_{request.sid[:4]}")
    
    # Admin verification
    if role == 'admin':
        if data.get('password') != os.getenv('ADMIN_PASSWORD'):
            emit('auth_response', {'success': False, 'message': 'Invalid admin password'})
            disconnect()
            return
        game_state.admin_sid = request.sid
    
    # Register player
    game_state.players[request.sid] = {'name': name, 'role': role}
    log_player(request.sid, name, role)
    
    emit('auth_response', {
        'success': True,
        'role': role,
        'is_admin': (role == 'admin')
    })
    
    # Broadcast player join
    emit('player_joined', {
        'id': request.sid,
        'name': name,
        'role': role
    }, broadcast=True)
    
    # Send initial game state
    if game_state.game_active:
        emit('game_state_update', {
            'energy': game_state.energy,
            'night': game_state.current_night,
            'doors': game_state.doors
        })

@socketio.on('door_action')
def handle_door(data):
    if request.sid not in game_state.players:
        return
    
    side = data.get('side')
    action = data.get('action')
    
    if side in game_state.doors:
        game_state.doors[side] = (action == 'open')
        emit('door_update', {
            'side': side,
            'state': game_state.doors[side]
        }, broadcast=True)
        
        # Log to database
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO door_events (player_id, door_side, action)
                VALUES (%s, %s, %s)
            """, (request.sid, side, action))
            db.commit()
        except Exception as e:
            print(f"Door log error: {e}")

@socketio.on('animatronic_move')
def handle_anim_move(data):
    if (request.sid not in game_state.players or 
        game_state.players[request.sid]['role'] != 'animatronic'):
        return
    
    anim_type = data.get('type')
    if anim_type in game_state.animatronics:
        game_state.animatronics[anim_type] = {
            'position': data.get('position'),
            'visible': data.get('visible', False)
        }
        
        emit('animatronic_update', {
            'type': anim_type,
            'position': data.get('position'),
            'visible': data.get('visible'),
            'x': data.get('x', 50),
            'y': data.get('y', 50)
        }, broadcast=True)

@socketio.on('admin_start_game')
def handle_start_game():
    if request.sid != game_state.admin_sid:
        emit('error', {'message': 'Admin privileges required'})
        return
    
    game_state.game_active = True
    game_state.start_time = datetime.now()
    
    emit('game_started', {
        'night': game_state.current_night,
        'energy': game_state.energy
    }, broadcast=True)
    
    # Log game start
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO game_sessions (start_time, night_number)
            VALUES (NOW(), %s)
        """, (game_state.current_night,))
        db.commit()
    except Exception as e:
        print(f"Game start log error: {e}")

@socketio.on('request_admin_data')
def handle_admin_data():
    if request.sid == game_state.admin_sid:
        emit('admin_update', {
            'players': [
                {'id': sid, 'name': p['name'], 'role': p['role']}
                for sid, p in game_state.players.items()
            ],
            'game_active': game_state.game_active,
            'night': game_state.current_night,
            'energy': game_state.energy
        })

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in game_state.players:
        player = game_state.players.pop(request.sid)
        emit('player_left', {
            'id': request.sid,
            'name': player['name']
        }, broadcast=True)
        
        if request.sid == game_state.admin_sid:
            game_state.admin_sid = None

# Health Check Endpoint
@app.route('/health')
def health_check():
    return {
        'status': 'online',
        'players': len(game_state.players),
        'game_active': game_state.game_active
    }

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    socketio.run(app, 
                 host='0.0.0.0', 
                 port=port,
                 debug=os.getenv('DEBUG', 'false').lower() == 'true')
