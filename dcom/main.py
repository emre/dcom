import os
import os.path

from dotenv import load_dotenv

from .client import DcomClient
from .embeds import get_help
from .utils import (
    parse_author_and_permlink,
    get_post_content,
    already_voted,
    in_curation_window,
    channel_is_whitelisted
)

import aiohttp


def main():
    # load environment vars from the .env file

    load_dotenv(dotenv_path=os.path.expanduser("~/.dcom_env"))

    # map environment vars to our config
    config = {
        "bot_account": os.getenv("BOT_ACCOUNT"),
        "bot_posting_key": os.getenv("BOT_POSTING_KEY"),
        "steem_nodes": os.getenv("STEEM_NODES").split(","),
        "mongo_uri": os.getenv("MONGO_URI"),
        "registration_channel": os.getenv("REGISTRATION_CHANNEL"),
        "registration_account": os.getenv("REGISTRATION_ACCOUNT"),
        "registration_account_active_key": os.getenv(
            "REGISTRATION_ACCOUNT_ACTIVE_KEY"),
        "role_name_for_registered_users": os.getenv(
            "ROLE_FOR_REGISTERED_USERS"),
        "patron_role": os.getenv("PATRON_ROLE"),
        "community_name": os.getenv("COMMUNITY_NAME"),
        "bot_log_channel": os.getenv("BOT_LOG_CHANNEL"),
        "account_for_vp_check": os.getenv("ACCOUNT_FOR_VP_CHECK"),
        "limit_on_maximum_vp": os.getenv("LIMIT_ON_MAXIMUM_VP"),
        "auto_curation_vote_weight": os.getenv("AUTO_CURATION_VOTE_WEIGHT"),
    }

    # init the modified Discord client
    bot = DcomClient(
        command_prefix="$",
        dcom_config=config)

    # remove the default help command, we're overriding a better one.
    bot.remove_command("help")

    # register the commands
    @bot.command(pass_context=True)
    async def upvote(ctx, url, weight):

        # only members of specified groups can use the bot.
        specified_groups = set(os.getenv("CURATOR_GROUPS").split(","))
        user_roles = set([r.name for r in ctx.message.author.roles])
        if not len(user_roles.intersection(specified_groups)):
            await bot.say("You don't have required permissions to do that.")
            return

        # check the channel is suitable
        if not channel_is_whitelisted(
                ctx.message.channel,
                os.getenv("CHANNEL_WHITELIST").split(",")):
            return

        # Try to parse author and permlink from the URL
        try:
            author, permlink = parse_author_and_permlink(url)
        except ValueError as e:
            await bot.say_error(e.args[0])
            return

        # check the post availability (It might be deleted.)
        try:
            post_content = get_post_content(
                bot.lightsteem_client,
                author,
                permlink)
        except ValueError as e:
            await bot.say_error(e.args[0])
            return

        # check the author is blacklisted in other communities.
        session = aiohttp.ClientSession()
        resp = await session.get(
            f"http://blacklist.usesteem.com/user/{author}")
        if resp.status != 200:
            print("Blacklist api returned non-200. Skipping the check.")
        else:
            response_in_json = await resp.json()
            if len(response_in_json["blacklisted"]):
                await bot.say(
                    f":x: Caution. This author @{author} is on a blacklist "
                    "and has **not** been upvoted."
                    " Please select another winner."
                )
                return

        # check if we already voted that post
        if already_voted(post_content, os.getenv("BOT_ACCOUNT")):
            await bot.say_error("Already voted on that post.")
            return

        # check the post in specified curation windows
        try:
            in_curation_window(
                post_content,
                max_age=os.getenv("LATE_CURATION_WINDOW"),
                min_age=os.getenv("EARLY_CURATION_WINDOW"))
        except Exception as e:
            await bot.say_error(e.args[0])
            return

        # check the weight
        try:
            weight = int(weight)
        except ValueError as e:
            await bot.say_error("Invalid weight.")
            return

        if weight < 0 or weight > 100:
            await bot.say_error("Invalid weight. It must be between [0-100].")
            return

        bot.upvote(post_content, weight)
        await bot.say_success(f"Voted.")

    @bot.command()
    async def vp():
        vp = bot.lightsteem_client.account(
            os.getenv("ACCOUNT_FOR_VP_CHECK")).vp()
        await bot.say(f"Current vp: %{vp}")

    @bot.command(pass_context=True)
    async def help(ctx):
        await bot.send_message(
            ctx.message.channel, "Available commands", embed=get_help())

    @bot.command(pass_context=True)
    async def register(ctx, username):

        await bot.send_typing(ctx.message.channel)

        # check the channel is suitable
        if ctx.message.channel.id != os.getenv("REGISTRATION_CHANNEL"):
            await bot.say(
                f"Use the <#{bot.registration_channel}> channel for "
                f"the registration commands.")
            return

        # check the username is valid
        if not bot.steem_username_is_valid(username):
            await bot.say_error(f"`{username}` is not an existing STEEM "
                                f"username. If you would like one, please "
                                f"ask for support in the #general channel.")
            return

        verification_code = bot.get_verification_code(
            username,
            ctx.message.author,
        )

        message = f":right_facing_fist: :left_facing_fist: " \
                  f"To register **{username}** with " \
                  f"{ctx.message.author.mention}, please send 0.001 STEEM or" \
                  f" 0.001 SBD to" \
                  f" `{bot.registration_account}` with the following memo:" \
                  f" ```{verification_code}```"

        await bot.say(message)

    # create a timer-task for registrations
    bot.loop.create_task(bot.check_transfers())

    # create a timer-task for auto-curation logic
    bot.loop.create_task(bot.auto_curation())

    # shoot!
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))


if __name__ == "__main__":
    main()
