from .responder import responder


async def setup(bot) -> None:
    await bot.add_cog(responder(bot))
