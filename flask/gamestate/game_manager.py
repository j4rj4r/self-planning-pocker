import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from peewee import DoesNotExist

from gamestate.deck import Deck
from gamestate.exceptions import GameDoesNotExistError, DeckDoesNotExistError, GameNotOngoingError
from gamestate.game import Game
from gamestate.models import StoredGame, HistoryEntry
from gamestate.player import Player

DEFAULT_STALE_GAME_TTL = timedelta(days=30)
DEFAULT_MAX_HISTORY_ENTRIES_PER_GAME = 50


class GameManager:
    """Class that manages games"""
    def __init__(self, max_history_entries_per_game: int = DEFAULT_MAX_HISTORY_ENTRIES_PER_GAME):
        self.games = {}
        # player ids whose disconnection has been scheduled but not yet confirmed,
        # giving them a chance to reclaim their seat (e.g. on a page reload) via rejoin
        self.pending_leaves: set[str] = set()
        self.max_history_entries_per_game = max_history_entries_per_game

    def create(self, name: str, deck_name='FIBONACCI') -> str:
        game_uuid = str(uuid.uuid4())
        deck = self.__get_deck(deck_name)
        StoredGame.create(uuid=game_uuid, name=name, deck=deck_name)
        self.games[game_uuid] = Game(name, deck)
        return game_uuid

    def get(self, game_uuid: str) -> Game:
        game = self.games.get(game_uuid)
        if game is None:
            try:
                stored_game = StoredGame.get(StoredGame.uuid == game_uuid)
                game = Game(stored_game.name, Deck[stored_game.deck])
                self.games[game_uuid] = game
            except DoesNotExist:
                raise GameDoesNotExistError(f'Game {game_uuid} does not exist')
        return game

    def __get_ongoing_game(self, game_uuid: str) -> Game:
        game = self.games.get(game_uuid)
        if game is None:
            raise GameNotOngoingError(f'Game {game_uuid} is not ongoing')
        return game
    
    def set_deck(self, game_uuid: str, deck_name: str) -> tuple[dict, dict]:
        deck = self.__get_deck(deck_name)
        game = self.__get_ongoing_game(game_uuid)
        game.set_deck(deck)
        StoredGame.update(deck=deck_name).where(StoredGame.uuid == uuid.UUID(game_uuid)).execute()
        return game.info(), game.state()

    def join_game(self, game_uuid: str, player_id: str, player_name: str, is_spectator: bool) -> tuple[dict, dict]:
        game = self.get(game_uuid)
        player = Player(player_name, is_spectator)
        game.player_joins(player_id, player)
        self.__touch(game_uuid)
        return game.info(), game.state()

    def leave_game(self, game_uuid: str, player_uuid: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.player_leaves(player_uuid)
        if game.is_game_empty():
            self.games.pop(game_uuid)
        return game.state()

    def schedule_leave(self, player_uuid: str) -> None:
        """Marks a player as about to leave, without removing them yet."""
        self.pending_leaves.add(player_uuid)

    def cancel_leave(self, player_uuid: str) -> bool:
        """Cancels a previously scheduled leave (the player reconnected in time).

        Returns True if there was a pending leave to cancel.
        """
        if player_uuid in self.pending_leaves:
            self.pending_leaves.discard(player_uuid)
            return True
        return False

    def confirm_leave(self, game_uuid: str, player_uuid: str) -> Optional[dict]:
        """Finalizes a previously scheduled leave, unless it was cancelled by a rejoin."""
        if player_uuid not in self.pending_leaves:
            return None
        self.pending_leaves.discard(player_uuid)
        return self.leave_game(game_uuid, player_uuid)

    def cleanup_stale_games(self, ttl: timedelta = DEFAULT_STALE_GAME_TTL) -> int:
        """Deletes games that have had no activity for longer than ttl and are not currently in memory.

        Returns the number of games that were removed.
        """
        cutoff = datetime.now(timezone.utc) - ttl
        removed = 0
        for stored_game in StoredGame.select().where(StoredGame.last_active < cutoff):
            game_uuid = str(stored_game.uuid)
            if game_uuid in self.games:
                continue
            HistoryEntry.delete().where(HistoryEntry.game == stored_game.uuid).execute()
            stored_game.delete_instance()
            removed += 1
        return removed

    def rename_game(self, game_uuid: str, game_name: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.name = game_name
        StoredGame.update(name=game_name).where(StoredGame.uuid == uuid.UUID(game_uuid)).execute()
        return game.info()

    def set_player_name(self, game_uuid: str, player_uuid: str, player_name: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        player = game.get_player(player_uuid)
        player.name = player_name
        return game.state()

    def set_player_spectator(self, game_uuid: str, player_uuid: str, is_spectator: bool) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        player = game.get_player(player_uuid)
        player.spectator = is_spectator
        player.clear_hand()
        return game.state()

    def pick_card(self, game_uuid: str, player_uuid: str, pick: Optional[int]) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.player_picks(player_uuid, pick)
        return game.state()

    def reveal_cards(self, game_uuid: str) -> tuple[dict, dict]:
        game = self.__get_ongoing_game(game_uuid)
        game.reveal_hands()
        return game.state(), game.info()

    def end_turn(self, game_uuid: str) -> tuple[dict, dict]:
        game = self.__get_ongoing_game(game_uuid)
        if game.get_revealed():
            self.__record_history(game_uuid, game)
        game.end_turn()
        return game.state(), game.info()

    def get_history(self, game_uuid: str) -> list[dict]:
        self.get(game_uuid)
        entries = (HistoryEntry.select()
                   .where(HistoryEntry.game == uuid.UUID(game_uuid))
                   .order_by(HistoryEntry.recorded_at.desc()))
        return [
            {
                'recordedAt': entry.recorded_at.isoformat(),
                'deck': entry.deck,
                'players': json.loads(entry.results)
            }
            for entry in entries
        ]

    def __record_history(self, game_uuid: str, game: Game) -> None:
        results = [player.state_with_hand() for _, player in game.list_players()]
        HistoryEntry.create(
            game=uuid.UUID(game_uuid),
            deck=game.get_deck().name,
            results=json.dumps(results)
        )
        overflow = (HistoryEntry.select()
                    .where(HistoryEntry.game == uuid.UUID(game_uuid))
                    .count()) - self.max_history_entries_per_game
        if overflow > 0:
            stale_ids = (HistoryEntry.select(HistoryEntry.id)
                         .where(HistoryEntry.game == uuid.UUID(game_uuid))
                         .order_by(HistoryEntry.recorded_at.asc())
                         .limit(overflow))
            HistoryEntry.delete().where(HistoryEntry.id.in_(stale_ids)).execute()

    @staticmethod
    def __get_deck(deck_name) -> Deck:
        if deck_name not in Deck.__members__.keys():
            raise DeckDoesNotExistError(f'Deck {deck_name} does not exist')
        deck = Deck[deck_name]
        return deck

    @staticmethod
    def __touch(game_uuid: str) -> None:
        StoredGame.update(last_active=datetime.now(timezone.utc)) \
            .where(StoredGame.uuid == uuid.UUID(game_uuid)).execute()
    