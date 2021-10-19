import discord
from discord.channel import TextChannel
from discord.message import Message
from redbot.core import commands, bot, Config, checks

class Echo(commands.Cog):
    def __init__(self, bot: bot.Red) -> None:
        self.bot = bot

    @commands.group()
    @checks.admin()
    async def adminmsg(self, ctx: commands.Context) -> None:
        """
        Commands for managing and creating admin messages.
        """
        pass

    @adminmsg.command()
    async def create(self, ctx: commands.Context, chan: TextChannel) -> None:
        """
        Create an admin message in the specified channel.
        The contents of the message are everything except the first line of the message invoking the command, and are copied verbatim.
        """
        msg = "\n".join(ctx.message.content.split("\n")[1:])
        if not msg:
            await ctx.reply("Message is empty! Put it on a new line!")
            return

        try:
            await chan.send(msg)
        except discord.Forbidden:
            await ctx.reply("I do not have permission to send there!")
            return

        await ctx.tick()

    @adminmsg.command()
    async def edit(self, ctx: commands.Context, editMessage: Message) -> None:
        """
        Edits the contents of a message sent by the bot.
        The contents of the message are everything except the first line of the message invoking the command, and are copied verbatim.
        """
        msg = "\n".join(ctx.message.content.split("\n")[1:])
        if not msg:
            await ctx.reply("Message is empty! Put it on a new line!")
            return

        if editMessage.author != self.bot.user:
            await ctx.reply("I didn't send that message!")
            return

        await editMessage.edit(content=msg)
        await ctx.tick()