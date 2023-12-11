from .poweractions import poweractions


async def setup(bot):
    await bot.add_cog(poweractions(bot))
