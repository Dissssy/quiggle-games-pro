import lightbulb
import hikari
import lib
import random


def setup(bot: hikari.GatewayBot, client: lightbulb.Client) -> None:
    @client.register()
    class TicTacToeCommand(
        lightbulb.MessageCommand,
        name="tictactoe",
        description="Start a game of Tic Tac Toe!",
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            message = self.target
            if message is None:
                await ctx.respond("Could not fetch the target message.", ephemeral=True)
                return

            if message.author.is_bot:
                await ctx.respond("Bots cannot play games.", ephemeral=True)
                return
            if message.author.id == ctx.user.id:
                await ctx.respond("You cannot play against yourself!", ephemeral=True)
                return
            invite = lib.GameInvite(
                inviter_id=ctx.user.id,
                invited_id=message.author.id,
                game_name="Tic Tac Toe",
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {message.author.mention} to a game of Tic Tac Toe!",
                user_mentions=[ctx.user.id, message.author.id],
                components=invite.components(bot),
            )

    @bot.listen(hikari.InteractionCreateEvent)
    async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
        if not hasattr(event.interaction, "message"):
            return
        message = event.interaction.message
        if message is None:
            return
        content = message.content
        game_name = lib.header_name(content)
        if game_name != "Tic Tac Toe" and game_name != "TicTacToe":
            return
        invite = lib.GameInvite.from_header(content)
        if invite is None:

            ttt_game = TicTacToeGame.from_header(content)
            if ttt_game is None:
                return
            custom_id = event.interaction.custom_id
            if custom_id.startswith("ttt_move_"):
                parts = custom_id.split("_")
                if len(parts) != 4:
                    print("Invalid ttt_move_ interaction id:", custom_id)
                    return
                try:
                    row = int(parts[2])
                    col = int(parts[3])
                except ValueError:
                    return
                if ttt_game.make_move(event.interaction.user.id, row, col):
                    winner = ttt_game.check_winner()
                    if winner is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=ttt_game.content(),
                            components=ttt_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{ttt_game.to_empty_header()}The game is a tie!",
                            components=ttt_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, hikari.Snowflake):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{ttt_game.to_empty_header()}<@{winner}> has won the game!",
                            components=ttt_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                else:
                    await bot.rest.create_interaction_response(
                        event.interaction,
                        event.interaction.token,
                        hikari.ResponseType.MESSAGE_CREATE,
                        "Invalid move.",
                        flags=hikari.MessageFlag.EPHEMERAL,
                    )
                return
        else:
            if await invite.handle_interaction(event, bot):

                if random.choice([True, False]):
                    ttt_game = TicTacToeGame(invite.invited_id, invite.inviter_id)
                else:
                    ttt_game = TicTacToeGame(invite.inviter_id, invite.invited_id)

                await bot.rest.create_interaction_response(
                    interaction=event.interaction,
                    response_type=hikari.ResponseType.MESSAGE_UPDATE,
                    content=ttt_game.content(),
                    components=ttt_game.components(bot),
                    token=event.interaction.token,
                )
                return


class TicTacToeGame:
    def __init__(
        self,
        player_1: hikari.Snowflake,
        player_2: hikari.Snowflake,
        *,
        current_turn: hikari.Snowflake | None = None,
    ) -> None:
        self.player_x = player_1
        self.player_o = player_2
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.current_turn = current_turn or self.player_x

    def make_move(self, player: hikari.Snowflake, row: int, col: int) -> bool:
        if player in lib.admins():
            player = self.current_turn
        if self.current_turn != player:
            return False
        if self.board[row][col] != " ":
            return False
        self.board[row][col] = "X" if player == self.player_x else "O"
        self.current_turn = (
            self.player_o if self.current_turn == self.player_x else self.player_x
        )
        return True

    def check_winner(self) -> hikari.Snowflake | lib.Tie | None:

        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2] != " ":
                return self.player_x if self.board[i][0] == "X" else self.player_o
            if self.board[0][i] == self.board[1][i] == self.board[2][i] != " ":
                return self.player_x if self.board[0][i] == "X" else self.player_o
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != " ":
            return self.player_x if self.board[0][0] == "X" else self.player_o
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != " ":
            return self.player_x if self.board[0][2] == "X" else self.player_o
        if all(cell != " " for row in self.board for cell in row):
            return lib.Tie()
        return None

    def content(self) -> str:
        header = self.to_header()
        return f"{header}It is <@{self.current_turn}>'s turn! ({'X' if self.current_turn == self.player_x else 'O'})"

    def components(self, bot: hikari.GatewayBot) -> list:
        override_disable = self.check_winner() is not None
        rows = []
        for r in range(3):
            row = bot.rest.build_message_action_row()
            for c in range(3):
                label = self.board[r][c] if self.board[r][c] != " " else "-"
                color = hikari.components.ButtonStyle.SECONDARY
                if self.board[r][c] == "X":
                    color = hikari.components.ButtonStyle.PRIMARY
                elif self.board[r][c] == "O":
                    color = hikari.components.ButtonStyle.DANGER
                row.add_interactive_button(
                    color,
                    f"ttt_move_{r}_{c}",
                    label=label,
                    is_disabled=(self.board[r][c] != " ") or override_disable,
                )
            rows.append(row)
        return rows

    def to_header(self) -> str:
        game_data = {
            "player_x": str(self.player_x),
            "player_o": str(self.player_o),
            "board": self.board,
            "current_turn": str(self.current_turn),
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\nTic Tac Toe\n```"

    def to_empty_header(self) -> str:
        return f"```Tic Tac Toe```"

    @staticmethod
    def from_header(content: str) -> "TicTacToeGame | None":
        header = lib.extract_header(content)
        if header is None:
            return None
        try:
            content = header[3:-3].strip()
            lines = content.splitlines()
            if len(lines) < 2:
                return None
            game_data = lines[0].strip()
            dict_data = lib.deserialize(game_data)
            if dict_data is None:
                return None
            game = TicTacToeGame(
                player_1=hikari.Snowflake(dict_data["player_x"]),
                player_2=hikari.Snowflake(dict_data["player_o"]),
                current_turn=hikari.Snowflake(dict_data["current_turn"]),
            )
            game.board = dict_data["board"]
            return game
        except Exception:
            return None
