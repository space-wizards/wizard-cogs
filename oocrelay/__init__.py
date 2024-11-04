from .oocrelay import OocRelay

async def setup(bot):
    await bot.add_cog(OocRelay(bot))