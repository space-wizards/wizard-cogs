import asyncio
import base64
import json

import aiohttp
from discord import Embed
from redbot.core import commands, checks, Config
import logging
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils import menus
import discord
from redbot.core.utils.views import ConfirmView

log = logging.getLogger("red.wizard-cogs.gameserverstatus")


# Input class for the discord modal
class Input(discord.ui.Modal, title='Input server details'):
    name = discord.ui.TextInput(label='Name', placeholder='Server name (You can choose this yourself)', required=True)
    url = discord.ui.TextInput(label='URL',
                               placeholder='Watchdog server URL (https://ss14.io/watchdog http://localhost:1212)',
                               required=True)
    key = discord.ui.TextInput(label='Server ID',
                               placeholder='Server ID (ID of the the server)',
                               required=True)
    token = discord.ui.TextInput(label='API Token',
                                 placeholder='Server token (Value of ApiToken)',
                                 required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Processing...", ephemeral=True)
        self.stop()


# Button to bring up the modal
class Button(discord.ui.View):
    def __init__(self, member):
        self.member = member
        super().__init__()
        self.modal = None

    @discord.ui.button(label='Add', style=discord.ButtonStyle.green)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.member != interaction.user:
            return await interaction.response.send_message("You cannot use this.", ephemeral=True)

        self.modal = Input()
        await interaction.response.send_modal(self.modal)
        await self.modal.wait()
        self.stop()


class poweractions(commands.Cog):
    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=275978)

        default_guild = {
            "servers": {},
        }

        self.config.register_guild(**default_guild)

        self.bot = bot

    @commands.group()
    @checks.admin()
    async def poweractionscfg(self, ctx: commands.Context) -> None:
        """
        Commands for configuring the servers to be able to manage the actions for power actions.
        """
        pass

    @poweractionscfg.command()
    async def add(self, ctx: commands.Context) -> None:
        """
        Adds a server.
        """
        view = Button(member=ctx.author)

        await ctx.send("To add a server press this button.", view=view)
        await view.wait()
        if view.modal is None:
            return
        if not view.modal.name.value:
            return

        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if view.modal.name.value in cur_servers:
                await ctx.send("A server with that name already exists.")
                return

            if not view.modal.url.value.startswith("http://") and not view.modal.url.value.startswith("https://"):
                await ctx.send("The URL must start with http:// or https://")
                return

            # Remove trailing slash at the end of the URL
            if view.modal.url.value.endswith("/"):
                await ctx.send("Remove the trailing slash at the end of the URL.")

            if view.modal.url.value.endswith(f"/instances/{view.modal.key.value}/restart"):
                await ctx.send("No need for the last part of the URL, just the base URL to the watchdog (Example: "
                               "https://ss14.io/watchdog, http://localhost:1212)")
                return

            cur_servers[view.modal.name.value] = {
                "address": view.modal.url.value,
                "key": view.modal.key.value,
                "token": view.modal.token.value
            }

        await ctx.send("Server added successfully.")

    @poweractionscfg.command()
    async def remove(self, ctx: commands.Context, name: str) -> None:
        """
        Removes a server.

        `<name>`: The name of the server to remove.
        """
        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name not in cur_servers:
                await ctx.send("That server did not exist.")
                return

            del cur_servers[name]

        await ctx.tick()

    @poweractionscfg.command()
    async def list(self, ctx: commands.Context) -> None:
        """
        Get a list of servers.
        """
        servers = await self.config.guild(ctx.guild).servers()

        if len(servers) == 0:
            await ctx.send("No servers are currently configured!")
            return

        content = "\n".join(map(lambda s: f"{s[0]}: `{s[1]['address']}`", servers.items()))

        pages = list(pagify(content, page_length=1024))
        embed_pages = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title="Server List",
                description=page,
                colour=await ctx.embed_colour(),
            )
            embed.set_footer(text="Page {num}/{total}".format(num=idx, total=len(pages)))
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages, menus.DEFAULT_CONTROLS)

    @checks.admin()
    @commands.command()
    async def restartserver(self, ctx: commands.Context, server) -> None:
        """
        Restarts a server.
        """
        async with ctx.typing():
            selectedserver = await self.config.guild(ctx.guild).servers()

            if server not in selectedserver:
                await ctx.send("That server does not exist.")
                return
            else:
                server = selectedserver[server]

            authheader = "Basic " + base64.b64encode(f"{server['key']}:{server['token']}".encode("ASCII")).decode(
                "ASCII")

            try:
                async with aiohttp.ClientSession() as session:
                    async def load():
                        async with session.post(server["address"] + f"/instances/{server['key']}/restart",
                                                headers={"Authorization": authheader}) as resp:
                            if resp.status != 200:
                                await ctx.send(f"Failed to restart the server. Wrong status code: {resp.status}")
                                return

                    await asyncio.wait_for(load(), timeout=5)

            except asyncio.TimeoutError:
                await ctx.send("Server timed out.")
                return

            except Exception as e:
                await ctx.send(f"Server failed to restart. Error: {e}")

            await ctx.send("Server restarted successfully.")

    @checks.admin()
    @commands.command()
    async def restartnetwork(self, ctx: commands.Context) -> None:
        """
        Attemps to restarts all servers on the bot.
        """
        view = ConfirmView(ctx.author, disable_buttons=True, timeout=30)
        view.message = await ctx.send(":warning: You are about to restart all servers configured on this bot "
                                      "instance, are you certain this is what you want to do", view=view)
        await view.wait()
        if view.result:
            await ctx.send("Restarting all servers...")
            async with ctx.typing():
                network_data = await self.config.guild(ctx.guild).servers()

                embed = Embed(title="Network Restart", description="Results of the restarts", color=await ctx.embed_colour())

                for server_name, server_details  in network_data.items():
                    authheader = "Basic " + base64.b64encode(f"{server_details['key']}:{server_details['token']}".encode("ASCII")).decode(
                        "ASCII")

                    try:
                        async with aiohttp.ClientSession() as session:
                            async def load():
                                async with session.post(server_details["address"] + f"/instances/{server_details['key']}/restart",
                                                        headers={"Authorization": authheader}) as resp:
                                    if resp.status != 200:
                                        embed.add_field(name=server_name, value=f":x: Wrong status code: {resp.status}", inline=False)
                                    else:
                                        embed.add_field(name=server_name, value=":white_check_mark:  Success", inline=False)

                            await asyncio.wait_for(load(), timeout=5)

                    except asyncio.TimeoutError:
                        embed.add_field(name=server_name, value=":x: Timed out", inline=False)

                    except Exception as e:
                        embed.add_field(name=server_name, value=f":x: Failed to restart. Error: {e}", inline=False)

                await ctx.send("Done", embed=embed)
        else:
            await ctx.send("Canceled. No action taken.")
