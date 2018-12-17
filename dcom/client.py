import asyncio
import datetime
import sys
import uuid

import discord
import discord.utils
from discord.ext import commands
from lightsteem.client import Client as LightsteemClient
from lightsteem.datastructures import Operation
from pymongo import MongoClient


class DcomClient(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = kwargs.get("dcom_config")
        self.lightsteem_client = LightsteemClient(
            nodes=self.config["steem_nodes"],
            keys=[self.config["bot_posting_key"]]
        )
        self.community_name = self.config.get("community_name")
        self.registration_channel = self.config.get("registration_channel")
        self.registration_account = self.config.get("registration_account")
        self.role_name_for_registered_users = self.config.get(
            "role_name_for_registered_users")
        self.curation_channels = self.config.get("curation_channels")
        self.mongo_client = MongoClient(self.config.get("M0NGO_URI"))
        self.mongo_database = self.mongo_client["dcom"]

    @asyncio.coroutine
    def on_ready(self):
        print(self.user.name)
        print(self.user.id)
        if len(self.servers) > 1:
            sys.exit('This bot may run in only one server.')
        print(f'Running on {self.running_on.name}')

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

    def refund(self, to, amount):
        transfer_op = Operation('transfer', {
            'from': self.registration_account,
            'to': to,
            'memo': 'Successful registration. '
                    f'Welcome to {self.community_name}.',
            'amount': amount,
        })
        # swap posting key with active key
        # workaround for a lightsteem quirk
        old_keys = self.lightsteem_client.keys
        try:
            self.lightsteem_client.keys = [
                self.config.get("registration_account_active_key")]
            self.lightsteem_client.broadcast(transfer_op)
        finally:
            self.lightsteem_client.keys = old_keys

    def steem_username_is_valid(self, username):
        try:
            resp = self.lightsteem_client(
                'condenser_api').get_accounts([username])

            return bool(len(resp))
        except Exception as e:
            # retry logic on node failures
            return self.steem_username_is_valid(username)

    def get_verification_code(self, steem_username, discord_author):
        old_verification_code = self.mongo_database["verification_codes"]. \
            find_one({
                "verified": False,
                "steem_username": steem_username,
                "discord_id": str(discord_author),
            })
        if old_verification_code:
            verification_code = old_verification_code["code"]
            self.mongo_database["verification_codes"].update_one(
                {"code": old_verification_code["code"]},
                {'$set': {"last_update": datetime.datetime.utcnow()}}
            )
        else:
            verification_code = str(uuid.uuid4())
            self.mongo_database["verification_codes"].insert({
                "steem_username": steem_username,
                "discord_id": str(discord_author),
                "discord_backend_id": discord_author.id,
                "code": verification_code,
                "verified": False,
                "last_update": datetime.datetime.utcnow(),
            })

        return verification_code

    @property
    def running_on(self):
        return list(self.servers)[0]

    async def verify(self, memo, amount, _from):
        # check the memo is a valid verification code, first.
        verification_code = self.mongo_database["verification_codes"]. \
            find_one({
            "code": memo,
            "verified": False,
            "steem_username": _from,
        })

        if not verification_code:
            return

        # add the "registered" role to the user
        server = self.running_on
        member = server.get_member(verification_code["discord_backend_id"])
        role = discord.utils.get(
            server.roles,
            name=self.role_name_for_registered_users)

        await self.add_roles(member, role)

        # send an informative message to the channel about the verification
        # status
        channel = discord.Object(self.registration_channel)
        await self.send_message(
            channel,
            f":wave: Success! **{verification_code['steem_username']}**"
            f" has been successfully registered with "
            f" <@{verification_code['discord_backend_id']}>."
        )

        # mark the code as verified
        self.mongo_database["verification_codes"].update_one(
            {"code": memo},
            {'$set': {"verified": True}}
        )

        # refund the user
        self.refund(verification_code["steem_username"], amount)

    async def check_transfers(self):
        processed_memos = set()
        await self.wait_until_ready()
        while not self.is_closed:
            # If there are no waiting verifications
            # There is no need to poll the account history
            one_hour_ago = datetime.datetime.utcnow() - \
                           datetime.timedelta(minutes=60)
            waiting_verifications = self.mongo_database["verification_codes"]. \
                count({"last_update": {
                "$gte": one_hour_ago}, "verified": False})

            if waiting_verifications > 0:
                print(f"Waiting {waiting_verifications} verifications. "
                      f"Checking transfers")
                try:
                    # Poll the account history and check for the
                    # STEEM transfers
                    account = self.lightsteem_client.account(
                        self.registration_account)
                    for op in account.history(
                            stop_at=one_hour_ago,
                            filter=["transfer"]):
                        if op.get("memo") in processed_memos:
                            continue
                        if op.get("from") == self.registration_account:
                            continue

                        await self.verify(
                            op.get("memo"),
                            op.get("amount"),
                            op.get("from")
                        )
                        processed_memos.add(op.get("memo"))

                except Exception as e:
                    print(e)

            await asyncio.sleep(5)