import asyncio

from discord.ext import commands
from lightsteem.client import Client as LightsteemClient
from lightsteem.datastructures import Operation


class DcomClient(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = kwargs.get("dcom_config")
        self.lightsteem_client = LightsteemClient(
            nodes=self.config["steem_nodes"],
            keys=[self.config["bot_posting_key"], ]
        )

    @asyncio.coroutine
    def on_ready(self):
        print(self.user.name)
        print(self.user.id)

    def say_error(self, error):
        return self.say(f"**Error:** {error}")

    def say_success(self, message):
        return self.say(f":thumbsup: {message}")

    def upvote(self, post_content, weight):
        vote_op = Operation('vote', {
            'voter': self.config.get("bot_account"),
            'author': post_content.get("author"),
            'permlink': post_content.get("permlink"),
            'weight': weight * 100
        })
        self.lightsteem_client.broadcast(vote_op)
