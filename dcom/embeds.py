from discord import Embed


def get_help():
    embed = Embed(
        color=0x2ecc71,  # green
    )
    embed.add_field(
        name="$upvote",
        value="Upvotes a post with the specified voting weight."
              "```$upvote <post_url> <vote_weight_in_percent>```",
        inline=False,
    )

    embed.add_field(
        name="$register",
        value="Registers your STEEM account with your Discord ID"
              "```$register <steem_username>```",
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

    return embed


def get_vote_details(author, permlink, weight, voter):
    """
    A simple embed to post auto curation details.
    """
    embed = Embed(
        color=0x2ecc71,  # green
    )
    embed.add_field(
        name="Post",
        value=f"<https://steemit.com/{author}/{permlink}>",
        inline=False,
    )
    embed.add_field(
        name="Vote weight",
        value=f"%{weight}",
    )

    embed.add_field(
        name="Voted by",
        value=voter
    )

    return embed
