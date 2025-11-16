import os
from attr import dataclass
import hikari
import zlib
import base64
import json
import sys
import datetime
import logging

LOGGER = logging.getLogger("quiggle-games-pro")


class GameInvite:
    def __init__(
        self,
        inviter_id: hikari.Snowflake,
        invited_id: hikari.Snowflake | None,
        game_name: str,
        game_display_name: str,
        options: dict | None = None,
    ):
        self.inviter_id = inviter_id
        self.invited_id = invited_id
        self.target_game_name = game_name
        self.target_game_display_name = game_display_name
        self.game_name = "Invitation"
        self.options = options or {}

    @staticmethod
    def from_header(content: str) -> "GameInvite | None":
        header = extract_header(content)
        if header is None:
            return None
        try:
            content = header[3:-3].strip()
            lines = content.splitlines()
            if len(lines) < 2:
                return None
            game_data = lines[0].strip()
            target_game_name = lines[1].strip()
            dict_data = deserialize(game_data)
            if dict_data is None:
                return None
            invited = dict_data.get("invited_id")
            if invited == "None":
                invited = None
            if invited is not None:
                invited = hikari.Snowflake(invited)
            return GameInvite(
                inviter_id=hikari.Snowflake(dict_data["inviter_id"]),
                invited_id=invited,
                game_name=target_game_name,
                game_display_name=dict_data.get("game_display_name", target_game_name),
                options=dict_data.get("options"),
            )
        except Exception as e:
            # print(f"Error deserializing GameInvite from header: {e}")
            return None

    def to_header(self) -> str:
        data = {
            "inviter_id": str(self.inviter_id),
            "invited_id": str(self.invited_id),
            "game_display_name": self.target_game_display_name,
            "options": self.options,
        }
        serialized_data = serialize(data)
        header = f"```{serialized_data}\n{self.target_game_name}\n```"
        return header

    def components(self, bot: hikari.GatewayBot) -> list:
        row = bot.rest.build_message_action_row()
        if self.invited_id is None:
            row.add_interactive_button(
                hikari.components.ButtonStyle.SUCCESS,
                "invite_accept",
                label="Join",
            )
        else:
            row.add_interactive_button(
                hikari.components.ButtonStyle.SUCCESS, "invite_accept", label="Accept"
            )
            row.add_interactive_button(
                hikari.components.ButtonStyle.DANGER, "invite_decline", label="Decline"
            )
        return [row]

    def content(self) -> str:
        if self.invited_id is None:
            return f"{self.to_header()}<@{self.inviter_id}> has invited anyone to play **{self.target_game_display_name}**!"
        else:
            return f"{self.to_header()}<@{self.inviter_id}> has invited <@{self.invited_id}> to play **{self.target_game_display_name}**!"

    def user_mentions(self) -> list[hikari.Snowflake]:
        mentions = [self.inviter_id]
        if self.invited_id is not None:
            mentions.append(self.invited_id)
        return mentions

    async def handle_interaction(
        self, event: hikari.InteractionCreateEvent, bot: hikari.GatewayBot
    ) -> bool:
        if (
            event.interaction.user.id == self.inviter_id
            and event.interaction.user.id not in admins()
        ):
            await bot.rest.create_interaction_response(
                event.interaction,
                event.interaction.token,
                hikari.ResponseType.MESSAGE_CREATE,
                "You cannot accept or decline your own game invite.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return False
        if self.invited_id is not None:
            if (
                event.interaction.user.id != self.invited_id
                and event.interaction.user.id not in admins()
            ):
                await bot.rest.create_interaction_response(
                    event.interaction,
                    event.interaction.token,
                    hikari.ResponseType.MESSAGE_CREATE,
                    "You are not invited to this game.",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return False
        else:
            self.invited_id = event.interaction.user.id

        custom_id = event.interaction.custom_id

        if custom_id == "invite_accept":

            return True
        elif custom_id == "invite_decline":

            message = event.interaction.message
            if message is not None:
                await bot.rest.create_interaction_response(
                    event.interaction,
                    event.interaction.token,
                    hikari.ResponseType.MESSAGE_UPDATE,
                    "The game invite has been declined.",
                    components=[],
                    embeds=message.embeds,
                )
            return False
        await bot.rest.create_interaction_response(
            event.interaction,
            event.interaction.token,
            hikari.ResponseType.MESSAGE_CREATE,
            "Unknown interaction.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return False


def serialize(data: dict) -> str:

    json_data = json.dumps(data).encode("utf-8")
    compressed_data = zlib.compress(json_data)
    b64_data = base64.urlsafe_b64encode(compressed_data).decode("utf-8").rstrip("=")
    return b64_data


def deserialize(data: str) -> dict | None:

    try:
        padded_data = data + "=" * (-len(data) % 4)
        compressed_data = base64.urlsafe_b64decode(padded_data.encode("utf-8"))
        json_data = zlib.decompress(compressed_data)
        dict_data = json.loads(json_data.decode("utf-8"))
        return dict_data
    except Exception:
        return None


def header_name(content: str) -> str | None:
    header = extract_header(content)
    if header is None:
        return None
    try:
        content = header[3:-3].strip()
        lines = content.splitlines()
        if len(lines) != 2:
            return None
        game_name = lines[1].strip()
        return game_name
    except Exception:
        return None


def extract_header(content: str) -> str | None:

    if content.startswith("```") and "```" in content[3:]:
        end_index = content.find("```", 3) + 3
        return content[:end_index]
    return None


class Tie:
    def __init__(self, player1_id: hikari.Snowflake, player2_id: hikari.Snowflake):
        self.player1_id = player1_id
        self.player2_id = player2_id


class Win:
    def __init__(self, *, winner_id: hikari.Snowflake, loser_id: hikari.Snowflake):
        self.winner_id = winner_id
        self.loser_id = loser_id


class Forfeit:
    def __init__(self, *, winner_id: hikari.Snowflake, forfeiter_id: hikari.Snowflake):
        self.winner_id = winner_id
        self.forfeiter_id = forfeiter_id


def admins() -> list[hikari.Snowflake]:
    if "--admin" in sys.argv:
        return [hikari.Snowflake(156533151198478336)]
    return []


class MaybeEphemeral:
    def __init__(self, message: str, ephemeral: bool):
        self.message = message
        self.ephemeral = ephemeral


def current_timestamp() -> int:
    return int(datetime.datetime.now().timestamp())


@dataclass
class RefreshMessage:
    resend: bool = False


def number_emoji(n: int) -> str:

    return application_emoji(str(n))


def letter_emoji(n: int) -> str:

    return application_emoji(str(chr(64 + n)))


application_emojis = {}


def set_application_emojis(emojis: dict[str, str]) -> None:
    global application_emojis
    emojis_str = "Application emojis set: "
    # print(f"Application emojis set: ", end="")
    first = True
    for key, value in emojis.items():
        # print(f"  {key}: {value}")
        # print(f"{', ' if not first else ''}{key}", end="")
        emojis_str += f"{', ' if not first else ''}{key}"
        first = False
    LOGGER.info(emojis_str)
    application_emojis = emojis


def application_emoji(name: str) -> str:
    if len(name) == 1:
        name = f"{name}_"
    emoji = application_emojis.get(name)
    if emoji is not None:
        return emoji
    return fallback(name)


game_names = {}


def set_game_name(game_code: str, name: str) -> None:
    global game_names
    game_names[game_code] = name


def get_game_name(game_code: str) -> str:
    global game_names
    return game_names.get(game_code, "Unknown Game")


def fallback(name: str) -> str:
    LOGGER.warning(f"Falling back for emoji: {name}")
    return "❌"


def get_username(user: hikari.User) -> str:
    # get the pretty username of the user, otherwise fall back to their full actual username
    return user.global_name or user.username


def donation_url() -> str:
    return os.getenv("DONATION_LINK", "https://google.com")


def donation_logo_url() -> str:
    return os.getenv(
        "DONATION_LOGO_URL",
        "https://storage.ko-fi.com/cdn/kofi3.png?v=2",
    )
