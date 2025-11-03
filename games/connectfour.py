import lightbulb
import hikari
import lib
import random


def setup(bot: hikari.GatewayBot, client: lightbulb.Client) -> None:
    @client.register()
    class ConnectFourCommand(
        lightbulb.MessageCommand,
        name="connectfour",
        description="Start a game of Connect Four!",
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
                game_name="Connect Four",
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {message.author.mention} to a game of Connect Four!",
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
        if game_name != "Connect Four" and game_name != "ConnectFour":
            return
        invite = lib.GameInvite.from_header(content)
        if invite is None:

            c4_game = ConnectFourGame.from_header(content)
            if c4_game is None:
                return
            custom_id = event.interaction.custom_id
            if custom_id.startswith("c4_move_"):
                parts = custom_id.split("_")
                if len(parts) != 3:
                    print("Invalid c4_move_ interaction id:", custom_id)
                    return
                try:
                    col = int(parts[2])
                except ValueError:
                    print("Invalid column in c4_move_ interaction id:", custom_id)
                    return
                if c4_game.make_move(event.interaction.user.id, col):
                    winner = c4_game.check_winner()
                    if winner is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=c4_game.content(),
                            embeds=c4_game.embeds(),
                            components=c4_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{c4_game.to_empty_header()}The game is a tie!",
                            embeds=c4_game.embeds(),
                            components=c4_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, hikari.Snowflake):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{c4_game.to_empty_header()}<@{winner}> has won the game!",
                            embeds=c4_game.embeds(),
                            components=c4_game.components(bot),
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
            elif custom_id == "c4_quiggle":
                await bot.rest.create_interaction_response(
                    event.interaction,
                    event.interaction.token,
                    hikari.ResponseType.MESSAGE_CREATE,
                    "(heehee that tickles!)>" + lib.application_emoji("quiggle"),
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return
        else:
            if await invite.handle_interaction(event, bot):

                if random.choice([True, False]):
                    c4_game = ConnectFourGame(invite.invited_id, invite.inviter_id)
                else:
                    c4_game = ConnectFourGame(invite.inviter_id, invite.invited_id)

                await bot.rest.create_interaction_response(
                    interaction=event.interaction,
                    response_type=hikari.ResponseType.MESSAGE_UPDATE,
                    content=c4_game.content(),
                    embeds=c4_game.embeds(),
                    components=c4_game.components(bot),
                    token=event.interaction.token,
                )
                return


class ConnectFourGame:
    def __init__(
        self,
        player_1: hikari.Snowflake,
        player_2: hikari.Snowflake,
        *,
        current_turn: hikari.Snowflake | None = None,
    ) -> None:
        self.player_r = player_1
        self.player_y = player_2
        self.board = [[" " for _ in range(7)] for _ in range(6)]
        self.current_turn = current_turn or self.player_r

    def make_move(self, player: hikari.Snowflake, col: int) -> bool:
        if player in lib.admins():
            player = self.current_turn
        if self.current_turn != player:
            return False

        for row in reversed(range(6)):
            if self.board[row][col] == " ":
                self.board[row][col] = "R" if player == self.player_r else "Y"
                break
        else:
            return False
        self.current_turn = (
            self.player_y if self.current_turn == self.player_r else self.player_r
        )
        return True

    def get_all_winning_positions(self) -> list[tuple[int, int]]:
        winning_positions = []

        for r in range(6):
            for c in range(4):
                if (
                    self.board[r][c] != " "
                    and self.board[r][c]
                    == self.board[r][c + 1]
                    == self.board[r][c + 2]
                    == self.board[r][c + 3]
                ):
                    winning_positions.extend(
                        [(r, c), (r, c + 1), (r, c + 2), (r, c + 3)]
                    )
        for c in range(7):
            for r in range(3):
                if (
                    self.board[r][c] != " "
                    and self.board[r][c]
                    == self.board[r + 1][c]
                    == self.board[r + 2][c]
                    == self.board[r + 3][c]
                ):
                    winning_positions.extend(
                        [(r, c), (r + 1, c), (r + 2, c), (r + 3, c)]
                    )
        for r in range(3):
            for c in range(4):
                if (
                    self.board[r][c] != " "
                    and self.board[r][c]
                    == self.board[r + 1][c + 1]
                    == self.board[r + 2][c + 2]
                    == self.board[r + 3][c + 3]
                ):
                    winning_positions.extend(
                        [(r, c), (r + 1, c + 1), (r + 2, c + 2), (r + 3, c + 3)]
                    )
        for r in range(3, 6):
            for c in range(4):
                if (
                    self.board[r][c] != " "
                    and self.board[r][c]
                    == self.board[r - 1][c + 1]
                    == self.board[r - 2][c + 2]
                    == self.board[r - 3][c + 3]
                ):
                    winning_positions.extend(
                        [(r, c), (r - 1, c + 1), (r - 2, c + 2), (r - 3, c + 3)]
                    )
        return winning_positions

    def check_winner(self) -> hikari.Snowflake | lib.Tie | None:
        winning_positions = self.get_all_winning_positions()
        if winning_positions:
            winner_piece = self.board[winning_positions[0][0]][winning_positions[0][1]]
            if winner_piece == "R":
                return self.player_r
            else:
                return self.player_y
        elif all(cell != " " for row in self.board for cell in row):
            return lib.Tie()
        else:
            return None

    def content(self) -> str:
        header = self.to_header()
        return f"{header}It is <@{self.current_turn}>'s turn! {lib.application_emoji('c4_red_piece') if self.current_turn == self.player_r else lib.application_emoji('c4_yellow_piece')}"

    def embeds(self) -> list[hikari.Embed]:
        embed = hikari.Embed(
            description=self.board_str(),
            color=hikari.Color(0xFFAA00),
        )
        return [embed]

    def board_str(self) -> str:

        board_lines = []
        winning_positions = self.get_all_winning_positions()

        top_border = lib.application_emoji("c4_border_top_left")
        for i in range(7):
            top_border += lib.application_emoji(f"c4_border_top_{i + 1}")
        top_border += lib.application_emoji("c4_border_top_right")
        board_lines.append(top_border)

        for row_index, row in enumerate(self.board):
            row_str = lib.application_emoji("c4_border_left")
            for col_index, cell in enumerate(row):
                if cell == "R":
                    if (row_index, col_index) in winning_positions:
                        row_str += lib.application_emoji("c4_red_winner")
                    else:
                        row_str += str(lib.application_emoji("c4_red"))
                elif cell == "Y":
                    if (row_index, col_index) in winning_positions:
                        row_str += lib.application_emoji("c4_yellow_winner")
                    else:
                        row_str += str(lib.application_emoji("c4_yellow"))
                else:
                    row_str += str(lib.application_emoji("c4_empty"))
            row_str += lib.application_emoji("c4_border_right")
            board_lines.append(row_str)

        bottom_border_str = lib.application_emoji("c4_border_bottom_left")
        for i in range(7):
            bottom_border_str += lib.application_emoji(f"c4_border_bottom_{i + 1}")
        bottom_border_str += lib.application_emoji("c4_border_bottom_right")
        board_lines.append(bottom_border_str)
        return "\n".join(board_lines)

    def components(self, bot: hikari.GatewayBot) -> list:
        rows = []
        if self.check_winner() is not None:
            return rows
        row = bot.rest.build_message_action_row()
        for c in range(4):
            row.add_interactive_button(
                hikari.components.ButtonStyle.SECONDARY,
                f"c4_move_{c}",
                emoji=hikari.Emoji.parse(lib.number_emoji(c + 1)),
                is_disabled=self.board[0][c] != " ",
            )
        rows.append(row)
        row = bot.rest.build_message_action_row()
        for c in range(4, 7):
            row.add_interactive_button(
                hikari.components.ButtonStyle.SECONDARY,
                f"c4_move_{c}",
                emoji=hikari.Emoji.parse(lib.number_emoji(c + 1)),
                is_disabled=self.board[0][c] != " ",
            )
        row.add_interactive_button(
            hikari.components.ButtonStyle.SUCCESS,
            "c4_quiggle",
            emoji=hikari.Emoji.parse(lib.application_emoji("quiggle")),
        )
        rows.append(row)

        return rows

    def to_header(self) -> str:
        game_data = {
            "player_r": str(self.player_r),
            "player_y": str(self.player_y),
            "board": self.board,
            "current_turn": str(self.current_turn),
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\nConnect Four\n```"

    def to_empty_header(self) -> str:
        return f"```Connect Four```"

    @staticmethod
    def from_header(content: str) -> "ConnectFourGame | None":
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
            game = ConnectFourGame(
                player_1=hikari.Snowflake(dict_data["player_r"]),
                player_2=hikari.Snowflake(dict_data["player_y"]),
                current_turn=hikari.Snowflake(dict_data["current_turn"]),
            )
            game.board = dict_data["board"]
            return game
        except Exception:
            return None
