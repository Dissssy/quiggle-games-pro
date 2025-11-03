import lightbulb
import hikari
import lib
import random
import chess


def setup(bot: hikari.GatewayBot, client: lightbulb.Client) -> None:
    @client.register()
    class ChessCommand(
        lightbulb.MessageCommand,
        name="chess",
        description="Start a game of Chess!",
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
                game_name="Chess",
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {message.author.mention} to a game of Chess!",
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
        if game_name != "Chess":
            return
        invite = lib.GameInvite.from_header(content)
        if invite is None:

            chess_game = ChessGame.from_header(content)
            if chess_game is None:
                return
            custom_id = event.interaction.custom_id
            if custom_id.startswith("chess_"):
                remainder = custom_id[len("chess_") :]
                resp = chess_game.make_move(
                    event.interaction.user.id, remainder, event.interaction
                )
                if type(resp) == bool and resp:
                    winner = chess_game.check_winner()
                    if winner is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=chess_game.content(),
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{chess_game.to_empty_header()}The game is a tie!",
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(winner, hikari.Snowflake):
                        content = f"{chess_game.to_empty_header()}<@{winner}> has won the game"
                        if chess_game.force_win is not None:
                            content += " by forfeit"
                        content += "!"
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=content,
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                elif type(resp) == lib.MaybeEphemeral:
                    await bot.rest.create_interaction_response(
                        event.interaction,
                        event.interaction.token,
                        hikari.ResponseType.MESSAGE_CREATE,
                        resp.message,
                        flags=hikari.MessageFlag.EPHEMERAL if resp.ephemeral else 0,
                    )
                elif type(resp) == lib.RefreshMessage:
                    await bot.rest.create_interaction_response(
                        interaction=event.interaction,
                        response_type=hikari.ResponseType.MESSAGE_UPDATE,
                        content=chess_game.content(),
                        embeds=chess_game.embeds(),
                        components=chess_game.components(bot),
                        token=event.interaction.token,
                    )
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
                    chess_game = ChessGame(invite.invited_id, invite.inviter_id)
                else:
                    chess_game = ChessGame(invite.inviter_id, invite.invited_id)

                await bot.rest.create_interaction_response(
                    interaction=event.interaction,
                    response_type=hikari.ResponseType.MESSAGE_UPDATE,
                    content=chess_game.content(),
                    embeds=chess_game.embeds(),
                    components=chess_game.components(bot),
                    token=event.interaction.token,
                )
                return


class ChessGame:
    def __init__(
        self,
        player_1: hikari.Snowflake,
        player_2: hikari.Snowflake,
        *,
        current_turn: hikari.Snowflake | None = None,
    ) -> None:
        self.player_w = player_1
        self.player_b = player_2
        self.selected_piece = None
        self.board = chess.Board()
        self.current_turn = current_turn or self.player_w
        self.force_win = None

    def make_move(
        self,
        player: hikari.Snowflake,
        remainder: str,
        interaction: hikari.PartialInteraction,
    ) -> bool | lib.MaybeEphemeral | lib.RefreshMessage:
        if player in lib.admins():
            player = self.current_turn
        command_parts = remainder.split("_")
        if self.selected_piece is not None and len(self.selected_piece) != 2:
            self.selected_piece = None
            return lib.RefreshMessage()
        if self.current_turn != player and command_parts[0] != "remind":
            return lib.MaybeEphemeral("It's not your turn to play!", True)
        if command_parts[0] == "select":
            if len(command_parts) < 2:
                extend_with = (
                    interaction.values if hasattr(interaction, "values") else []
                )
                if len(extend_with) > 0:
                    command_parts.append(extend_with[0])
                else:
                    return lib.RefreshMessage()
            square = command_parts[1]

            square_index = chess.parse_square(square.lower())
            piece = self.board.piece_at(square_index)
            if piece is None:
                return lib.MaybeEphemeral("No piece at that square.", True)
            if (piece.color == chess.WHITE and self.current_turn != self.player_w) or (
                piece.color == chess.BLACK and self.current_turn != self.player_b
            ):
                return lib.MaybeEphemeral("It's not your piece!", True)
            self.selected_piece = square
            return True
        elif command_parts[0] == "move":
            if self.selected_piece is None:
                return lib.MaybeEphemeral("No piece selected.", True)
            if len(command_parts) < 2:
                extend_with = (
                    interaction.values if hasattr(interaction, "values") else []
                )
                if len(extend_with) > 0:
                    command_parts.append(extend_with[0])
                else:
                    return lib.RefreshMessage()
            to_square = command_parts[1]
            uci_move = f"{self.selected_piece}{to_square}"
            move = chess.Move.from_uci(uci_move.lower())
            if move not in self.board.legal_moves:
                return lib.MaybeEphemeral("Illegal move.", True)
            self.board.push(move)
            self.selected_piece = None
            self.current_turn = (
                self.player_b if self.current_turn == self.player_w else self.player_w
            )
            self.cooldown = None
        elif command_parts[0] == "deselect":
            self.selected_piece = None
            return True
        elif command_parts[0] == "remind":
            if self.current_turn == player:
                return lib.MaybeEphemeral("Just make a move!", True)

            return lib.MaybeEphemeral("AHHHHHHHHHHHHHHH", True)
        elif command_parts[0] == "forfeit":
            self.force_win = (
                self.player_b if self.current_turn == self.player_w else self.player_w
            )
        else:
            return lib.RefreshMessage()
        return True

    def check_winner(self) -> hikari.Snowflake | lib.Tie | None:
        if self.force_win is not None:
            return self.force_win
        if self.board.is_checkmate():
            return (
                self.player_b if self.current_turn == self.player_w else self.player_w
            )
        if self.board.is_stalemate() or self.board.is_insufficient_material():
            return lib.Tie()
        return None

    def content(self) -> str:
        header = self.to_header()
        return f"{header}It is <@{self.current_turn}>'s turn! ({'⚪' if self.current_turn == self.player_w else '⚫'})"

    def embeds(self) -> list:
        board_str = self.render_board()
        embed = hikari.Embed(
            description=board_str,
            color=hikari.Color(0x3498DB),
        )
        return [embed]

    def render_board(self) -> str:
        force_red = []
        if self.selected_piece is not None:

            moves = self.get_moves()
            for to_square in moves.get(self.selected_piece, []):
                force_red.append(to_square)
        board_str = ""
        for rank in range(8, 0, -1):
            board_str += lib.number_emoji(rank)
            for file in range(1, 9):
                square_index = chess.square(file - 1, rank - 1)
                piece = self.board.piece_at(square_index)
                if (
                    self.selected_piece is not None
                    and chess.square_name(square_index).upper() in force_red
                ):
                    emoji = get_emoji(file - 1, rank - 1, piece, danger=True)
                else:
                    emoji = get_emoji(file - 1, rank - 1, piece)
                board_str += str(emoji)
            board_str += "\n"
        board_str += lib.application_emoji("quiggle")
        for file in range(1, 9):
            board_str += lib.letter_emoji(file)
        return board_str

    def components(self, bot: hikari.GatewayBot) -> list:
        if self.check_winner() is not None:
            return []
        helper_row = bot.rest.build_message_action_row()
        helper_row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            "chess_remind",
            label="Remind!",
        )
        helper_row.add_interactive_button(
            hikari.ButtonStyle.DANGER,
            "chess_forfeit",
            label="Forfeit",
            emoji=hikari.Emoji.parse("🏳️"),
        )
        helper_row.add_link_button(
            "https://www.youtube.com/watch?v=OCSbzArwB10",
            label="How to Play",
        )
        moves = self.get_moves()

        rows = []
        if self.selected_piece is None:
            working_row = bot.rest.build_message_action_row()

            for square in sorted(moves.keys()):
                piece = self.board.piece_at(chess.parse_square(square.lower()))
                emoji = get_emoji(
                    chess.square_file(chess.parse_square(square.lower())),
                    chess.square_rank(chess.parse_square(square.lower())),
                    piece,
                )
                working_row.add_interactive_button(
                    hikari.ButtonStyle.PRIMARY,
                    f"chess_select_{square}",
                    label=square,
                    emoji=hikari.Emoji.parse(emoji),
                )
                if len(working_row.components) >= 5:
                    rows.append(working_row)
                    working_row = bot.rest.build_message_action_row()
        else:
            working_row = bot.rest.build_message_action_row()

            emoji = get_emoji(
                chess.square_file(chess.parse_square(self.selected_piece.lower())),
                chess.square_rank(chess.parse_square(self.selected_piece.lower())),
                self.board.piece_at(chess.parse_square(self.selected_piece.lower())),
            )
            working_row.add_interactive_button(
                hikari.ButtonStyle.DANGER,
                "chess_deselect",
                emoji=hikari.Emoji.parse(emoji),
                label=f"{self.selected_piece}",
            )

            for square in sorted(moves[self.selected_piece]):
                piece = self.board.piece_at(
                    chess.parse_square(self.selected_piece.lower())
                )
                emoji = get_emoji(
                    chess.square_file(chess.parse_square(square.lower())),
                    chess.square_rank(chess.parse_square(square.lower())),
                    self.board.piece_at(chess.parse_square(square.lower())),
                )
                working_row.add_interactive_button(
                    hikari.ButtonStyle.SUCCESS,
                    f"chess_move_{square}",
                    label=square,
                    emoji=hikari.Emoji.parse(emoji),
                )
                if len(working_row.components) >= 5:
                    rows.append(working_row)
                    working_row = bot.rest.build_message_action_row()
        if len(working_row.components) > 0:
            rows.append(working_row)
        if len(rows) > 4:

            rows = []
            piece_selector_row = bot.rest.build_message_action_row()
            piece_selector = piece_selector_row.add_text_menu(
                "chess_select",
                placeholder="Select a piece to move",
            )
            for square in sorted(moves.keys()):
                piece = self.board.piece_at(chess.parse_square(square.lower()))
                piece_selector.add_option(
                    f"{square} ({piece_name(piece.symbol()).capitalize()})",
                    f"{square}",
                    is_default=(self.selected_piece == square),
                )
            rows.append(piece_selector_row)
            if self.selected_piece is not None:
                move_selector_row = bot.rest.build_message_action_row()
                move_selector = move_selector_row.add_text_menu(
                    "chess_move_dropdown",
                    placeholder="Select a square to move to",
                )
                i = 1
                for square in sorted(moves[self.selected_piece]):
                    i += 1
                    move_selector.add_option(
                        f"Move {piece_name(self.board.piece_at(chess.parse_square(self.selected_piece.lower())).symbol())} to {square}",
                        f"{square}",
                    )
                    if i >= 25:
                        rows.append(move_selector_row)
                        move_selector_row = bot.rest.build_message_action_row()
                        move_selector = move_selector_row.add_text_menu(
                            "chess_move_dropdown_cont",
                            placeholder="Select a square to move to (cont.)",
                        )
                        i = 1
                rows.append(move_selector_row)
        rows.append(helper_row)
        return rows

    def get_moves(self) -> dict:
        moves = {}
        for move in self.board.legal_moves:
            uci_move = move.uci().upper()
            from_square = uci_move[0:2]
            to_square = uci_move[2:4]
            if moves.get(from_square) is None:
                moves[from_square] = set()
            moves[from_square].add(to_square)
        return moves

    def to_header(self) -> str:
        game_data = {
            "player_w": str(self.player_w),
            "player_b": str(self.player_b),
            "board": str(self.board.fen()),
            "selected_piece": str(self.selected_piece),
            "current_turn": str(self.current_turn),
            "force_win": str(self.force_win),
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\nChess\n```"

    def to_empty_header(self) -> str:
        return f"```Chess```"

    @staticmethod
    def from_header(content: str) -> "ChessGame | None":
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
            game = ChessGame(
                player_1=hikari.Snowflake(dict_data["player_w"]),
                player_2=hikari.Snowflake(dict_data["player_b"]),
                current_turn=hikari.Snowflake(dict_data["current_turn"]),
            )
            game.board = chess.Board(fen=dict_data["board"])
            game.selected_piece = dict_data["selected_piece"]
            if game.selected_piece == "None":
                game.selected_piece = None
            game.force_win = dict_data.get("force_win", None)
            if game.force_win == "None":
                game.force_win = None
            return game
        except Exception:
            return None


def get_emoji(
    x: int, y: int, piece: chess.PieceType | None, *, danger: bool = False
) -> hikari.Emoji:
    is_black_square = (x + y) % 2 == 1
    square_color = "black" if is_black_square else "red"
    if piece is None:

        if square_color == "black":
            if danger:
                return lib.application_emoji("green_danger")
            else:
                return lib.application_emoji("green")
        elif square_color == "red":
            if danger:
                return lib.application_emoji("white_danger")
            else:
                return lib.application_emoji("white")
        else:
            return lib.application_emoji("quiggle")

    color = "w" if piece.color == chess.WHITE else "b"
    symbol = piece.symbol().upper()
    background = "g" if is_black_square else "w"
    emoji_name = f"{color}{symbol}{background}"
    if danger:
        emoji_name += "_danger"
    return lib.application_emoji(emoji_name)


def piece_name(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol == "K":
        return "King"
    elif symbol == "Q":
        return "Queen"
    elif symbol == "R":
        return "Rook"
    elif symbol == "B":
        return "Bishop"
    elif symbol == "N":
        return "Knight"
    elif symbol == "P":
        return "Pawn"
    return "Unknown"
