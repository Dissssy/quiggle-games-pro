from attr import dataclass
import hikari
import zlib
import base64
import json
import sys
import datetime


class GameInvite:
    def __init__(
        self, inviter_id: hikari.Snowflake, invited_id: hikari.Snowflake, game_name: str
    ):
        self.inviter_id = inviter_id
        self.invited_id = invited_id
        self.target_game_name = game_name
        self.game_name = "Invitation"

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
            return GameInvite(
                inviter_id=hikari.Snowflake(dict_data["inviter_id"]),
                invited_id=hikari.Snowflake(dict_data["invited_id"]),
                game_name=target_game_name,
            )
        except Exception:
            return None

    def to_header(self) -> str:
        data = {
            "inviter_id": str(self.inviter_id),
            "invited_id": str(self.invited_id),
        }
        serialized_data = serialize(data)
        header = f"```{serialized_data}\n{self.target_game_name}\n```"
        return header

    def components(self, bot: hikari.GatewayBot) -> list:
        row = bot.rest.build_message_action_row()
        row.add_interactive_button(3, "invite_accept", label="Accept")
        row.add_interactive_button(4, "invite_decline", label="Decline")
        return [row]

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
        custom_id = event.interaction.custom_id

        if custom_id == "invite_accept":

            return True
        elif custom_id == "invite_decline":

            message = event.interaction.message
            if message is not None:
                await message.delete()
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
    print(f"Application emojis set:")
    for key, value in emojis.items():
        print(f"  {key}: {value}")
    application_emojis = emojis


def application_emoji(name: str) -> str:
    if len(name) == 1:
        name = f"{name}_"
    emoji = application_emojis.get(name)
    if emoji is not None:
        return emoji
    return fallback(name)


def fallback(name: str) -> str:
    print(f"Falling back for emoji: {name}")
    return ":x:"


def get_username(user: hikari.User) -> str:
    # get the pretty username of the user, otherwise fall back to their full actual username
    return user.global_name or user.username
