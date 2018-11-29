# dcom

dcom *(discord community bot)* is a discord bot for communities to trigger
upvotes from specified discord channels/servers.

# Installation

```bash
$ pip install dcom
```

# Configuration

Configurations happens on environment variables. However, you can also use .env files.
Create an .env file where you run the ```dcom```.

Example .env file:

```
BOT_ACCOUNT=<bot_username>
BOT_POSTING_KEY=<bot_posting_key>
STEEM_NODES=https://api.steemit.com
DISCORD_BOT_TOKEN=<discord_bot_token>
CHANNEL_WHITELIST=<channel_id_1>,<channel_id_2>
LATE_CURATION_WINDOW=561600
EARLY_CURATION_WINDOW=800
CURATOR_GROUPS=curators,admins
```


# Running

```bash
$ dcom
```

That's it.


