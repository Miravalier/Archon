import json
import random
import os
from fastapi import APIRouter, Header
from hmac import compare_digest
from urllib.parse import unquote

from . import database
from .errors import AuthError, ClientError
from .database_models import Permission, Channel
from .request_models import channel_by_twitch_id
from .game import games, resource_types, Entity, EntityType, Position, Job


TWITCH_KEY = os.environ["TWITCH_KEY"]


router = APIRouter()


@router.get("/twitch-event")
async def handle_twitch_event(key: str = Header(), event: str = Header()):
    if not compare_digest(key, TWITCH_KEY):
        raise AuthError("invalid twitch key")

    request: dict = json.loads(event)
    print("TWITCH EVENT", request)

    if request.get("type") == "link":
        user_id: str = request.get("userId")
        user_name: str = request.get("userName")
        channel_id: str = request.get("channelId")
        channel_name: str = request.get("channelName")
        link_code: str = request.get("code")
        if (
            not user_id or not user_name
            or not channel_id or not channel_name
            or not link_code
        ):
            return

        if channel_id == user_id:
            level = Permission.Broadcaster
        elif str(request.get("mod")) == "True":
            level = Permission.Moderator
        else:
            return

        user = database.users.find_one({"link_code": link_code})
        if not user:
            return

        channel = database.channels.find_one_and_update(
           {"twitch_id": channel_id},
           {"$set": {"name": channel_name}}
        )
        if not channel:
            channel = database.channels.create(Channel(twitch_id=channel_id, name=channel_name))

        user.name = user_name
        user.linked_channels[channel.id] = level
        user.regenerate_link_code()
        channel.linked_users[user.id] = level
        database.users.save(user)
        database.channels.save(channel)

    if request.get("type") == "join":
        user_id: str = request.get("userId")
        user_name: str = request.get("userName")
        channel_id: str = request.get("channelId")
        user_image: str = request.get("img")
        if (
            not user_id or not user_name
            or not channel_id or not user_image
        ):
            return

        if channel_id == user_id:
            level = Permission.Broadcaster
        elif str(request.get("mod")) == "True":
            level = Permission.Moderator
        elif str(request.get("vip")) == "True":
            level = Permission.VIP
        elif str(request.get("sub")) == "True":
            level = Permission.Subscriber
        else:
            level = Permission.Basic

        channel = channel_by_twitch_id(channel_id)
        game = games.get(channel.id)
        if game is None:
            raise ClientError("no active game on this channel")

        worker = game.entities.get(user_id)
        if worker is None:
            worker = Entity(
                entity_type=EntityType.Worker,
                id=user_id,
                name=user_name,
                position=game.empty_space_near(Position(0,0)),
                job=random.choice([Job.Lumberjack, Job.Farmer, Job.Miner]),
                priority=random.choice(resource_types),
                image=unquote(user_image),
            )
            await game.add_entity(worker)
        worker.name = user_name

    if request.get("type") == "job":
        user_id: str = request.get("userId")
        channel_id: str = request.get("channelId")
        job_input: str = request.get("job")

        if not user_id or not channel_id or not job_input:
            return

        try:
            job = Job(job_input.lower())
        except ValueError:
            return

        channel = channel_by_twitch_id(channel_id)
        game = games.get(channel.id)
        if game is None:
            raise ClientError("no active game on this channel")

        worker = game.entities.get(user_id)
        if worker is None:
            worker = Entity(
                entity_type=EntityType.Worker,
                id=user_id,
                name=user_name,
                position=game.empty_space_near(Position(0,0)),
                job=job,
                priority=random.choice(resource_types),
            )
            await game.add_entity(worker)
        else:
            worker.job = job
