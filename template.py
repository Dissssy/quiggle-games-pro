import lightbulb
import hikari
import lib
import random
import elo


def game_name(command_name: bool = False) -> str:
    name = "Template"
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
                invited_id=message.author.id,
                game_name=game_name(),
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {message.author.mention} to a game of {game_name()}!",
                user_mentions=[ctx.user.id, message.author.id],
                components=invite.components(bot),
            )

    @client.register()
    class SlashCommand(
        lightbulb.SlashCommand,
        name=game_name.lower(),
        description=f"Start a game of {game_name()}!",
    ):
        target = lightbulb.user(
            "target",
            f"The user to challenge to a game of {game_name()}.",
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
                game_name=game_name(),
            )
            header = invite.to_header()
            await ctx.respond(
                f"{header}{ctx.user.mention} has challenged {user.mention} to a game of {game_name()}!",
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
                response = game.make_move(event.interaction.user.id, elo_handler)
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
        *,
        current_turn: hikari.Snowflake | None = None,
    ) -> None:
        self.player_x = player_1
        self.player_o = player_2
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.current_turn = current_turn or self.player_x

    def make_move(
        self, player: hikari.Snowflake, elo_handler: elo.EloHandler
    ) -> bool | lib.MaybeEphemeral:
        if player in lib.admins():
            player = self.current_turn
        if self.current_turn != player:
            return lib.MaybeEphemeral("It's not your turn!", ephemeral=True)
        # game logic

        # change turn
        self.current_turn = (
            self.player_o if self.current_turn == self.player_x else self.player_x
        )
        outcome = self.check_outcome()
        if outcome is not None:
            elo_handler.record_outcome(outcome)
        return True

    def check_outcome(self) -> lib.Win | lib.Tie | lib.Forfeit | None:
        # game logic to check for win/tie
        return None

    def content(self) -> str:
        header = self.to_header()
        return f"{header}It is <@{self.current_turn}>'s turn! ({'X' if self.current_turn == self.player_x else 'O'})"

    def embeds(self) -> list[hikari.Embed]:
        embeds = []
        # game logic to create embeds
        return embeds

    def components(self, bot: hikari.GatewayBot) -> list:
        # override_disable = self.check_outcome() is not None
        rows = []
        # game logic to create components
        return rows

    def to_header(self) -> str:
        game_data = {
            "player_1": str(self.player_x),
            "player_2": str(self.player_o),
            "current_turn": str(self.current_turn),
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
                current_turn=hikari.Snowflake(dict_data["current_turn"]),
            )
            return game
        except Exception:
            return None
