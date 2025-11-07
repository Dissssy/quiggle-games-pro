import lightbulb
import hikari
import lib
import random
import elo


def setup(
    bot: hikari.GatewayBot, client: lightbulb.Client, elo_handler: elo.EloHandler
) -> None:
    @client.register()
    class BattleshipCommand(
        lightbulb.MessageCommand,
        name="battleship",
        description="Start a game of Battleship!",
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
                game_name="Battleship",
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {message.author.mention} to a game of Battleship!",
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
        if game_name != "Battleship" and game_name != "Battleship":
            return
        invite = lib.GameInvite.from_header(content)
        if invite is None:

            bs_game = BattleshipGame.from_header(content)
            if bs_game is None:
                return
            custom_id = event.interaction.custom_id
            if custom_id.startswith("bs_move_"):
                parts = custom_id.split("_")
                if len(parts) != 4:
                    print("Invalid bs_move_ interaction id:", custom_id)
                    return
                try:
                    row = int(parts[2])
                    col = int(parts[3])
                except ValueError:
                    return
                if bs_game.make_move(event.interaction.user.id, row, col):
                    winner = bs_game.check_winner()
                    if winner is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=bs_game.content(),
                            components=bs_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{bs_game.to_empty_header()}The game is a tie!",
                            components=bs_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, hikari.Snowflake):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{bs_game.to_empty_header()}<@{winner}> has won the game!",
                            components=bs_game.components(bot),
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
                    bs_game = BattleshipGame(invite.invited_id, invite.inviter_id)
                else:
                    bs_game = BattleshipGame(invite.inviter_id, invite.invited_id)

                await bot.rest.create_interaction_response(
                    interaction=event.interaction,
                    response_type=hikari.ResponseType.MESSAGE_UPDATE,
                    content=bs_game.content(),
                    components=bs_game.components(bot),
                    token=event.interaction.token,
                )
                return


class BattleshipGame:
    def __init__(
        self,
        player_1: hikari.Snowflake,
        player_2: hikari.Snowflake,
        *,
        current_turn: hikari.Snowflake | None = None,
    ) -> None:
        self.player_1 = player_1
        self.player_2 = player_2
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.current_turn = current_turn or self.player_1

    def make_move(self, player: hikari.Snowflake, row: int, col: int) -> bool:
        if player in lib.admins():
            player = self.current_turn
        if self.current_turn != player:
            return False
        if self.board[row][col] != " ":
            return False
        self.board[row][col] = "X" if player == self.player_1 else "O"
        self.current_turn = (
            self.player_2 if self.current_turn == self.player_1 else self.player_1
        )
        return True

    def check_winner(self) -> hikari.Snowflake | lib.Tie | None:

        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2] != " ":
                return self.player_1 if self.board[i][0] == "X" else self.player_2
            if self.board[0][i] == self.board[1][i] == self.board[2][i] != " ":
                return self.player_1 if self.board[0][i] == "X" else self.player_2
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != " ":
            return self.player_1 if self.board[0][0] == "X" else self.player_2
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != " ":
            return self.player_1 if self.board[0][2] == "X" else self.player_2
        if all(cell != " " for row in self.board for cell in row):
            return lib.Tie()
        return None

    def content(self) -> str:
        header = self.to_header()
        return f"{header}It is <@{self.current_turn}>'s turn! ({'X' if self.current_turn == self.player_1 else 'O'})"

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
                    f"bs_move_{r}_{c}",
                    label=label,
                    is_disabled=(self.board[r][c] != " ") or override_disable,
                )
            rows.append(row)
        return rows

    def to_header(self) -> str:
        game_data = {
            "player_1": str(self.player_1),
            "player_2": str(self.player_2),
            "board": self.board,
            "current_turn": str(self.current_turn),
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\nBattleship\n```"

    def to_empty_header(self) -> str:
        return f"```Battleship```"

    @staticmethod
    def from_header(content: str) -> "BattleshipGame | None":
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
            game = BattleshipGame(
                player_1=hikari.Snowflake(dict_data["player_1"]),
                player_2=hikari.Snowflake(dict_data["player_2"]),
                current_turn=hikari.Snowflake(dict_data["current_turn"]),
            )
            game.board = dict_data["board"]
            return game
        except Exception:
            return None
