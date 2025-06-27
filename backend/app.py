import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room, disconnect
from game_state import GameState
import eventlet
from datetime import datetime

# Required for WebSocket support on Render
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret_123')

# Configure Socket.IO with CORS and async mode
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=True,
                   engineio_logger=True)

game_state = GameState()

# --------------------------
# Authentication Endpoints
# --------------------------

@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "online",
        "time": datetime.now().isoformat(),
        "players": len(game_state.players)
    })

@socketio.on('connect')
def handle_connect():
    print(f"New connection: {request.sid}")

@socketio.on('authenticate')
def handle_auth(data):
    role = data.get('role')
    name = data.get('name', 'Anonymous')
    password = data.get('password', '')

    # Admin authentication
    if role == 'admin':
        if password != os.getenv('ADMIN_PASSWORD'):
            emit('auth_response', {
                "success": False,
                "message": "Invalid admin password"
            })
            disconnect()
            return

        game_state.set_admin(request.sid)
        emit('auth_response', {
            "success": True,
            "role": "admin",
            "is_admin": True
        })
        emit('admin_update', {
            "players": game_state.get_player_list(),
            "game_active": game_state.game_active
        }, room=request.sid)
        return

    # Player authentication
    if game_state.game_active:
        emit('auth_response', {
            "success": False,
            "message": "Game already in progress"
        })
        disconnect()
        return

    game_state.add_player(request.sid, role, name)
    emit('auth_response', {
        "success": True,
        "role": role,
        "is_admin": False
    })
    emit('player_joined', {
        "id": request.sid,
        "name": name,
        "role": role
    }, broadcast=True)

# --------------------------
# Game Control Endpoints
# --------------------------

@socketio.on('start_game')
def handle_start_game():
    if not game_state.is_admin(request.sid):
        emit('error', {"message": "Admin privileges required"})
        return

    if game_state.game_active:
        emit('error', {"message": "Game already running"})
        return

    game_state.start_game()
    emit('game_started', {
        "night": game_state.current_night,
        "energy": game_state.energy
    }, broadcast=True)

@socketio.on('end_game')
def handle_end_game():
    if not game_state.is_admin(request.sid):
        emit('error', {"message": "Admin privileges required"})
        return

    game_state.end_game()
    emit('game_ended', broadcast=True)

# --------------------------
# Player Actions
# --------------------------

@socketio.on('door_action')
def handle_door(data):
    if not game_state.validate_player(request.sid):
        disconnect()
        return

    side = data.get('side')
    action = data.get('action')
    game_state.update_door(side, action)
    emit('door_update', data, broadcast=True)

@socketio.on('animatronic_move')
def handle_anim_move(data):
    player = game_state.get_player(request.sid)
    if not player or player['role'] != 'animatronic':
        return

    if game_state.validate_move(data):
        emit('animatronic_update', {
            "type": data['type'],
            "location": data['location'],
            "player_id": request.sid
        }, broadcast=True)

# --------------------------
# Admin Controls
# --------------------------

@socketio.on('request_player_list')
def handle_player_list_request():
    if game_state.is_admin(request.sid):
        emit('player_list_update', {
            "players": game_state.get_player_list(),
            "game_active": game_state.game_active
        })

@socketio.on('kick_player')
def handle_kick_player(data):
    if not game_state.is_admin(request.sid):
        return

    player_id = data.get('player_id')
    if player_id in game_state.players:
        emit('kicked', {}, room=player_id)
        disconnect(player_id)

# --------------------------
# Connection Cleanup
# --------------------------

@socketio.on('disconnect')
def handle_disconnect():
    player = game_state.remove_player(request.sid)
    if player:
        emit('player_left', {
            "id": request.sid,
            "name": player['name'],
            "role": player['role']
        }, broadcast=True)

    if game_state.is_admin(request.sid):
        game_state.admin_sid = None

# --------------------------
# Main Execution
# --------------------------

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    socketio.run(app,
                host='0.0.0.0',
                port=port,
                debug=os.getenv('DEBUG', 'false').lower() == 'true')
