from bson import ObjectId
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import AuthError, ClientError
from .handlers import register
from .request_models import Connection, ChannelRequest


def generate_id() -> str:
    return ObjectId().binary.hex()


class Job(StrEnum):
    Miner = "miner"
    Farmer = "food"
    Lumberjack = "lumberjack"
    Enchanter = "enchanter"
    Builder = "builder"
    Militia = "militia"
    Merchant = "merchant"
    Scout = "scout"


class GameState(StrEnum):
    Lobby = "lobby"


# In-Memory Models
@dataclass
class Worker:
    id: str
    name: str
    job: Job = Job.Militia


@dataclass
class Game:
    id: str # Same ID as the associated channel
    state: GameState = GameState.Lobby
    workers: dict[str, Worker] = field(default_factory=dict)


games: dict[str, Game]


@register("game/create")
def handle_create_game(connection: Connection, request: ChannelRequest) -> Game:
    if request.channel.id not in connection.user.linked_channels:
        raise AuthError("channel not linked")

    if request.channel.id in games:
        raise ClientError("channel already has an active game")

    game = Game(id=request.channel.id)
    games[game.id] = game
    return {"id": game.id}
