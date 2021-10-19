from redbot.core.bot import Red
from .gameserverstatus import GameServerStatus


def setup(bot: Red) -> None:
    bot.add_cog(GameServerStatus(bot))