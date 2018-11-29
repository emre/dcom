from datetime import datetime

from dateutil.parser import parse


def parse_author_and_permlink(url):
    """
    Parses a typical steem URL and returns a tuple
    including the author and permlink.
    Ex: http://steemit.com/@author/permlink
    """
    try:
        author = url.split("@")[1].split("/")[0]
        permlink = url.split("@")[1].split("/")[1]
    except IndexError as e:
        raise ValueError("This is not valid Steem permlink.")

    return author, permlink


def get_post_content(lightsteem_client, author, permlink):
    """
    Gets the raw content of the post from the STEEM
    blockchain.
    """
    post_content = lightsteem_client.get_content(author, permlink)
    if not post_content.get("author"):
        # this case might happen if the link is valid but the post
        # doesn't exists in the blockchain.
        raise ValueError("This content is not available on the blockchain.")

    return post_content


def in_curation_window(comment, max_age=561600, min_age=800):
    """
    Based on the max_age (seconds) checks the post is votable or not.
    """
    if isinstance(max_age, str):
        max_age = int(max_age)

    if isinstance(min_age, str):
        min_age = int(min_age)

    created_at = parse(comment["created"])
    diff_in_seconds = (datetime.utcnow() - created_at).total_seconds()

    if diff_in_seconds < min_age:
        raise ValueError(
            f"Posts are eligible for an upvote after {min_age} seconds."
            f"Wait {int(min_age - diff_in_seconds)} more seconds.")

    if diff_in_seconds > max_age:
        raise ValueError("Post is too old.")

    return True


def already_voted(comment, voter):
    return voter in [v["voter"] for v in comment["active_votes"]]


def channel_is_whitelisted(channel, channel_whitelist):
    return channel.id in channel_whitelist
