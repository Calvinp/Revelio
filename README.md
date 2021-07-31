# Revelio

A discord bot to post writing prompts to your server.

## Description

This bot takes user-generated writing prompts and sends them to your discord server, one per day.

Prompts are not provided. It is expected that you will provide them. 
To facilitate this, the `new_prompts` command allows you to add new prompts. 
It can take a list of prompts (one per line, no special characters) as either part of the same discord message as the command, or a plain-text file uploaded in the same message as the command.
It can read through Discord spoilers, so you can upload the new prompts without others who would rather wait until the day it's posted seeing them in their feed.
You can set a command channel and a prompt channel. They can be the same for convenience, or different to separate bot interaction from reflection.

When the bot starts running out of prompts, it will send a warning with each prompt so that you know to add more. The threshold at which the warning will be sent is configurable.
When the bot runs out of prompts completely, it can start repeating old prompts. It can be configured not to do this using the `set_send_repeat_prompts` command.

### Commands

The bot will automatically send a prompt once per day. In addition, the following commands are provided to enhance the bot's functionality:
* `new_prompts` - Use this to input new prompts to the bot. It can accept prompts in two ways:
  1. A plain-text file (not an MS Word file), with each prompt on its own line.
  2. As part of the Discord message, with each prompt on its own line. Note that I can read through spoiler tags, so feel free to use them to avoid spoiling the prompts for the rest of the server.
  * Note that these are mutually exclusive. If there is a file attachment, the bot will ignore the rest of the message.
  * IMPORTANT - Don't put any text in the message with this command other than prompts, or the bot will add the text as a prompt.
* `send_prompt` - Forces the bot to send a prompt off schedule. This will be in addition to the usual daily prompt.
* `prompts_left` - Replies with the number of prompts left that have not been sent before.
* `get_time_to_send_prompt` - Replies with the time of day at which the bot will send a prompt.
* `set_time_to_send_prompt` - Use this to set the time of day at which the bot will send a prompt. Put the whole time in quotes if you plan to specify a timezone.
* `countdown` - Replies with the amount of time until the next time the bot will automatically send a prompt.
* `get_warn_threshold` - Replies with the threshold (in number of remaining prompts) at which the bot will start sending a warning that it is running out.
* `set_warn_threshold` - Use this to set the threshold (in number of remaining prompts) at which the bot will start sending a warning that it is running out. Too high and people may ignore it. Too low and you may not have time to find new prompts to send. This command allows you to set a value that works for your group.
* `get_send_repeat_prompts` - Replies with whether the bot is configured to send repeat prompts or not if it runs out of fresh prompts.
* `set_send_repeat_prompts` - Use this to configure whether the bot will send repeat prompts or not if it runs out of fresh prompts.
* `pause` - Use this to set the number of days to skip before sening another prompt. Supply 0 to stop skipping days.
* `uptime` - Replies with the amount of time since the bot started up.
* `make_backup` - Makes a local backup of the bot's prompt database and settings. Settings contains the Discord Token secret, so it cannot send you the backup.
* `ping` - Replies `Pong` so you know the bot is up.
* `test` - Replies with information about the server the bot is connected to.
* `prompt_channel_test` - Posts a test message to the prompt channel to verify that it is set properly.

## Setup the Bot

* Clone this repository
* The bot was developed using Python version 3.9.5. If you have an older version and somehing isn't working, update to 3.9.5 first.
* Install the discord and dateutil libraries using pip
```
pip install discord.py
pip install python-dateutil
```
* If you don't already have a Discord token for the bot, [create one](https://www.writebots.com/discord-bot-token/).
* Create a file called `settings.json`. Its contents should look something like this, but feel free to change them to match your situation and preferences:
```
{
    "DiscordToken": "(Your Token)",
    "DiscordGuild": "(Your Server Name)",
    "PromptChannel": "revelio",
    "CommandChannel": "revelio-cmd",
    "CommandPrefix": ".",
    "TimeToSendPrompt": "12:00am EDT",
    "PauseDays": 0,
    "WarnThreshold": 2,
    "DebugMode": false,
    "SendRepeatPrompts": true
}
```
* Run the bot with `python main.py`
* The bot doesn't come with any prompts, so use the `new_prompts` command (in Discord) to provide a list of prompts.

## License

This project is licensed under the GPL v3.0 License - see the LICENSE.md file for details.

## Acknowledgments

* [How to Make a Discord Bot in Python](https://realpython.com/how-to-make-a-discord-bot-python/)
* [discord.py Documentation](https://discordpy.readthedocs.io/en/stable/index.html)
* [Timezone abbreviations](https://gist.github.com/h-j-13/e3a585796510b59601e34a07e99b386d)
* [Readme Template](https://gist.github.com/DomPizzie/7a5ff55ffa9081f2de27c315f5018afc)