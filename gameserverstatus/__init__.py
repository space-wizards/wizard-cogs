from redbot.core.bot import Red
from .gameserverstatus import GameServerStatus


async def setup(bot: Red) -> None:
    await bot.add_cog(GameServerStatus(bot))