import dotenv
import hikari
import lightbulb
import os
import sys
import lib

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

for filename in os.listdir("games"):
    if filename.endswith(".py") and not filename.startswith("__"):
        module_name = f"games.{filename[:-3]}"
        module = importlib.import_module(module_name)
        if hasattr(module, "setup"):
            if callable(module.setup):
                module.setup(bot, client)
            else:
                raise TypeError(f"The setup in {module_name} is not callable.")
        else:
            raise AttributeError(f"No setup function found in {module_name}.")


@bot.listen()
async def on_ready(event: hikari.StartedEvent) -> None:
    emojis = await bot.rest.fetch_application_emojis(client._application.id)
    parsed = {}
    for emoji in emojis:
        parsed[str(emoji.name)] = f"<:{emoji.name}:{emoji.id}>"
    lib.set_application_emojis(parsed)
    print(f"Successfully loaded {len(emojis)} emojis.")
    print(lib.application_emoji("quiggle"))


if __name__ == "__main__":
    bot.run()
