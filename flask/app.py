import errno
import os
import sys
import uuid
from datetime import timedelta

from flask import Flask, request, session, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, leave_room, emit
from peewee import SqliteDatabase, OperationalError

from permission_check import check_db_file_permissions
from gamestate.exceptions import PlanningPokerException, GameDoesNotExistError
from gamestate.game_manager import GameManager
from gamestate.models import database_proxy, ensure_schema

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

if app.config['DEBUG']:
    real_db = SqliteDatabase('database.db')
    socketio = SocketIO(app, cors_allowed_origins=[
        'http://localhost:4200', 'http://localhost:5000',
        'http://127.0.0.1:4200', 'http://127.0.0.1:5000'
    ])
    CORS(app)
else:
    check_db_file_permissions()
    real_db = SqliteDatabase('/data/database.db')
    socketio = SocketIO(app)
database_proxy.initialize(real_db)
if database_proxy.is_closed():
    database_proxy.connect()
ensure_schema()

gm = GameManager()

app_root = os.getenv('APP_ROOT', '/')
if not app_root.endswith('/'):
    app_root += '/'

# How long a disconnected player's seat is kept before being removed, to survive a quick
# page reload (which disconnects then reconnects) without showing a duplicate/ghost player.
DISCONNECT_GRACE_SECONDS = int(os.getenv('DISCONNECT_GRACE_SECONDS', '10'))
# How long an idle game (not currently loaded by any server process) is kept before being deleted.
STALE_GAME_TTL = timedelta(days=int(os.getenv('STALE_GAME_TTL_DAYS', '30')))
STALE_GAME_CLEANUP_INTERVAL_SECONDS = 60 * 60


def cleanup_stale_games_periodically():
    while True:
        socketio.sleep(STALE_GAME_CLEANUP_INTERVAL_SECONDS)
        gm.cleanup_stale_games(STALE_GAME_TTL)


socketio.start_background_task(cleanup_stale_games_periodically)


@app.route('/create', methods=['POST'])
def create():
    body = request.json
    game_name = body['name']
    game_deck = body['deck']
    return gm.create(game_name, game_deck)


@app.route('/<string:file>.<string:ext>')
def serve_file(file, ext):
    return app.send_static_file(f'{file}.{ext}')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    spy = request.args.get('spy')
    session['spy'] = spy is not None and spy not in ('0', 'false')
    return render_template('index.html', app_root=app_root)


@app.route('/favicon.ico')
def serve_icon():
    return app.send_static_file('favicon/favicon.ico')

@app.route('/assets/<path:path>')
def serve_assets(path):
    return app.send_static_file(f'assets/{path}')

def emit_state(game_id, state, emit_fn=emit):
    emit_fn('state', state, to=game_id, json=True)
    game = gm.get(game_id)
    spies = game.get_spies()
    if spies:
        full_state = game.full_state()
        for spy_id in spies:
            emit_fn('state', full_state, to=spy_id, json=True)


@socketio.event
def join(data):
    player_id = str(uuid.uuid4())
    session['player_id'] = player_id
    player_name = data['name']
    spectator = data['spectator']
    game_id = data['game']

    session['game_id'] = game_id
    join_room(game_id)
    join_room(player_id)

    info, state = gm.join_game(game_id, player_id, player_name, spectator)
    if session.get('spy'):
        gm.get(game_id).add_spy(player_id)
    else:
        gm.get(game_id).remove_spy(player_id)
    emit_state(game_id, state)

    info['playerId'] = player_id
    return info


@socketio.event
def rejoin(data):
    """Like join, but reclaims a previous seat (and its vote) if it hasn't been removed yet."""
    game_id = data['game']
    previous_player_id = data.get('playerId')

    if previous_player_id and gm.cancel_leave(previous_player_id):
        try:
            game = gm.get(game_id)
        except GameDoesNotExistError:
            game = None
        if game is not None and previous_player_id in game.list_players_uuid():
            session['player_id'] = previous_player_id
            session['game_id'] = game_id
            join_room(game_id)
            join_room(previous_player_id)
            if session.get('spy'):
                game.add_spy(previous_player_id)
            else:
                game.remove_spy(previous_player_id)
            emit_state(game_id, game.state())

            info = game.info()
            info['playerId'] = previous_player_id
            return info

    return join(data)


@socketio.event
def disconnect():
    player_id = session.get('player_id')
    game_id = session.get('game_id')
    if not player_id or not game_id:
        return

    leave_room(game_id)
    leave_room(player_id)
    gm.schedule_leave(player_id)
    socketio.start_background_task(finalize_leave, game_id, player_id)

    session['player_id'] = None
    session['game_id'] = None


def finalize_leave(game_id, player_id):
    socketio.sleep(DISCONNECT_GRACE_SECONDS)
    try:
        state = gm.confirm_leave(game_id, player_id)
        if state is not None:
            emit_state(game_id, state, emit_fn=socketio.emit)
    except PlanningPokerException:
        pass


@socketio.event
def rename_game(data):
    game_id = session['game_id']
    game_name = data['name']

    info = gm.rename_game(game_id, game_name)
    emit('info', info, to=game_id, json=True)


@socketio.event
def set_deck(data):
    game_id = session['game_id']
    deck_name = data['deck']

    info, state = gm.set_deck(game_id, deck_name)
    emit('info', info, to=game_id, json=True)
    emit_state(game_id, state)


@socketio.event
def set_player_name(data):
    player_id = session['player_id']
    game_id = session['game_id']
    player_name = data['name']

    state = gm.set_player_name(game_id, player_id, player_name)
    emit_state(game_id, state)


@socketio.event
def set_spectator(data):
    player_id = session['player_id']
    game_id = session['game_id']
    is_spectator = data['spectator']

    state = gm.set_player_spectator(game_id, player_id, is_spectator)
    emit_state(game_id, state)


@socketio.event
def pick_card(data):
    player_id = session['player_id']
    game_id = session['game_id']
    card = data['card']

    state = gm.pick_card(game_id, player_id, card)
    emit_state(game_id, state)


@socketio.event
def reveal_cards():
    game_id = session['game_id']

    state, info = gm.reveal_cards(game_id)
    emit_state(game_id, state)
    emit('info', info, to=game_id, json=True)


@socketio.event
def end_turn():
    game_id = session['game_id']

    state, info = gm.end_turn(game_id)
    emit_state(game_id, state)
    emit('info', info, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.on_error()
def on_error_handler(e):
    body = {'error': True, 'message': str(e), 'code': 0}
    if isinstance(e, PlanningPokerException):
        body['code'] = e.code
    return body


if __name__ == '__main__':
    socketio.run(app)
