import lightbulb
import hikari
import lib
import random
import elo


def game_name(command_name: bool = False) -> str:
    name = "Rock Paper Scissors"
    if command_name:
        return name.lower().replace(" ", "")
    return name


def setup(
    bot: hikari.GatewayBot, client: lightbulb.Client, elo_handler: elo.EloHandler
) -> None:
    @client.register()
    class Command(
        lightbulb.MessageCommand,
        name=game_name(command_name=True),
        description=f"Start a game of {game_name()}!",
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
                invited_id=user.id if user is not None else None,
                game_name=game_name(),
                game_display_name=game_name(),
            )
            await ctx.respond(
                invite.content(),
                user_mentions=invite.user_mentions(),
                components=invite.components(bot),
            )

    @client.register()
    class SlashCommand(
        lightbulb.SlashCommand,
        name=game_name(command_name=True),
        description=f"Start a game of {game_name()}!",
    ):
        opponent = lightbulb.user(
            "opponent",
            f"The user to challenge to a game of {game_name()}.",
            default=None,  # Support posting an open challenge
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            user = self.opponent
            if user is not None:
                if user.is_bot:
                    await ctx.respond("Bots cannot play games.", ephemeral=True)
                    return
                elo_handler.store_user_data(
                    user_id=user.id,
                    username=lib.get_username(user),
                    avatar_url=user.display_avatar_url or user.default_avatar_url,
                )
                if user.id == ctx.user.id:
                    await ctx.respond(
                        "You cannot play against yourself!", ephemeral=True
                    )
                    return
            invite = lib.GameInvite(
                inviter_id=ctx.user.id,
                invited_id=user.id if user is not None else None,
                game_name=game_name(),
                game_display_name=game_name(),
            )
            await ctx.respond(
                invite.content(),
                user_mentions=invite.user_mentions(),
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
        parsed_name = lib.header_name(content)
        if parsed_name != f"{game_name()}":
            return
        invite = lib.GameInvite.from_header(content)
        if invite is None:

            game = Game.from_header(content)
            if game is None:
                return
            custom_id = event.interaction.custom_id
            if custom_id.startswith(f"{game_name()}_move_"):
                parts = custom_id.split("_")
                # if len(parts) != 4:
                #     print(f"Invalid {game_name()}_move_ interaction id:", custom_id)
                #     return
                # try:
                #     row = int(parts[2])
                #     col = int(parts[3])
                # except ValueError:
                #     return
                try:
                    choice = int(parts[2])  # 0: Rock, 1: Paper, 2: Scissors
                except ValueError:
                    return
                if choice not in [0, 1, 2]:
                    await bot.rest.create_interaction_response(
                        event.interaction,
                        event.interaction.token,
                        hikari.ResponseType.MESSAGE_CREATE,
                        "Invalid move choice.",
                        flags=hikari.MessageFlag.EPHEMERAL,
                    )
                    return
                response = game.make_move(
                    event.interaction.user.id, choice, elo_handler
                )
                if isinstance(response, lib.MaybeEphemeral):
                    await bot.rest.create_interaction_response(
                        event.interaction,
                        event.interaction.token,
                        hikari.ResponseType.MESSAGE_CREATE,
                        response.message,
                        flags=(
                            hikari.MessageFlag.EPHEMERAL
                            if response.ephemeral
                            else hikari.MessageFlag.NONE
                        ),
                    )
                    return
                elif isinstance(response, bool) and response:
                    outcome = game.check_outcome()
                    if outcome is None:
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=game.content(),
                            components=game.components(bot),
                            embeds=game.embeds(),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Tie):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{game.to_empty_header()}The game is a tie!",
                            components=game.components(bot),
                            embeds=game.embeds(),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Win):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{game.to_empty_header()}<@{outcome.winner_id}> has won the game!",
                            components=game.components(bot),
                            embeds=game.embeds(),
                            token=event.interaction.token,
                        )
                        return
                    if isinstance(outcome, lib.Forfeit):
                        await bot.rest.create_interaction_response(
                            interaction=event.interaction,
                            response_type=hikari.ResponseType.MESSAGE_UPDATE,
                            content=f"{game.to_empty_header()}<@{outcome.winner_id}> has won the game by forfeit!",
                            components=game.components(bot),
                            embeds=game.embeds(),
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
                    game = Game(invite.invited_id, invite.inviter_id)
                else:
                    game = Game(invite.inviter_id, invite.invited_id)

                await bot.rest.create_interaction_response(
                    interaction=event.interaction,
                    response_type=hikari.ResponseType.MESSAGE_UPDATE,
                    content=game.content(),
                    components=game.components(bot),
                    embeds=game.embeds(),
                    token=event.interaction.token,
                )
                return


class Game:
    def __init__(
        self,
        player_1: hikari.Snowflake,
        player_2: hikari.Snowflake,
    ) -> None:
        self.player_1 = player_1
        self.player_2 = player_2
        self.player_1_choice: int | None = None  # 0: Rock, 1: Paper, 2: Scissors
        self.player_2_choice: int | None = None  # 0: Rock, 1: Paper, 2: Scissors
        self.player_1_wins = 0
        self.player_2_wins = 0
        self.round_history: list[tuple[int, int]] = []

    def make_move(
        self, player: hikari.Snowflake, choice: int, elo_handler: elo.EloHandler
    ) -> bool | lib.MaybeEphemeral:
        if player in lib.admins():
            player = self.player_1 if self.player_1_choice is None else self.player_2
        if player != self.player_1 and player != self.player_2:
            return lib.MaybeEphemeral(
                message="You are not a player in this game.",
                ephemeral=True,
            )
        # game logic
        if player == self.player_1 and self.player_1_choice is not None:
            return lib.MaybeEphemeral(
                message="You have already made your move.",
                ephemeral=True,
            )
        if player == self.player_2 and self.player_2_choice is not None:
            return lib.MaybeEphemeral(
                message="You have already made your move.",
                ephemeral=True,
            )

        if player == self.player_1:
            self.player_1_choice = choice
        elif player == self.player_2:
            self.player_2_choice = choice
        else:
            return lib.MaybeEphemeral(
                message="You are not a player in this game. HOW????",
                ephemeral=True,
            )
        outcome = self.check_outcome()
        if outcome is not None:
            if isinstance(outcome, lib.Win):
                if outcome.winner_id == self.player_1:
                    self.player_1_wins += 1
                else:
                    self.player_2_wins += 1
            self.round_history.append((self.player_1_choice, self.player_2_choice))
            self.player_1_choice = None
            self.player_2_choice = None
            elo_handler.record_outcome(outcome)
        return True

    def check_outcome(self) -> lib.Win | lib.Tie | lib.Forfeit | None:
        # game logic to check for win/tie
        if self.player_1_choice is not None and self.player_2_choice is not None:
            if self.player_1_choice == self.player_2_choice:
                return lib.Tie(player1_id=self.player_1, player2_id=self.player_2)
            elif (self.player_1_choice - self.player_2_choice) % 3 == 1:
                return lib.Win(winner_id=self.player_1, loser_id=self.player_2)
            else:
                return lib.Win(winner_id=self.player_2, loser_id=self.player_1)
        return None

    def content(self) -> str:
        header = self.to_header()
        outcome = ""
        player_1_last_move = ""
        player_2_last_move = ""
        # get the latest round outcome
        if self.round_history:
            # set the last moves, and outcome will be either <@{winner}> won the last round! or The last round was a tie!
            last_round = self.round_history[-1]
            player_1_last_move = move_map[last_round[0]]["emoji"] + " "
            player_2_last_move = move_map[last_round[1]]["emoji"] + " "
            if last_round[0] == last_round[1]:
                outcome = f"The last round was a tie!\n"
            elif (last_round[0] - last_round[1]) % 3 == 1:
                outcome = f"<@{self.player_1}> won the last round!\n"
            else:
                outcome = f"<@{self.player_2}> won the last round!\n"
        return f"{header}{outcome}{player_1_last_move}<@{self.player_1}>{"" if self.player_1_choice is None else " ✅"}\nVS.\n{player_2_last_move}<@{self.player_2}>{"" if self.player_2_choice is None else " ✅"}\nMake your move!"

    def embeds(self) -> list[hikari.Embed]:
        embeds = []
        # create embed showing score and round history
        embed = hikari.Embed(title=f"{game_name()} Scoreboard")
        embed.add_field(
            name=f"Wins: {self.player_1_wins}", value=f"<@{self.player_1}>", inline=True
        )
        embed.add_field(
            name=f"Wins: {self.player_2_wins}", value=f"<@{self.player_2}>", inline=True
        )
        if self.round_history:
            history_str = ""
            for i, (p1_move, p2_move) in enumerate(self.round_history, start=1):
                history_str += (
                    f"Round {i}: {move_map[p1_move]['emoji']} "
                    f"vs {move_map[p2_move]['emoji']}\n"
                )
            embed.add_field(name="Round History", value=history_str, inline=False)
        embeds.append(embed)
        return embeds

    def components(self, bot: hikari.GatewayBot) -> list:
        # override_disable = self.check_outcome() is not None
        rows = []
        # game logic to create components
        row = bot.rest.build_message_action_row()
        for i, move in enumerate(move_map):
            row.add_interactive_button(
                move["button_style"],
                f"{game_name()}_move_{i}",
                label=move["name"],
                emoji=move["emoji"],
            )
        rows.append(row)
        return rows

    def to_header(self) -> str:
        game_data = {
            "player_1": str(self.player_1),
            "player_2": str(self.player_2),
            "player_1_wins": self.player_1_wins,
            "player_2_wins": self.player_2_wins,
            "player_1_choice": self.player_1_choice,
            "player_2_choice": self.player_2_choice,
            "round_history": self.round_history,
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\n{game_name()}\n```"

    def to_empty_header(self) -> str:
        return f"```{game_name()}```"

    @staticmethod
    def from_header(content: str) -> "Game | None":
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
            game = Game(
                player_1=hikari.Snowflake(dict_data["player_1"]),
                player_2=hikari.Snowflake(dict_data["player_2"]),
            )
            game.player_1_wins = dict_data["player_1_wins"]
            game.player_2_wins = dict_data["player_2_wins"]
            game.player_1_choice = dict_data["player_1_choice"]
            if game.player_1_choice is not None:
                game.player_1_choice = int(game.player_1_choice)
            game.player_2_choice = dict_data["player_2_choice"]
            if game.player_2_choice is not None:
                game.player_2_choice = int(game.player_2_choice)
            game.round_history = [tuple(pair) for pair in dict_data["round_history"]]
            return game
        except Exception:
            return None


move_map = [
    {"emoji": "🪨", "name": "Rock", "button_style": hikari.ButtonStyle.PRIMARY},
    {"emoji": "📄", "name": "Paper", "button_style": hikari.ButtonStyle.SUCCESS},
    {"emoji": "✂️", "name": "Scissors", "button_style": hikari.ButtonStyle.DANGER},
]
