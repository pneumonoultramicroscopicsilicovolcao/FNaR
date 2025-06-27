class GameState:
    def __init__(self):
        self.players = {}
        self.admin_sid = None
        self.game_active = False
        self.current_night = 1
        self.energy = 240
        self.doors = {"left": False, "right": False}

    def set_admin(self, sid):
        self.admin_sid = sid

    def is_admin(self, sid):
        return sid == self.admin_sid

    def add_player(self, sid, role, name):
        self.players[sid] = {"role": role, "name": name}

    def remove_player(self, sid):
        return self.players.pop(sid, None)

    def start_game(self):
        self.game_active = True
        return True

    def end_game(self):
        self.game_active = False
        return True

    def get_player_list(self):
        return [
            {"id": sid, "name": data["name"], "role": data["role"]}
            for sid, data in self.players.items()
        ]

    def validate_player(self, sid):
        return sid in self.players

    def validate_move(self, data):
        # Implement your animatronic movement rules here
        return True

    def update_door(self, side, action):
        if side in self.doors:
            self.doors[side] = (action == "open")
