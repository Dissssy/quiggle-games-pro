import lightbulb
import hikari
import lib
import random
import chess
import elo


def setup(
    bot: hikari.GatewayBot, client: lightbulb.Client, elo_handler: elo.EloHandler
) -> None:
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
            user = message.author
            elo_handler.store_user_data(
                user_id=user.id,
                username=lib.get_username(user),
                avatar_url=user.display_avatar_url or user.default_avatar_url,
            )
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

    @client.register()
    class ChessSlashCommand(
        lightbulb.SlashCommand,
        name="chess",
        description="Start a game of Chess!",
    ):
        target = lightbulb.user(
            "target",
            "The user to challenge to a game of Chess.",
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            user = self.target or ctx.user
            if user.is_bot:
                await ctx.respond("Bots cannot play games.", ephemeral=True)
                return
            elo_handler.store_user_data(
                user_id=user.id,
                username=lib.get_username(user),
                avatar_url=user.display_avatar_url or user.default_avatar_url,
            )
            if user.id == ctx.user.id:
                await ctx.respond("You cannot play against yourself!", ephemeral=True)
                return
            invite = lib.GameInvite(
                inviter_id=ctx.user.id,
                invited_id=user.id,
                game_name="Chess",
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {user.mention} to a game of Chess!",
                user_mentions=[ctx.user.id, user.id],
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
                    event.interaction.user.id, remainder, event.interaction, elo_handler
                )
                if type(resp) == bool and resp:
                    outcome = chess_game.check_outcome()
                    if outcome is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=chess_game.content(),
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{chess_game.to_empty_header()}The game is a tie!",
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Win):
                        content = f"{chess_game.to_empty_header()}<@{outcome.winner_id}> has won the game!"
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=content,
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Forfeit):
                        content = f"{chess_game.to_empty_header()}<@{outcome.winner_id}> has won the game by forfeit!"
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
                    if resp.resend:
                        # TODO: delete old message?
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content="Game resent!",
                            embeds=[],
                            components=[],
                            token=event.interaction.token,
                        )

                        # await bot.rest.create_interaction_response(
                        #     interaction=event.interaction,
                        #     response_type=hikari.ResponseType.DEFERRED_MESSAGE_CREATE,
                        #     token=event.interaction.token,
                        # )

                        await bot.rest.execute_webhook(
                            webhook=event.interaction.application_id,
                            token=event.interaction.token,
                            content=chess_game.content(),
                            embeds=chess_game.embeds(),
                            components=chess_game.components(bot),
                        )
                    else:
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
        # self.last_move = None
        self.last_fen = None
        self.undo_vote = None
        self.truce_offer = None

    def make_move(
        self,
        player: hikari.Snowflake,
        remainder: str,
        interaction: hikari.PartialInteraction,
        elo_handler: elo.EloHandler,
    ) -> bool | lib.MaybeEphemeral | lib.RefreshMessage:
        if player in lib.admins():
            player = self.current_turn
        command_parts = remainder.split("_")
        if self.selected_piece is not None and len(self.selected_piece) != 2:
            self.selected_piece = None
            return lib.RefreshMessage()
        if self.current_turn != player and command_parts[0] in [
            "select",
            "move",
            "deselect",
        ]:
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
                # return lib.MaybeEphemeral("It's not your piece!", True)
                self.board.turn = not self.board.turn
                return lib.RefreshMessage()
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
            if to_square == "dropdown" or to_square == "dropdown_cont":
                to_square = interaction.values[0]
            if self.next_move_is_promotion():
                # expecting format: move_<to_square>_promote_<piece>
                if len(command_parts) < 4 or command_parts[2] != "promote":
                    return lib.MaybeEphemeral("Promotion piece not specified.", True)
                promotion_piece_str = command_parts[3].lower()
                promotion_piece = None
                if promotion_piece_str == "queen":
                    promotion_piece = chess.QUEEN
                elif promotion_piece_str == "rook":
                    promotion_piece = chess.ROOK
                elif promotion_piece_str == "bishop":
                    promotion_piece = chess.BISHOP
                elif promotion_piece_str == "knight":
                    promotion_piece = chess.KNIGHT
                if promotion_piece is None:
                    return lib.MaybeEphemeral("Invalid promotion piece.", True)
                uci_move = f"{self.selected_piece}{to_square}{chess.piece_symbol(promotion_piece).lower()}"
                move = chess.Move.from_uci(uci_move.lower())
                if move not in self.board.legal_moves:
                    return lib.MaybeEphemeral("Illegal move.", True)
                self.last_fen = self.board.fen()
                self.board.push(move)
                self.selected_piece = None
                # self.last_move = uci_move.upper()
                self.current_turn = (
                    self.player_b
                    if self.current_turn == self.player_w
                    else self.player_w
                )
                self.cooldown = None
            else:
                uci_move = f"{self.selected_piece}{to_square}"
                move = chess.Move.from_uci(uci_move.lower())
                if move not in self.board.legal_moves:
                    return lib.MaybeEphemeral("Illegal move.", True)
                self.last_fen = self.board.fen()
                self.board.push(move)
                self.selected_piece = None
                # self.last_move = uci_move.upper()
                self.current_turn = (
                    self.player_b
                    if self.current_turn == self.player_w
                    else self.player_w
                )
                self.cooldown = None
        elif command_parts[0] == "deselect":
            self.selected_piece = None
            return True
        elif command_parts[0] == "remind" or command_parts[0] == "resend":  # legacy
            # if self.current_turn == player:
            #     return lib.MaybeEphemeral("Just make a move!", True)

            # return lib.MaybeEphemeral("AHHHHHHHHHHHHHHH", True)
            return lib.RefreshMessage(resend=True)
        elif command_parts[0] == "forfeit":
            # self.force_win = (
            #     self.player_b if self.current_turn == self.player_w else self.player_w
            # )
            self.force_win = lib.Forfeit(forfeiter_id=player)
        elif command_parts[0] == "undo":
            # return lib.MaybeEphemeral("This doesnt actually work yet", True)
            if self.last_fen is None:
                return lib.MaybeEphemeral("No moves to undo.", True)
            elif self.undo_vote is None:
                self.undo_vote = player
                return lib.RefreshMessage()
            elif self.undo_vote != player:
                # if command_parts index 1 == decline, then decline
                if len(command_parts) > 1 and command_parts[1] == "decline":
                    self.undo_vote = None
                    return lib.RefreshMessage()
                elif self.undo_vote == player:
                    return lib.MaybeEphemeral(
                        "You cannot accept your own undo request.", True
                    )
                # undo last move
                # if len(self.board.move_stack) < 1:
                #     return lib.MaybeEphemeral("Not enough moves to undo.", True)
                # self.board.pop()
                self.board = chess.Board(fen=self.last_fen)  # reset to last fen
                self.last_fen = None
                self.current_turn = (
                    self.player_b
                    if self.current_turn == self.player_w
                    else self.player_w
                )
                self.selected_piece = None
                # self.last_move = None
                self.undo_vote = None
            elif self.undo_vote == player:
                # toggle off
                self.undo_vote = None
                return lib.RefreshMessage()
        elif command_parts[0] == "truce":
            # return lib.MaybeEphemeral("This doesnt actually work yet", True)
            # if self.last_fen is None:
            #     return lib.MaybeEphemeral("No moves to truce.", True)
            if self.truce_offer is None:
                self.truce_offer = player
                return lib.RefreshMessage()
            elif self.truce_offer != player:
                # if command_parts index 1 == decline, then decline
                if len(command_parts) > 1 and command_parts[1] == "decline":
                    self.truce_offer = None
                    return lib.RefreshMessage()
                elif self.truce_offer == player:
                    return lib.MaybeEphemeral(
                        "You cannot accept your own truce offer.", True
                    )
                # accept truce
                self.truce_offer = None
                self.force_win = lib.Tie(self.player_w, self.player_b)
                return True
            elif self.truce_offer == player:
                # toggle off
                self.truce_offer = None
                return lib.RefreshMessage()
        else:
            return lib.RefreshMessage()
        outcome = self.check_outcome()
        if outcome is not None:
            elo_handler.record_outcome(outcome)
        return True

    def check_outcome(self) -> lib.Win | lib.Tie | lib.Forfeit | None:
        if self.force_win is not None:
            # return lib.Forfeit(
            #     winner_id=self.force_win,
            #     forfeiter_id=(
            #         self.player_b if self.force_win == self.player_w else self.player_w
            #     ),
            # )
            return self.force_win
        if self.board.is_checkmate():
            # return (
            #     self.player_b if self.current_turn == self.player_w else self.player_w
            # )
            return lib.Win(
                winner_id=(
                    self.player_b
                    if self.current_turn == self.player_w
                    else self.player_w
                ),
                loser_id=(
                    self.player_w
                    if self.current_turn == self.player_w
                    else self.player_b
                ),
            )
        if self.board.is_stalemate() or self.board.is_insufficient_material():
            return lib.Tie(self.player_w, self.player_b)
        return None

    def last_move(self) -> str | None:
        if len(self.board.move_stack) == 0:
            return None
        last_move = self.board.move_stack[-1]
        return last_move.uci().upper()

    def content(self) -> str:
        header = self.to_header()
        content = f"{header}It is <@{self.current_turn}>'s turn! {'⚪' if self.current_turn == self.player_w else '⚫'}"
        # append last move if there is one
        if self.last_move() is not None:
            position = self.last_move()[2:4].lower()
            move_str = f"{self.last_move()[0:2]} to {self.last_move()[2:4]}"
            content += f"\nLast move: {piece_name(self.board.piece_at(chess.parse_square(position)).symbol())} {move_str}\n\n"
        return content

    def embeds(self) -> list:
        board_str = self.render_board()
        embed = hikari.Embed(
            description=board_str,
            color=hikari.Color(0x3498DB),
        )
        return [embed]

    def render_board(self) -> str:
        if self.board.is_checkmate():
            # special rendering for checkmate that renders the cause of checkmate
            return self.render_checkmate_board()
        force_red = []
        if self.selected_piece is not None:
            moves = self.get_moves()
            for to_square in moves.get(self.selected_piece, []):
                force_red.append(to_square)
        last_moved = None
        if self.last_move() is not None:
            uci = self.last_move()[2:4]
            # convert to 0-indexed file/rank
            file = ord(uci[0]) - ord("A")
            rank = int(uci[1]) - 1
            last_moved = (file, rank)
        board_str = ""
        for rank in range(8, 0, -1):
            board_str += lib.number_emoji(rank)
            for file in range(1, 9):
                square_index = chess.square(file - 1, rank - 1)
                piece = self.board.piece_at(square_index)
                board_str += str(
                    get_emoji(
                        file - 1,
                        rank - 1,
                        piece,
                        red=self.selected_piece is not None
                        and chess.square_name(square_index).upper() in force_red,
                        green=self.selected_piece
                        == chess.square_name(square_index).upper(),
                        blue=last_moved == (file - 1, rank - 1),
                    )
                )
            board_str += "\n"
        board_str += lib.application_emoji("quiggle")
        for file in range(1, 9):
            board_str += lib.letter_emoji(file)
        return board_str

    def render_checkmate_board(self) -> str:
        # find the king in check
        king_square = None
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if (
                piece is not None
                and piece.piece_type == chess.KING
                and piece.color == self.board.turn
            ):
                king_square = square
                break
        if king_square is None:
            return self.render_board()
        # find all attackers to the king and any surrounding squares
        attackers = self.board.attackers(not self.board.turn, king_square)
        red_squares = set()
        king_file = chess.square_file(king_square)
        king_rank = chess.square_rank(king_square)
        for df in [-1, 0, 1]:
            for dr in [-1, 0, 1]:
                if df == 0 and dr == 0:
                    continue
                f = king_file + df
                r = king_rank + dr
                if (
                    0 <= f <= 7
                    and 0 <= r <= 7
                    and self.board.piece_at(chess.square(f, r)) is None
                ):
                    red_squares.add(chess.square(f, r))
        board_str = ""
        for rank in range(8, 0, -1):
            board_str += lib.number_emoji(rank)
            for file in range(1, 9):
                square_index = chess.square(file - 1, rank - 1)
                piece = self.board.piece_at(square_index)
                board_str += str(
                    get_emoji(
                        file - 1,
                        rank - 1,
                        piece,
                        red=square_index in red_squares or square_index == king_square,
                        green=square_index in attackers,
                    )
                )
            board_str += "\n"
        board_str += lib.application_emoji("quiggle")
        for file in range(1, 9):
            board_str += lib.letter_emoji(file)
        return board_str

    def components(self, bot: hikari.GatewayBot) -> list:
        if self.check_outcome() is not None:
            return []
        helper_row = bot.rest.build_message_action_row()
        helper_row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            "chess_resend",
            label="Resend!",
        )
        helper_row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            "chess_forfeit",
            label="Forfeit",
            emoji=hikari.Emoji.parse("🏳️"),
        )
        if self.truce_offer is None and self.undo_vote is None:
            helper_row.add_interactive_button(
                hikari.ButtonStyle.SECONDARY,
                "chess_truce",
                label="Offer Truce",
                emoji=hikari.Emoji.parse("🤝"),
            )
            helper_row.add_interactive_button(
                (
                    hikari.ButtonStyle.SECONDARY
                    if self.undo_vote is None
                    else hikari.ButtonStyle.DANGER
                ),
                "chess_undo",
                label=(
                    "Request Undo" if self.last_fen is not None else "No Undo Available"
                ),
                is_disabled=(self.last_fen is None),
                emoji=(hikari.UNDEFINED if self.undo_vote is None else "⏪"),
            )
        helper_row.add_link_button(
            "https://www.youtube.com/watch?v=OCSbzArwB10",
            label="How to Play",
        )
        moves = self.get_moves()

        rows = []
        if self.selected_piece is None:
            working_row = bot.rest.build_message_action_row()
            only_do_four_wide = (
                len(moves) <= 16
            )  # otherwise do the full 5 wide, this helps with rendering the buttons on mobile
            for square in my_sorted(moves.keys()):
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
                if len(working_row.components) >= (5 if not only_do_four_wide else 4):
                    rows.append(working_row)
                    working_row = bot.rest.build_message_action_row()
        elif self.next_move_is_promotion():
            # create buttons showing promotion options
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
            for to_square in moves[self.selected_piece]:
                for promotion_piece, label, emoji_name in [
                    (chess.QUEEN, "Queen", "wQw"),
                    (chess.ROOK, "Rook", "wRw"),
                    (chess.BISHOP, "Bishop", "wBw"),
                    (chess.KNIGHT, "Knight", "wNw"),
                ]:
                    if self.board.turn == chess.BLACK:
                        emoji_name = f"b{emoji_name[1:]}"
                    piece = self.board.piece_at(
                        chess.parse_square(self.selected_piece.lower())
                    )
                    emoji = get_emoji(
                        chess.square_file(chess.parse_square(to_square.lower())),
                        chess.square_rank(chess.parse_square(to_square.lower())),
                        self.board.piece_at(chess.parse_square(to_square.lower())),
                    )
                    working_row.add_interactive_button(
                        hikari.ButtonStyle.SUCCESS,
                        f"chess_move_{to_square}_promote_{label.lower()}",
                        label=f"{label} at {to_square}",
                        emoji=hikari.Emoji.parse(lib.application_emoji(emoji_name)),
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
            only_do_four_wide = len(moves[self.selected_piece]) <= 16
            for square in my_sorted(moves[self.selected_piece]):
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
                if len(working_row.components) >= (5 if not only_do_four_wide else 4):
                    rows.append(working_row)
                    working_row = bot.rest.build_message_action_row()
        if len(working_row.components) > 0:
            rows.append(working_row)
        if len(rows) > 4:

            rows = []
            piece_selector_row = bot.rest.build_message_action_row()
            # piece_selector = piece_selector_row.add_text_menu(
            #     "chess_select",
            #     placeholder="Select a piece to move",
            # )
            # for square in my_sorted(moves.keys()):
            #     piece = self.board.piece_at(chess.parse_square(square.lower()))
            #     piece_selector.add_option(
            #         f"{square} ({piece_name(piece.symbol()).capitalize()})",
            #         f"{square}",
            #         is_default=(self.selected_piece == square),
            #     )
            emoji = get_emoji(
                chess.square_file(chess.parse_square(self.selected_piece.lower())),
                chess.square_rank(chess.parse_square(self.selected_piece.lower())),
                self.board.piece_at(chess.parse_square(self.selected_piece.lower())),
            )
            piece_selector_row.add_interactive_button(
                hikari.ButtonStyle.DANGER,
                "chess_deselect",
                label=f"{self.selected_piece}",
                emoji=hikari.Emoji.parse(emoji),
            )
            rows.append(piece_selector_row)
            if self.selected_piece is not None:
                move_selector_row = bot.rest.build_message_action_row()
                move_selector = move_selector_row.add_text_menu(
                    "chess_move_dropdown",
                    placeholder="Select a square to move to",
                )
                i = 1
                append = False
                for square in my_sorted(moves[self.selected_piece]):
                    append = True
                    i += 1
                    move_selector.add_option(
                        f"Move {piece_name(self.board.piece_at(chess.parse_square(self.selected_piece.lower())).symbol())} to {square}",
                        f"{square}",
                    )
                    if i >= 25:
                        append = False
                        rows.append(move_selector_row)
                        move_selector_row = bot.rest.build_message_action_row()
                        move_selector = move_selector_row.add_text_menu(
                            "chess_move_dropdown_cont",
                            placeholder="Select a square to move to (cont.)",
                        )
                        i = 1
                if append:
                    rows.append(move_selector_row)
        if self.undo_vote is not None:
            rows = []
            new_row = bot.rest.build_message_action_row()
            new_row.add_interactive_button(
                hikari.ButtonStyle.DANGER,
                "chess_undo",
                label="Accept Undo",
                emoji="⏪",
            )
            new_row.add_interactive_button(
                hikari.ButtonStyle.SECONDARY,
                "chess_undo_decline",
                label="Decline/Cancel Undo",
                emoji="❌",
            )
            rows.append(new_row)
        elif self.truce_offer is not None:
            rows = []
            new_row = bot.rest.build_message_action_row()
            new_row.add_interactive_button(
                hikari.ButtonStyle.SUCCESS,
                "chess_truce",
                label="Accept Truce",
                emoji="🤝",
            )
            new_row.add_interactive_button(
                hikari.ButtonStyle.DANGER,
                "chess_truce_decline",
                label="Decline/Cancel Truce",
                emoji="❌",
            )
            rows.append(new_row)
        rows.append(helper_row)
        return rows

    def next_move_is_promotion(self) -> bool:
        if self.selected_piece is None:
            return False
        moves = self.get_moves()
        for to_square in moves.get(self.selected_piece, []):
            from_rank = int(self.selected_piece[1])
            to_rank = int(to_square[1])
            piece = self.board.piece_at(chess.parse_square(self.selected_piece.lower()))
            if piece is not None and piece.piece_type == chess.PAWN:
                if (piece.color == chess.WHITE and to_rank == 8) or (
                    piece.color == chess.BLACK and to_rank == 1
                ):
                    return True
        return False

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
            # "last_move": str(self.last_move),
            "last_fen": str(self.last_fen),
            "move_stack": [move_to_string(m) for m in self.board.move_stack],
            "undo_vote": str(self.undo_vote),
            "truce_offer": str(self.truce_offer),
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
            # game.last_move = dict_data.get("last_move", None)
            # if game.last_move == "None":
            #     game.last_move = None
            game.last_fen = dict_data.get("last_fen", None)
            if game.last_fen == "None":
                game.last_fen = None
            move_stack = dict_data.get("move_stack", None)
            if move_stack == "None":
                move_stack = None
            if move_stack is not None:
                game.board.move_stack = [string_to_move(m) for m in move_stack]
            game.undo_vote = dict_data.get("undo_vote", None)
            if game.undo_vote == "None":
                game.undo_vote = None
            if game.undo_vote is not None:
                game.undo_vote = hikari.Snowflake(
                    game.undo_vote
                )  # we'll use these for comparisons so convert now
            game.truce_offer = dict_data.get("truce_offer", None)
            if game.truce_offer == "None":
                game.truce_offer = None
            if game.truce_offer is not None:
                game.truce_offer = hikari.Snowflake(
                    game.truce_offer
                )  # we'll use these for comparisons so convert now
            return game
        except Exception:
            return None


def get_emoji(
    x: int,
    y: int,
    piece: chess.PieceType | None,
    *,
    red: bool = False,
    green: bool = False,
    blue: bool = False,
) -> hikari.Emoji:
    is_black_square = (x + y) % 2 == 1
    square_color = "black" if is_black_square else "red"
    if piece is None:

        if square_color == "black":
            if red:
                return lib.application_emoji("green_danger")
            elif green:
                return lib.application_emoji("green_green")
            elif blue:
                return lib.application_emoji("green_blue")
            else:
                return lib.application_emoji("green")
        elif square_color == "red":
            if red:
                return lib.application_emoji("white_danger")
            elif green:
                return lib.application_emoji("white_green")
            elif blue:
                return lib.application_emoji("white_blue")
            else:
                return lib.application_emoji("white")
        else:
            return lib.application_emoji("quiggle")

    color = "w" if piece.color == chess.WHITE else "b"
    symbol = piece.symbol().upper()
    background = "g" if is_black_square else "w"
    emoji_name = f"{color}{symbol}{background}"
    if red:
        emoji_name += "_danger"
    elif green:
        emoji_name += "_green"
    elif blue:
        emoji_name += "_blue"
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


def move_to_string(move: chess.Move) -> str:
    return {
        "from_square": str(move.from_square),
        "to_square": str(move.to_square),
        "promotion": str(move.promotion),
        "drop": str(move.drop),
    }


def string_to_move(data: dict) -> chess.Move:
    from_square = int(data["from_square"])
    to_square = int(data["to_square"])
    promotion = int(data["promotion"]) if data["promotion"] != "None" else None
    drop = data["drop"] if data["drop"] != "None" else None
    return chess.Move(from_square, to_square, promotion=promotion, drop=drop)


def my_sorted(iterable):
    """A sorting function for chess squares that sorts by rank then file."""

    # board displays 8 at the top, so we sort by rank descending
    # and A at the left, so file ascending
    def sort_key(square):
        file = ord(square[0].upper()) - ord("A")
        rank = int(square[1])
        return (-rank, file)

    return sorted(iterable, key=sort_key)
