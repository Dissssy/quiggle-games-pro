import dotenv
import hikari
import lightbulb
import os
import sys
import lib
import elo

dotenv.load_dotenv()


token = None

if "--prod" in sys.argv:
    token = os.getenv("PRODUCTION_TOKEN")
else:
    token = os.getenv("DEVELOPMENT_TOKEN")

if token is None:
    raise ValueError("Bot token not found in environment variables.")

bot = hikari.GatewayBot(token=token)
client = lightbulb.client_from_app(bot)
bot.subscribe(hikari.StartingEvent, client.start)


import importlib

db = elo.init_db()

for filename in os.listdir("games"):
    if filename.endswith(".py") and not filename.startswith("__"):
        game_name = filename[:-3]
        module_name = f"games.{game_name}"
        module = importlib.import_module(module_name)
        if hasattr(module, "setup"):
            if callable(module.setup):
                module.setup(bot, client, elo.EloHandler(db=db, game_name=game_name))
                try:
                    readable_name = module.game_name()
                    print(f"Loaded game: {readable_name}")
                    lib.set_game_name(game_code=game_name, name=readable_name)
                except AttributeError:
                    print(
                        f"Loaded game module: {module_name} (no game_name function found)"
                    )
            else:
                raise TypeError(f"The setup in {module_name} is not callable.")
        else:
            raise AttributeError(f"No setup function found in {module_name}.")

handler = elo.EloHandler(db=db, game_name="elo")


@bot.listen()
async def on_ready(event: hikari.StartedEvent) -> None:
    emojis = await bot.rest.fetch_application_emojis(client._application.id)
    parsed = {}
    for emoji in emojis:
        parsed[str(emoji.name)] = f"<:{emoji.name}:{emoji.id}>"
    lib.set_application_emojis(parsed)
    print(f"Successfully loaded {len(emojis)} emojis.")
    print(lib.application_emoji("quiggle"))


@bot.listen(hikari.InteractionCreateEvent)
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    # attempt to cache the authors username and profile picture on any interaction
    user = event.interaction.user
    if user is not None:
        if not user.is_bot:
            handler.store_user_data(
                user_id=user.id,
                username=lib.get_username(user),
                avatar_url=user.display_avatar_url or user.default_avatar_url,
            )


if __name__ == "__main__":
    bot.run()
