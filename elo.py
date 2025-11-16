from sqlite3 import Connection, Cursor
import sqlite3
from typing import Optional
import lib
import hikari

default_elo = 1200


class Change:
    def __init__(
        self, result: lib.Win | lib.Tie | lib.Forfeit, elomap: dict[int, dict[str, int]]
    ):
        self.result = result
        self.elomap = elomap

    def get_new_elo(self, user_id: int) -> Optional[int]:
        if user_id in self.elomap:
            return self.elomap[user_id]["new_elo"]
        return None

    def get_old_elo(self, user_id: int) -> Optional[int]:
        if user_id in self.elomap:
            return self.elomap[user_id]["old_elo"]
        return None

    def get_elo_change(self, user_id: int) -> Optional[int]:
        new_elo = self.get_new_elo(user_id)
        old_elo = self.get_old_elo(user_id)
        if new_elo is not None and old_elo is not None:
            return new_elo - old_elo
        return None


# Abstract handler for Elo rating system, to be used in ALL zero-sum quiggle games.
class EloHandler:
    # db: Connection
    # game_name: str
    def __init__(self, db: Connection, game_name: str) -> None:
        self.db = db
        self.game_name = game_name
        init_table(db, game_name)

    def get_cursor(self) -> Cursor:
        return self.db.cursor()

    def store_user_data(self, user_id: int, username: str, avatar_url: str) -> None:
        cursor = self.get_cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_data (id, username, avatar_url)
            VALUES (?, ?, ?)
            """,
            (user_id, username, str(avatar_url)),
        )
        self.db.commit()

    def _get_elo(self, user_id: int) -> Optional[int]:
        cursor = self.get_cursor()
        cursor.execute(f"SELECT elo FROM {self.game_name} WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        if result is None:
            return None
        return result[0]

    def _set_elo(self, user_id: int, elo: int) -> None:
        cursor = self.get_cursor()
        cursor.execute(
            f"INSERT OR REPLACE INTO {self.game_name} (id, elo) VALUES (?, ?)",
            (user_id, elo),
        )
        self.db.commit()

    def get_elo(self, user_id: int) -> int:
        elo = self._get_elo(user_id)
        if elo is None:
            self._set_elo(user_id, default_elo)
            return default_elo
        return elo

    def get_all_games(self) -> list[tuple[int, int]]:
        if self.game_name == "elo":
            # get all table names in the database except for elo and sqlite internal tables
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'elo' AND name != 'user_data'"
            )
            tables = cursor.fetchall()
            result = []
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                (count,) = cursor.fetchone()
                result.append((table_name, count))
            return result
        else:
            return []

    def get_elo_from_table(self, user_id: int, table_name: str) -> Optional[int]:
        if self.game_name == "elo":
            cursor = self.get_cursor()
            cursor.execute(f"SELECT elo FROM {table_name} WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            if result is None:
                return None
            return result[0]
        else:
            return None

    def record_outcome(self, result: lib.Win | lib.Tie | lib.Forfeit) -> Change:
        if isinstance(result, lib.Win):
            winner_elo = self.get_elo(result.winner_id)
            loser_elo = self.get_elo(result.loser_id)

            expected_win = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
            k = 32
            new_winner_elo = round(winner_elo + k * (1 - expected_win))
            new_loser_elo = round(loser_elo + k * (0 - (1 - expected_win)))

            self._set_elo(result.winner_id, new_winner_elo)
            self._set_elo(result.loser_id, new_loser_elo)
            elomap = {
                result.winner_id: {
                    "old_elo": winner_elo,
                    "new_elo": new_winner_elo,
                },
                result.loser_id: {
                    "old_elo": loser_elo,
                    "new_elo": new_loser_elo,
                },
            }
            return Change(result, elomap)
        elif isinstance(result, lib.Tie):
            player1_elo = self.get_elo(result.player1_id)
            player2_elo = self.get_elo(result.player2_id)

            expected_player1_win = 1 / (1 + 10 ** ((player2_elo - player1_elo) / 400))
            k = 32
            new_player1_elo = round(player1_elo + k * (0.5 - expected_player1_win))
            new_player2_elo = round(
                player2_elo + k * (0.5 - (1 - expected_player1_win))
            )

            self._set_elo(result.player1_id, new_player1_elo)
            self._set_elo(result.player2_id, new_player2_elo)
            elomap = {
                result.player1_id: {
                    "old_elo": player1_elo,
                    "new_elo": new_player1_elo,
                },
                result.player2_id: {
                    "old_elo": player2_elo,
                    "new_elo": new_player2_elo,
                },
            }
            return Change(result, elomap)
        elif isinstance(result, lib.Forfeit):
            # dont penalize a forfeiter as heavily as a normal loss
            winner_elo = self.get_elo(result.winner_id)
            forfeiter_elo = self.get_elo(result.forfeiter_id)

            expected_win = 1 / (1 + 10 ** ((forfeiter_elo - winner_elo) / 400))
            k = 16  # reduced k-factor for forfeits
            new_winner_elo = round(winner_elo + k * (1 - expected_win))
            new_forfeiter_elo = round(forfeiter_elo + k * (0 - (1 - expected_win)))

            self._set_elo(result.winner_id, new_winner_elo)
            self._set_elo(result.forfeiter_id, new_forfeiter_elo)
            elomap = {
                result.winner_id: {
                    "old_elo": winner_elo,
                    "new_elo": new_winner_elo,
                },
                result.forfeiter_id: {
                    "old_elo": forfeiter_elo,
                    "new_elo": new_forfeiter_elo,
                },
            }
            return Change(result, elomap)
        else:
            raise ValueError("Invalid result type")


def init_db(db_path: str = "elo_ratings.db") -> Connection:
    conn = sqlite3.connect(db_path)
    return conn


def init_table(db: Connection, game_name: str) -> None:
    cursor = db.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {game_name} (
            id INTEGER PRIMARY KEY,
            elo INTEGER NOT NULL
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY,
            avatar_url TEXT,
            username TEXT
        )
        """
    )
    db.commit()


