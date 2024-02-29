import random
from redbot.core import commands
import re
from typing import Match
import discord
from discord import Message


class responder(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        channel = message.channel

        author = message.author
        valid_user = isinstance(author, discord.Member) and not author.bot
        if not valid_user:
            return

        if await self.bot.is_automod_immune(message):
            return


        # Tetris
        match = re.search(r".*tetris.*", message.content, re.IGNORECASE)
        if match:
            await channel.send("*Nanotrasen Block Game:tm:")

        # WYCI
        match = re.search(r"\S\s+(?:when|whence)[\s*?.!)]*$", message.content, re.IGNORECASE)
        if match:
            if random.random() > 0.005:
                await channel.send("When You Code It.")
            else:
                await channel.send("Never.")

        # Based

        match = re.search(r"^\s*(based|gebaseerd|basé|basato|basado|basiert|βασισμένο|βασισμενο|ベース)[\s*?.!)]*$", message.content,
                          re.IGNORECASE)

        if match:
            if match.group(1).lower() == "based":
                based = "Based on what?"
                unbased = "Not Based."

            if match.group(1).lower() == "gebaseerd":
                based = "Gebaseerd op wat?"
                unbased = "Niet Gebaseerd."

            elif match.group(1).lower() == "basiert":
                based = "Worauf?"
                unbased = "Nicht basiert."

            elif match.group(1).lower() == "basé":
                based = "Sur quoi?"
                unbased = "Pas basé."

            elif match.group(1).lower() == "basado":
                based = "¿Basado en qué?"
                unbased = "No basado."

            elif match.group(1).lower() == "basato":
                based = "Basato su cosa?"
                unbased = "Non basato."

            elif match.group(1) == u"ベース":
                based = u"何に基づいてですか"
                unbased = u"ベースではない"

            elif match.group(1).lower() == "bunaithe":
                based = "Cad é ina bunaithe?"
                unbased = "Ní bunaithe."

            elif match.group(1).lower() in ["βασισμένο", "βασισμενο"]:
                based = "Βασισμένο σε τι;"
                unbased = "Αβάσιμο."

            if random.random() > 0.005:
                await channel.send(based)
            else:
                await channel.send(unbased)
