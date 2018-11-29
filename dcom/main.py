import os

from discord import Embed
from dotenv import load_dotenv

from .client import DcomClient
from .utils import (
    parse_author_and_permlink,
    get_post_content,
    already_voted,
    in_curation_window,
    channel_is_whitelisted
)


def main():
    # load environment vars from the .env file
    load_dotenv()

    # map environment vars to our config
    config = {
        "bot_account": os.getenv("BOT_ACCOUNT"),
        "bot_posting_key": os.getenv("BOT_POSTING_KEY"),
        "steem_nodes": os.getenv("STEEM_NODES").split(",")
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
        vp = bot.lightsteem_client.account(os.getenv("BOT_ACCOUNT")).vp()
        await bot.say_success(f"Voted. Current vp: %{vp}")

    @bot.command()
    async def vp():
        vp = bot.lightsteem_client.account(os.getenv("BOT_ACCOUNT")).vp()
        await bot.say(f"Current vp: %{vp}")

    @bot.command(pass_context=True)
    async def help(ctx):
        embed = Embed(
            color=0x2ecc71, # green
        )
        embed.add_field(
            name="$upvote",
            value="Upvotes a post with the specified voting weight."
                  "```$upvote <post_url> <vote_weight_in_percent>```",
            inline=False,
        )
        embed.add_field(
            name="$vp",
            value="Shows the current voting power.",
            inline=False,
        )
        embed.add_field(
            name="$help",
            value="Shows this message.",
            inline=False,
        )
        await bot.send_message(
            ctx.message.channel, "Available commands", embed=embed)

    # shoot!
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))


if __name__ == "__main__":
    main()
