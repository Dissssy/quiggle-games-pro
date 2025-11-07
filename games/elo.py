import lightbulb
import hikari
import lib
import random
import elo


def setup(
    bot: hikari.GatewayBot, client: lightbulb.Client, elo_handler: elo.EloHandler
) -> None:
    @client.register()
    class EloCommand(
        lightbulb.MessageCommand,
        name="elo",
        description="Show this user's Elo ratings!",
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
            elo_display = EloGame(
                target=message.author.id,
                username=lib.get_username(message.author),
                invoker=ctx.user.id,
            )
            await ctx.respond(
                content=elo_display.content(),
                embeds=elo_display.embeds(elo_handler=elo_handler),
                components=elo_display.components(bot),
                ephemeral=True,
            )

    @client.register()
    class EloUserCommand(
        lightbulb.UserCommand,
        name="elo",
        description="Show this user's Elo ratings!",
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            user = self.target
            if user is None:
                await ctx.respond("Could not fetch the target user.", ephemeral=True)
                return
            if user.is_bot:
                await ctx.respond("Bots cannot play games.", ephemeral=True)
                return
            elo_handler.store_user_data(
                user_id=user.id,
                username=lib.get_username(user),
                avatar_url=user.display_avatar_url or user.default_avatar_url,
            )
            elo_display = EloGame(
                target=user.id, username=lib.get_username(user), invoker=ctx.user.id
            )
            await ctx.respond(
                content=elo_display.content(),
                embeds=elo_display.embeds(elo_handler=elo_handler),
                components=elo_display.components(bot),
                ephemeral=True,
            )

    @client.register()
    class EloSlashCommand(
        lightbulb.SlashCommand,
        name="elo",
        description="Show a user's Elo ratings!",
    ):
        target = lightbulb.user(
            "target",
            "The user to show Elo ratings for (leave blank for yourself).",
            default=None,
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
            elo_display = EloGame(
                target=user.id, username=lib.get_username(user), invoker=ctx.user.id
            )
            await ctx.respond(
                content=elo_display.content(),
                embeds=elo_display.embeds(elo_handler=elo_handler),
                components=elo_display.components(bot),
                ephemeral=True,
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
        if game_name != "Elo" and game_name != "Elo":
            return
        elo_display = EloGame.from_header(content)
        if elo_display is None:
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
            elo_display.make_move(event.interaction.user.id, row, col, elo_handler)
            await bot.rest.create_interaction_response(
                interaction=event.interaction,
                response_type=hikari.ResponseType.MESSAGE_UPDATE,
                content=elo_display.content(),
                embeds=elo_display.embeds(elo_handler=elo_handler),
                components=elo_display.components(bot),
                token=event.interaction.token,
            )


class EloGame:
    def __init__(
        self,
        target: hikari.Snowflake,
        username: str,
        invoker: hikari.Snowflake,
    ) -> None:
        self.target = target
        self.username = username
        self.invoker = invoker

    def make_move(self, remaining_parts: list[str]) -> bool:
        # Todo: implement Elo display logic
        return lib.RefreshMessage()

    def content(self) -> str:
        header = self.to_header()
        return f"{header}"

    def components(self, bot: hikari.GatewayBot) -> list:
        rows = []
        # nothing for now
        return rows

    def embeds(self, elo_handler: elo.EloHandler) -> list[hikari.Embed]:
        description = ""
        all_games = elo_handler.get_all_games()
        for game_name, _ in all_games:
            score = elo_handler.get_elo_from_table(self.target, game_name)
            if score is not None:
                description += f"**{lib.get_game_name(game_name)}**: {score}"
                if score > elo.default_elo:
                    percent_diff = (score - elo.default_elo) / elo.default_elo * 100
                    if percent_diff <= 1:
                        percentage_display = f"{percent_diff:.2f}"
                    elif percent_diff <= 10:
                        percentage_display = f"{percent_diff:.1f}"
                    else:
                        percentage_display = f"{int(percent_diff)}"
                    description += f" (+{percentage_display}%{"" if percent_diff < 50 else " 🚀"})\n"
                elif score < elo.default_elo:
                    percent_diff = (elo.default_elo - score) / elo.default_elo * 100
                    if percent_diff <= 1:
                        percentage_display = f"{percent_diff:.2f}"
                    elif percent_diff <= 10:
                        percentage_display = f"{percent_diff:.1f}"
                    else:
                        percentage_display = f"{int(percent_diff)}"
                    description += f" (-{percentage_display}%{"" if percent_diff < 50 else " 💀"})\n"
                else:
                    description += " ⚖️\n"
        if description == "":
            if self.target != self.invoker:
                description = "No Elo ratings found. Try playing with them!"
            else:
                description = "No Elo ratings found. Try playing some games!"
        embed = hikari.Embed(
            title=f"Elo Ratings for {self.username}",
            description=description.strip(),
            color=0x00FF00,
        )
        return [embed]

    def to_header(self) -> str:
        game_data = {
            "target": str(self.target),
            "username": self.username,
            "invoker": str(self.invoker),
        }
        game_data = lib.serialize(game_data)
        return f"```{game_data}\nElo\n```"

    def to_empty_header(self) -> str:
        return f"```Elo```"

    @staticmethod
    def from_header(content: str) -> "EloGame | None":
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
            game = EloGame(
                target=hikari.Snowflake(dict_data["target"]),
                username=dict_data["username"],
                invoker=hikari.Snowflake(dict_data["invoker"]),
            )
            return game
        except Exception:
            return None
