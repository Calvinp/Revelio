import logging, traceback, asyncio, sys
from discord.ext import commands, tasks
from discord import utils
from json import dump, load
from os import path, makedirs, remove
from datetime import datetime, timedelta
from random import choice
from dateutil.parser import parse
from timezones import whois_timezone_info

# Global Constants
directory = path.dirname(path.abspath(__file__))
tmpFilePath = directory + "/tmpFile.txt"
promptsPath = directory + "/prompts.json"
settingsPath = directory + "/settings.json"
backupsPath = directory + "/backups"
newPromptsHelp = """
    Inputs new prompts. I can accept prompts in two ways:
    1. A plain-text file (As you would create in Notepad - *not* an MS Word file), with each prompt on its own line.
    2. As part of the Discord message, with each prompt on its own line. Note that I can read through spoiler tags, so feel free to use them to avoid spoiling the prompts for the rest of the server.
    Note that these are mutually exclusive. If there is a file attachment, I will ignore the rest of the message.
    IMPORTANT - Don't put any text in the message with this command other than prompts, or I might add the text as a prompt.
"""

# Helpers
def loadJson(path):
    with open(path, "r") as json_file:
        return load(json_file)
        
def saveJson(path, jsonToSave):
    with open(path, 'w', encoding='utf-8') as json_file:
        dump(jsonToSave, json_file, ensure_ascii=False, indent=4)
        
def loadPrompts():
    try:
        return loadJson(promptsPath)
    except:
         return []
         
def savePrompts(prompts):
    saveJson(promptsPath, prompts)
    
def loadSettings():
    return loadJson(settingsPath)
    
def saveSettings(settingsToSave):
    saveJson(settingsPath, settingsToSave)
    
def parseTzAware(timeStr):
    return parse(timeStr, tzinfos=whois_timezone_info)

# If we're less than this many seconds to the next run, skip today 
# (to prevent issues caused by now changing during calculations)
fuzzFactor = 2

# Parses the time string, and returns the
# next time we will hit the time of day specified
def nextInstance(timeStr):
    time = parseTzAware(timeStr)
    now = datetime.now()
    time = datetime(year=now.year, month=now.month, day=now.day, hour=time.hour, minute=time.minute, second=time.second)
    timeTo = time - now
    if timeTo < timedelta(seconds=fuzzFactor):
        time += timedelta(days=1)
    return time

# Parses the time string, and returns the time until the 
# next time we will hit the time of day specified (as a timedelta).
def timeToNextInstance(timeStr):
    return nextInstance(timeStr) - datetime.now()

# Load settings and save global settings into variables.
settings = loadSettings()
TOKEN = settings["DiscordToken"]
PREFIX = settings["CommandPrefix"]
DEBUG_MODE = settings["DebugMode"]

# Other setup
sendHours = 0
sendMinutes = 1
sendSeconds = 0
# In DEBUG_MODE, we don't send a prompt on a schedule.
# Send once per minute instead.
if DEBUG_MODE: 
    sendHours = 0
    sendMinutes = 1
    sendSeconds = 0
bot = commands.Bot(command_prefix=PREFIX)
startupTime = datetime.now()