def result_embeds(
    change: Change,
) -> list[hikari.Embed]:
    result = change.result
    if isinstance(result, lib.Win):
        embed = hikari.Embed()
        embed.add_field(
            name="Winner",
            value=f"<@{result.winner_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.winner_id)} \u001b[1;32m(+{change.get_elo_change(result.winner_id)})\n```",
            inline=True,
        )
        embed.add_field(
            name="Loser",
            value=f"<@{result.loser_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.loser_id)} \u001b[1;31m({change.get_elo_change(result.loser_id)})\n```",
            inline=True,
        )
    elif isinstance(result, lib.Tie):
        embed = hikari.Embed(title="It's a tie!")
        elo_color = (
            "32"
            if change.get_elo_change(result.player1_id) > 0
            else "31" if change.get_elo_change(result.player1_id) < 0 else "33"
        )
        sign = "+" if change.get_elo_change(result.player1_id) > 0 else ""
        embed.add_field(
            name="Player 1",
            value=f"<@{result.player1_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.player1_id)} \u001b[1;{elo_color}m({sign}{change.get_elo_change(result.player1_id)})\n```",
            inline=True,
        )
        elo_color = (
            "32"
            if change.get_elo_change(result.player2_id) > 0
            else "31" if change.get_elo_change(result.player2_id) < 0 else "33"
        )
        sign = "+" if change.get_elo_change(result.player2_id) > 0 else ""
        embed.add_field(
            name="Player 2",
            value=f"<@{result.player2_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.player2_id)} \u001b[1;{elo_color}m({sign}{change.get_elo_change(result.player2_id)})\n```",
            inline=True,
        )
    elif isinstance(result, lib.Forfeit):
        embed = hikari.Embed(title="Forfeit!")
        embed.add_field(
            name="Winner",
            value=f"<@{result.winner_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.winner_id)} \u001b[1;32m(+{change.get_elo_change(result.winner_id)})\n```",
            inline=True,
        )
        embed.add_field(
            name="Forfeiter",
            value=f"<@{result.forfeiter_id}>\n**Rating:**```ansi\n{change.get_new_elo(result.forfeiter_id)} \u001b[1;31m({change.get_elo_change(result.forfeiter_id)})\n```",
            inline=True,
        )
    else:
        raise ValueError("Invalid result type")

    embed.set_author(
        name="Match Result and Elo Update",
        url=lib.donation_url(),
        icon=lib.donation_logo_url(),
    )

    return [embed]
