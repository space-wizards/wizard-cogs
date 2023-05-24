from redbot.core.bot import Red
from .echo import Echo


async def setup(bot: Red) -> None:
    await bot.add_cog(Echo(bot))