class Prompts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.prompts = loadPrompts()
        self.sendPromptLoop.start()
        self.warnThreshold = settings["WarnThreshold"]
        self.guild = settings["DiscordGuild"]
        self.channel = settings["DiscordChannel"]
        self.pauseDays = settings["PauseDays"]
        self.sendRepeatPrompts = settings["SendRepeatPrompts"]
        self.timeToSendPrompt = settings["TimeToSendPrompt"]
        self.claimedDays = {}
        # Note - don't take the lock and do something that will take a long time 
        # or you'll block everyone else from using the bot for shared access.
        self.lock = asyncio.Lock()
        
    # Tells us if we are allowed to post; only if ctx is self.guild.
    def bot_check(self, ctx):
        return ctx.guild and ctx.guild.name == self.guild and ctx.channel and ctx.channel.name == self.channel
    
    # Sets the number of days until we start sending prompts again.
    def setPauseDays(self, newPauseDays):
        self.pauseDays = newPauseDays
        settings["PauseDays"] = self.pauseDays
        saveSettings(settings)
      
    # Decreases by 1 the number of days until we start sending prompts again.
    def decrementPauseDays(self):
        self.setPauseDays(self.pauseDays - 1)
    
    # Adds the given prompts to our prompts database.
    def addPrompts(self, prompts):
        if len(self.prompts) == 0:
            self.prompts.append([])
        self.prompts[0] += prompts
        savePrompts(self.prompts)
    
    # Makes a local backup of our prompts and settings database.
    def makeBackup(self):
        try:
            makedirs(backupsPath)
        except OSError as e: # I'm sorry OS, did I offend you by making a directory that already exists?.
            pass # (I'm not actually sorry)
        currentTime = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        settingsBackupPath = backupsPath + f"/settings.{currentTime}.json"
        promptsBackupPath = backupsPath + f"/prompts.{currentTime}.json"
        saveJson(settingsBackupPath, settings)
        saveJson(promptsBackupPath, self.prompts)
    
    # Parses a list of prompts.
    async def parsePrompts(self, ctx):
        message = ctx.message
        attachments = message.attachments
        prompts = []
        if attachments:
            for attachment in attachments:
                filePath = tmpFilePath
                await attachment.save(filePath)
                try:
                    with open(filePath, "r") as file:
                        for line in file:
                            prompts.append(line.replace("\n", ""))
                finally:
                    if path.exists(filePath):
                        remove(filePath)
        else:
            scrubbedContent = message.content.replace(f"{PREFIX}new_prompts", "").replace("||", "")
            prompts = scrubbedContent.splitlines()
        while "" in prompts:
            prompts.remove("")
        return prompts
    
    @commands.command(name="new_prompts", help=newPromptsHelp)
    async def newPrompts(self, ctx: commands.Context):
        try:
            prompts = await self.parsePrompts(ctx)
            self.addPrompts(prompts)
            await ctx.send(f"Succesfully added {len(prompts)} new prompts. I now have {len(self.prompts[0])} total prompts that have never been sent.")
        except:
            await ctx.send("""
            An error occurred reading and parsing your prompts. 
If they're in an MS Word file, try copying it into a plain text file. 
On Windows, Notepad makes plain text files by default. 
On Mac, TextEdit can make plain text files by config - google how to. 
If the file is already a plain text file, or you didn't even attach a file, ping Calvin and ask him to to debug his code.
            """)
    
    # Function that actually sends a prompt if possible.
    # It will send repeats with a warning.
    # It can also provide a warning if there aren't many prompts left.
    async def doSendPrompt(self, ctx):
        message = ""
        numRepetitions = 0
        while len(self.prompts) > numRepetitions + 1 and len(self.prompts[numRepetitions]) == 0:
            numRepetitions += 1
        if len(self.prompts) == 0 or len(self.prompts[numRepetitions]) == 0:
            await ctx.send(f"I don't have any prompts to post. I will look again tomorrow, or when someone issues the command `{PREFIX}send_prompt`.\nYou can add more prompts by issuing the command `{PREFIX}new_prompts`. You can use `{PREFIX}help new_prompts` to learn how to use `{PREFIX}new_prompts`.")
            return
        elif len(self.prompts[0]) == 0 and not self.sendRepeatPrompts:
            await ctx.send(f"I have run out of prompts, and SendRepeatPrompts is set to false. If you would like to see a repeated prompt, you can send the command `{PREFIX}set_send_repeat_prompts true` and I will go through old prompts again.")
            return
        prompt = choice(self.prompts[numRepetitions])
        self.prompts[numRepetitions].remove(prompt)
        if len(self.prompts) == numRepetitions + 1:
            self.prompts.append([])
        self.prompts[numRepetitions + 1].append(prompt)
        message += f"Your prompt for today:\n"
        message += "> **" + prompt + "**\n"
        if len(self.prompts[0]) < self.warnThreshold:
            message += "```\nWARNING\n"
            if numRepetitions == 0:
                message += f"I have {len(self.prompts[numRepetitions])} more prompts. "
                message += f"After that, I will have to start repeating prompts. "
            else:
                message += f"I have already sent this prompt {numRepetitions} times. " 
                message += f"I have {len(self.prompts[numRepetitions])} more prompts that have been repeated {numRepetitions} times. " 
                message += f"After that, I will have to start repeating prompts another time. "
            message += f"\nYou can add more prompts by issuing the command {PREFIX}new_prompts. "
            message += f"You can use {PREFIX}help new_prompts to learn how to use {PREFIX}new_prompts."
            message += f"```\n"
        await ctx.send(message)
        savePrompts(self.prompts)
        self.makeBackup()
        
    # Returns whether we can send a prompt (false if someone else has claimed
    # the right to send a prompt for the day already).
    async def canSendPrompt(self):
        await self.lock.acquire()
        try:
            promptDay = nextInstance(self.timeToSendPrompt)
            promptDayStr = f"{promptDay.year}_{promptDay.month}_{promptDay.day}"
            if promptDayStr in self.claimedDays and self.claimedDays[promptDayStr]:
                return False
            self.claimedDays[promptDayStr] = True
            return True
        finally:
            self.lock.release()

    # Version of sendPrompt that runs in a loop (not on command) to send prompts at the set time of day.
    @tasks.loop(seconds=sendSeconds, minutes=sendMinutes, hours=sendHours)
    async def sendPromptLoop(self):
        guild = utils.get(bot.guilds, name=self.guild)
        channel = utils.get(guild.channels, name=self.channel)
        canSend = await self.canSendPrompt()
        if canSend: 
            if not DEBUG_MODE:
                waitTime = timeToNextInstance(self.timeToSendPrompt)
                await asyncio.sleep(waitTime.total_seconds())
            if (self.pauseDays == 0):
                await self.doSendPrompt(channel)
            else:
                self.decrementPauseDays()
                await channel.send(f"I am not sending a prompt today because I am paused. I will be paused for {self.pauseDays} more days. You can change the number of days to stay paused by issuing `{PREFIX}pause <days>`, or get a prompt anyway with `{PREFIX}send_prompt`")

    # Runs before starting the loop (not before each iteration)
    @sendPromptLoop.before_loop 
    async def beforeSendPrompt(self):
        print("Connecting to Discord.")
        await bot.wait_until_ready()
        print("Connected to Discord.")
        
    @commands.command(name="send_prompt", help="Forces me to send a prompt now, even if it's not on schedule. This does not interrupt my regular schedule.")
    async def sendPromptCommand(self, ctx: commands.Context):
        await self.doSendPrompt(ctx)
        
    @commands.command(name="prompts_left", help="Replies with the number of prompts I have left until I will have to start repeating prompts.")
    async def promptsLeft(self, ctx: commands.Context):
        message = ""
        if len(self.prompts) == 0 or len(self.prompts[0]) == 0:
            message += f"I have no more prompts that have not been repeated."
        else:
            numPrompts = len(self.prompts[0])
            message += f"I have {numPrompts} more prompts. "
            message += f"After that, I will have to start repeating prompts. "
        message += f"\nYou can add more prompts by issuing the command `{PREFIX}new_prompts`."
        message += f"You can use `{PREFIX}help new_prompts` to learn how to use `{PREFIX}new_prompts`."
        await ctx.send(message)
        
    @commands.command(name="get_warn_threshold", help="Gets the warning threshold. If I have less prompts than this threshold, I will include a warning with the prompt.")
    async def getWarnThreshold(self, ctx: commands.Context):
        await ctx.send(f"I will warn if I have less than __**{self.warnThreshold}**__ prompts that have not yet been show. Change with `{PREFIX}set_warn_threshold`.")
        
    @commands.command(name="set_warn_threshold", help="Sets the warning threshold. If I have less prompts than this threshold, I will include a warning with the prompt.")
    async def setWarnThreshold(self, ctx: commands.Context, newThreshold: int):
        self.warnThreshold = newThreshold
        settings["WarnThreshold"] = newThreshold
        saveSettings(settings)
        await ctx.send(f"My warn threshold is now {newThreshold}")
        
    @commands.command(name="set_send_repeat_prompts", help="Sets whether I will send repeat prompts once I run out. If you send true, then when I run out of prompts I will re-send prompts I have already sent. If false, I will send a warning instead.")
    async def setSendRepeatPrompts(self, ctx: commands.Context, sendRepeatPrompts: bool):
        self.sendRepeatPrompts = sendRepeatPrompts
        settings["SendRepeatPrompts"] = sendRepeatPrompts
        saveSettings(settings)
        if sendRepeatPrompts:
            message = "If I run out of prompts, I will send repeat prompts."
        else:
            message = "If I run out of prompts, I will stop sending prompts and send a warning instead."
        await ctx.send(message)
        
    @commands.command(name="get_send_repeat_prompts", help="Tells you if I will re-send prompts I have already sent once I run out of prompts.")
    async def getSendRepeatPrompts(self, ctx: commands.Context):
        await ctx.send(f"Send repeat prompts: {self.sendRepeatPrompts}")     
        
    @commands.command(name="set_time_to_send_prompt", help="Sets the time of day that I will send prompts. PLEASE PASS IT IN QUOTES, OR ALL AS ONE WORD (NO SPACE BETWEEN TIME AND TIMEZONE). Note that this will go into effect only after the next time I send a prompt, unless the bot is manually rebooted.")
    async def setTimeToSendPrompt(self, ctx: commands.Context, newTime: str):
        try:
            parseTzAware(newTime) # Just to ensure it's not a junk time
            self.timeToSendPrompt = newTime
            settings["TimeToSendPrompt"] = newTime
            saveSettings(settings)
            await ctx.send(f"I will now send prompts at {newTime}. Note that this will go into effect after the next time I send a prompt, and may (or may not) lead to two being sent in one day.")
        except:
            await ctx.send("Sorry, I didn't understand that time.")
        
    @commands.command(name="get_time_to_send_prompt", help="Tells you what time of day I am scheduled to send prompts.")
    async def getTimeToSendPrompt(self, ctx: commands.Context):
        await ctx.send(f"I am scheduled to send prompts at {self.timeToSendPrompt}")
        
    @commands.command(name="countdown", help="Tells you how long until the next time I will send a prompt.")
    async def countdown(self, ctx: commands.Context):
        await ctx.send(f"I will send the next prompt in: {timeToNextInstance(self.timeToSendPrompt)}. If you'd like one sooner, use `{PREFIX}send_prompt` to send one now.")
        
    @commands.command(name="pause", help="Tells me to skip sending a prompt for the number of days specified. I will instead send a message reminding that I am paused, and stating the number of pause days left. Note that this is a set, so any value provided will override previous values given.")
    async def pause(self, ctx: commands.Context, pauseDays: int):
        self.setPauseDays(pauseDays)
        if (pauseDays == 0):
            await ctx.send(f"I am unpaused and will send another prompt at {self.timeToSendPrompt}. If you would like me to send one earlier, use `{PREFIX}send_prompt`.")
        else:
            await ctx.send(f"I will not send a prompt for the next {pauseDays} days, unless instructed to with `{PREFIX}send_prompt`.")
        
    @commands.command(name="ping", help="Replies \"Pong\" so you know that I'm up.")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong")
        
    @commands.command(name="uptime", help="Replies with the amount of time since I came up.")
    async def uptime(self, ctx: commands.Context):
        await ctx.send(f"I have been up for {datetime.now() - startupTime}.")
        
    @commands.command(name="test", help="Prints information about the server I'm connected to.")
    async def test(self, ctx: commands.Context):
        guild = utils.get(bot.guilds, name=self.guild)
        response = f'{bot.user} is connected to the following guild:\n' + f'{guild.name}(id: {guild.id})'
        await ctx.send(response)
        
    @commands.command(name="make_backup", help="Backs up the current state of the bot on the server. This happens automatically any time a prompt is sent, so there generally shouldn't be a need to do it manually.")
    async def makeBackupCmd(self, ctx: commands.Context):
        self.makeBackup()
        await ctx.send("I just made a local backup of my state.")

bot.add_cog(Prompts(bot))

@bot.event
async def on_command_error(self, error):
    if isinstance(error, commands.errors.CheckFailure):
        pass
    else:
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

bot.run(TOKEN)