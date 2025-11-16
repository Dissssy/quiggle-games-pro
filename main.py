import dotenv
import hikari
import lightbulb
import os
import sys
import lib
import elo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import datetime

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
                    lib.LOGGER.info(f"Loaded game: {readable_name}")
                    lib.set_game_name(game_code=game_name, name=readable_name)
                except AttributeError:
                    lib.LOGGER.info(
                        f"Loaded game module: {module_name} (no game_name function found)"
                    )
            else:
                raise TypeError(f"The setup in {module_name} is not callable.")
        else:
            raise AttributeError(f"No setup function found in {module_name}.")

handler = elo.EloHandler(db=db, game_name="elo")


rolling_interactions: list[int] = (
    []
)  # store timestamps of interactions, discard after an hour, give the average interactions per minute
first_interaction_timestamp: int | None = (
    None  # store the timestamp of the first interaction for average calculation until the bot has been running for an hour
)


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
    global first_interaction_timestamp
    if first_interaction_timestamp is None:
        first_interaction_timestamp = event.interaction.created_at.timestamp()
    rolling_interactions.append(event.interaction.created_at.timestamp())


@bot.listen()
async def on_ready(event: hikari.StartedEvent) -> None:
    emojis = await bot.rest.fetch_application_emojis(client._application.id)
    parsed = {}
    for emoji in emojis:
        parsed[str(emoji.name)] = f"<:{emoji.name}:{emoji.id}>"
    lib.set_application_emojis(parsed)
    lib.LOGGER.info(f"Successfully loaded {len(emojis)} emojis.")

    sched = AsyncIOScheduler()
    sched.start()

    @sched.scheduled_job(CronTrigger(minute="*/1"))
    async def update_interaction_stats():
        global rolling_interactions
        global first_interaction_timestamp
        current_timestamp = datetime.datetime.now().timestamp()
        # Remove timestamps older than 1 hour
        rolling_interactions = [
            ts for ts in rolling_interactions if current_timestamp - ts <= 3600
        ]
        interactions_count = len(rolling_interactions)
        if first_interaction_timestamp is not None:
            elapsed_time = current_timestamp - first_interaction_timestamp
            elapsed_minutes = max(elapsed_time / 60, 1)  # Avoid division by zero
            average_per_minute = interactions_count / elapsed_minutes
        else:
            average_per_minute = 0
        # set the bot's presence to show the average interactions per minute
        await bot.update_presence(
            activity=hikari.Activity(
                name=f"{average_per_minute:.2f} interactions/min",
                url=lib.donation_url(),
                type=hikari.ActivityType.WATCHING,
            ),
            status=hikari.Status.ONLINE,
        )

    lib.LOGGER.info("Launched scheduled interaction stats updater.")


if __name__ == "__main__":
    bot.run()
