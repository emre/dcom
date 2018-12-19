import asyncio
import datetime
import random
import sys
import uuid

import discord
import discord.utils
from dateutil.parser import parse
from discord.ext import commands
from lightsteem.client import Client as LightsteemClient
from lightsteem.datastructures import Operation
from pymongo import MongoClient

from .embeds import get_vote_details


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
        self.patron_role = self.config.get("patron_role")
        self.bot_log_channel = self.config.get("bot_log_channel")
        self.account_for_vp_check = self.config.get("account_for_vp_check")
        self.limit_on_maximum_vp = self.config.get("limit_on_maximum_vp")
        self.bot_account = self.config.get("bot_account")
        self.auto_curation_vote_weight = 20

    @asyncio.coroutine
    def on_ready(self):
        print(self.user.name)
        print(self.user.id)
        if len(self.servers) > 1:
            sys.exit('This bot may run in only one server.')
        print(f'Running on {self.running_on.name}')

    @asyncio.coroutine
    async def on_member_update(self, before, after):
        # This callback works every time a member is updated on Discord.
        # We use this to sync members having "patron" as a role.

        before_roles = [r.name for r in before.roles]
        after_roles = [r.name for r in after.roles]
        channel = discord.Object(self.bot_log_channel)

        if self.patron_role in before_roles and \
                self.patron_role not in after_roles:
            # looks like the user lost access to patron role
            await self.send_message(
                channel,
                f":broken_heart: {after.mention} lost patron rights."
            )
            self.mongo_database["patrons"].delete_many(
                {"discord_id": str(after)})
        elif self.patron_role in after_roles and \
                self.patron_role not in before_roles:
            # we have a new patron
            await self.send_message(
                channel,
                f":green_heart: {after.mention} gained patron rights."
            )
            self.mongo_database["patrons"].insert(
                {"discord_id": str(after)}
            )

    def say_error(self, error):
        return self.say(f"**Error:** {error}")

    def say_success(self, message):
        return self.say(f":thumbsup: {message}")

    def upvote(self, post_content, weight, author=None, permlink=None):
        vote_op = Operation('vote', {
            'voter': self.config.get("bot_account"),
            'author': author or post_content.get("author"),
            'permlink': permlink or post_content.get("permlink"),
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

    def get_a_random_patron_post(self):

        # Get a list of verified discord members having the role "patron:
        patron_users = list(self.mongo_database["patrons"].find())
        patron_users_ids = [u["discord_id"] for u in patron_users]
        verified_patrons = list(self.mongo_database["verification_codes"] \
                                .find({
            "verified": True,
            "discord_id": {"$in": patron_users_ids}}
        ).distinct("steem_username"))

        # Remove the patrons already voted in the last 24h.
        curated_authors = self.get_curated_authors_in_last_24_hours()
        verified_patrons = set(verified_patrons) - curated_authors

        print("Patrons", verified_patrons)
        # Prepare a list of patron posts
        posts = []
        for patron in verified_patrons:
            posts.append(self.get_last_votable_post(patron))

        if len(posts):
            # We have found some posts, shuffle it and
            # return the first element.
            random.shuffle(posts)
            return posts[0]

    def get_curated_authors_in_last_24_hours(self):
        """
        Returns a set of authors curated
        by the self.bot_account.
        """
        account = self.lightsteem_client.account(self.bot_account)
        one_day_ago = datetime.datetime.utcnow() - \
                      datetime.timedelta(days=1)
        voted_authors = set()
        for op in account.history(filter=["vote"], stop_at=one_day_ago):
            if op["voter"] != self.bot_account:
                continue

            voted_authors.add(op["author"])

        return voted_authors

    def get_last_votable_post(self, patron):
        """
        Returns a list of [author, permlink] lists.
        Output of this function is designed to be used in automatic curation.
        """
        posts = self.lightsteem_client.get_discussions_by_blog(
            {"limit": 7, "tag": patron})
        for post in posts:

            # exclude reblogs
            if post["author"] != patron:
                continue

            # check if it's votable
            created = parse(post["created"])
            diff_in_seconds = (datetime.datetime.utcnow() - created). \
                total_seconds()

            # check if the post's age is lower than 6.5 days
            if diff_in_seconds > 561600:
                break

            # check if we already voted on that.
            voters = [v["voter"] for v in post["active_votes"]]
            if self.account_for_vp_check in voters or \
                    self.bot_account in voters:
                continue

            return post["author"], post["permlink"]

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
            print("[task start] check_transfers()")
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

            print("[task finish] check_transfers()")
            await asyncio.sleep(10)

    async def auto_curation(self):
        channel = discord.Object(self.bot_log_channel)
        await self.wait_until_ready()
        while not self.is_closed:
            try:
                print("[task start] auto_curation()")
                # vp must be eligible for automatic curation
                acc = self.lightsteem_client.account(self.account_for_vp_check)
                if acc.vp() >= int(self.limit_on_maximum_vp):

                    # get the list of registered patrons
                    post = self.get_a_random_patron_post()
                    if post:
                        author, permlink = post
                        self.upvote(
                            None,
                            self.auto_curation_vote_weight,
                            author=author,
                            permlink=permlink
                        )
                        await self.send_message(
                            channel,
                            f"**[auto-curation round]**",
                            embed=get_vote_details(
                                author, permlink,
                                self.auto_curation_vote_weight,
                                self.bot_account)
                        )
                    else:
                        await self.send_message(
                            channel,
                            f"**[auto-curation round]** Couldn't find any "
                            f"suitable post. Skipping."
                        )
                else:
                    await self.send_message(
                        channel,
                        f"**[auto-curation round]** Vp is not enough."
                        f" ({acc.vp()}) Skipping."
                    )
                print("[task finish] auto_curation()")
            except Exception as e:
                print(e)
            await asyncio.sleep(900)
