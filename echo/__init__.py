from redbot.core.bot import Red
from .echo import Echo


def setup(bot: Red) -> None:
    bot.add_cog(Echo(bot))