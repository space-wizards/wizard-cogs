import aiohttp
import dateutil.parser
import logging

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, TypeVar, Callable
from urllib.parse import urlparse, urlunparse

import discord
from discord import TextChannel
from discord.ext import tasks

from redbot.core import app_commands, commands, bot, Config, checks
from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta

log = logging.getLogger("red.wizard-cogs.gameserverstatus")

SS14_RUN_LEVEL_STATUS = {
    0: "In Lobby",
    1: "In game",
    2: "Ending",
}


class StatusFetchError(Exception):
    pass


class SS14ServerStatus(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        name: str,
        player_count: str,
        status: str,
        gamemap: str,
        preset: str,
        round_id: str,
        color: discord.Color,
    ):
        super().__init__()

        self.container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"**{name}**"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                content=f"**Players:** {player_count}\n**Status:** {status}\n**Map:** {gamemap}\n**Preset:** {preset}"
            ),
            accent_color=color,
        )
        self.footer_text = discord.ui.TextDisplay(content=f"-# Round ID: {round_id}")

        self.add_item(self.container)
        self.add_item(self.footer_text)


class GameServerStatus(commands.Cog):
    def __init__(self, bot: bot.Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5645456348)
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Py Aiohttp - Wizard-cogs/GameServerStatus (+https://github.com/space-wizards/wizard-cogs)"
            }
        )

        default_guild: Dict[str, Any] = {"servers": {}, "watches": []}
        self.config.register_guild(**default_guild)

        self.printer.start()

    async def cog_unload(self) -> None:
        await self.session.close()
        self.printer.cancel()

    @commands.command()
    @commands.guild_only()
    async def status(
        self,
        ctx: commands.Context,
        server: Optional[str],
        legacy: Optional[bool] = False,
    ) -> None:
        """Shows status for a game server.

        Leave out server name to get a list of all servers.
        Set `legacy` to `True` to display the status as an old Discord embed.
        """
        if not server:
            await self.show_server_list(ctx)
            return

        async with ctx.typing():
            server = server.lower()
            cfg = await self.config.guild(ctx.guild).servers()
            cfg_lower = {key.lower(): value for (key, value) in cfg.items()}

            if server not in cfg_lower:
                await ctx.send("That server does not exist!")
                return

            data = cfg_lower[server]
            try:
                fetched_data = await self.get_ss14_server_status(data)
            except StatusFetchError:
                return await ctx.send("An error has occured when fetching server info.")

            if legacy is True:
                return await ctx.send(
                    embed=legacy_embed(
                        **fetched_data, color=await self.bot.get_embed_color(ctx)
                    )
                )
            else:
                component_view = SS14ServerStatus(
                    **fetched_data,
                    color=await self.bot.get_embed_color(ctx),
                )
                return await ctx.send(view=component_view)

    @app_commands.command(name="status")
    @app_commands.guild_only()
    @app_commands.guild_install()
    @app_commands.rename(server_name="server")
    async def slash_status(
        self, interaction: discord.Interaction, server_name: str, legacy: bool = False
    ) -> None:
        """Shows status for a game server.

        Parameters
        -----------
        server: str
            The server to query.
        legacy: bool
            Legacy mode, for older Discord clients
        """
        server_name = server_name.lower()
        game_servers: dict = await self.config.guild(interaction.guild).servers()

        game_server_data = game_servers.get(server_name)
        if game_server_data is None:
            return await interaction.response.send_message(
                "That server does not exist!", ephemeral=True
            )

        # Defer here so we can wait for the HTTP status to return
        await interaction.response.defer(thinking=True)
        try:
            fetched_data = await self.get_ss14_server_status(game_server_data)
        except StatusFetchError:
            return await interaction.followup.send(
                "An error has occured when fetching server info."
            )

        if legacy is True:
            return await interaction.followup.send(
                embed=legacy_embed(
                    **fetched_data,
                    color=await self.bot.get_embed_color(interaction.channel),
                )
            )
        else:
            return await interaction.followup.send(
                view=SS14ServerStatus(
                    **fetched_data,
                    color=await self.bot.get_embed_color(interaction.channel),
                )
            )

    @slash_status.autocomplete("server_name")
    async def slash_status_server_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        server_names = list(
            (await self.config.guild(interaction.guild).servers()).keys()
        )  # JSON is practically memcached anyhow
        return [
            app_commands.Choice(name=server.capitalize(), value=server)
            for server in server_names
            if current.lower() in server.lower()
        ][:25]  # Discord's Choice limit is 25, ensure we don't exceed it

    async def show_server_list(self, ctx: commands.Context) -> None:
        servers = await self.config.guild(ctx.guild).servers()

        if len(servers) == 0:
            await ctx.send("No servers are currently configured!")
            return

        content = "\n".join(
            map(lambda s: f"{s[0]}: `{s[1]['address']}`", servers.items())
        )

        pages = list(pagify(content, page_length=1024))
        embed_pages = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title="Server List",
                description=page,
                colour=await ctx.embed_colour(),
            )
            embed.set_footer(
                text="Page {num}/{total}".format(num=idx, total=len(pages))
            )
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages, menus.DEFAULT_CONTROLS)

    async def get_ss14_server_status(self, config: Dict[str, str]) -> Dict[str, str]:
        """Fetches and returns the status endpoint from a SS14 server."""
        cfgurl = config["address"]
        longname = config.get("name")  # noqa: F841
        addr = get_ss14_status_url(cfgurl)
        log.debug("SS14 addr is {}".format(addr))

        try:
            log.debug("Starting to query")
            async with self.session.get(addr + "/status") as resp:
                log.debug("Got response.")
                json = await resp.json()
        except:
            raise StatusFetchError

        count = json.get("players", "?")
        count_max = json.get("soft_max_players", "?")
        name = json.get("name", "?")
        round_id = json.get("round_id", "?")
        gamemap = json.get("map", "?")
        preset = json.get("preset", "?")
        run_level = json.get("run_level")
        round_start_time = json.get("round_start_time")

        player_count = f"{count}/{count_max}"
        if run_level == 1 and round_start_time is not None:
            start_time = dateutil.parser.isoparse(round_start_time)
            delta = datetime.now(timezone.utc) - start_time
            status = f"{SS14_RUN_LEVEL_STATUS.get(run_level, 'unknown')} ({humanize_timedelta(timedelta=delta, maximum_units=2)})"
        else:
            status = SS14_RUN_LEVEL_STATUS.get(run_level, "Unknown")

        return {
            "name": name,
            "player_count": player_count,
            "status": status,
            "gamemap": gamemap,
            "preset": preset,
            "round_id": round_id,
        }

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def statuscfg(self, ctx: commands.Context) -> None:
        """
        Commands for configuring the status servers.
        """
        pass

    # -- Command group for adding & removing servers
    @statuscfg.group()
    async def addserver(self, ctx: commands.Context) -> None:
        """
        Adds a status server.
        """
        pass

    @addserver.command(name="ss14")
    async def addserver_ss14(
        self, ctx: commands.Context, name: str, address: str, longname: Optional[str]
    ) -> None:
        """
        Adds an SS14-type server.

        `<name>`: The short name to refer to this server.
        `<address>`: The `ss14://` or `ss14s://` address of this server.
        `[longname]`: The "full name" of this server.
        """
        name = name.lower()
        address = address.rstrip("/")

        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name in cur_servers:
                return await ctx.send("A server with that name already exists.")

            cur_servers[name] = {
                "type": "ss14",
                "address": address,
                "name": longname,
            }
        await ctx.tick()

    @statuscfg.command()
    async def removeserver(self, ctx: commands.Context, name: str) -> None:
        """
        Removes a status server.

        `<name>`: The name of the server to remove.
        """
        name = name.lower()
        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name not in cur_servers:
                await ctx.send("That server did not exist.")
                return

            del cur_servers[name]

        async with self.config.guild(ctx.guild).watches() as watches:
            for w in watches:
                if w["server"] != name:
                    continue

                watches.remove(w)
                await self.remove_watch_message(ctx.guild, w)

        await ctx.tick()

    @statuscfg.command()
    async def addwatch(
        self, ctx: commands.Context, name: str, channel: TextChannel
    ) -> None:
        """
        Adds a server to the watch list. The bot will update a message with the server status every minute.

        `<name>`: The name of the server to watch.
        `<channel>`: The channel to send the message to.
        """
        name = name.lower()
        async with self.config.guild(ctx.guild).watches() as watches:
            servers = await self.config.guild(ctx.guild).servers()

            if name not in servers:
                await ctx.send("That server does not exist!")
                return

            data = servers[name]

            fetched_data = await self.get_ss14_server_status(data)
            component_view = SS14ServerStatus(
                **fetched_data, color=self.bot.get_embed_color(ctx.channel)
            )

            msg = await channel.send(view=component_view)
            watches.append({"message": msg.id, "server": name, "channel": channel.id})

            return await ctx.send("The server watch is successfully added.")

    @statuscfg.command()
    async def remwatch(
        self, ctx: commands.Context, name: str, channel: TextChannel
    ) -> None:
        """
        Removes a server to the watch list.

        `<name>`: The name of the server to remove from a watch.
        `<channel>`: The channel to remove from.
        """
        name = name.lower()
        async with self.config.guild(ctx.guild).watches() as watches:
            for w in watches:
                if w["server"] != name or w["channel"] != channel.id:
                    continue

                watches.remove(w)
                await self.remove_watch_message(ctx.guild, w)

        await ctx.tick()

    async def remove_watch_message(
        self, guild: discord.Guild, watch_data: Dict[str, Any]
    ) -> None:
        channel = guild.get_channel(watch_data["channel"])
        try:
            message = await channel.fetch_message(watch_data["message"])
            await message.delete()
        except Exception as e:
            log.exception(e)
            pass

    @statuscfg.command()
    async def watches(self, ctx: commands.Context) -> None:
        """
        Lists currently active watches
        """
        watches = await self.config.guild(ctx.guild).watches()

        if len(watches) == 0:
            await ctx.send("No watches are currently configured!")
            return

        content = "\n".join(
            map(
                lambda w: f"<#{w['channel']}> - {w['server']} - [message](https://discord.com/channels/{ctx.guild.id}/{w['channel']}/{w['message']})",
                watches,
            )
        )

        pages = list(pagify(content, page_length=1024))
        embed_pages = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title="Watch List",
                description=page,
                colour=await ctx.embed_colour(),
            )
            embed.set_footer(
                text="Page {num}/{total}".format(num=idx, total=len(pages))
            )
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages, menus.DEFAULT_CONTROLS)

    @tasks.loop(minutes=3)
    async def printer(self) -> None:
        log.debug("Starting watcher loop.")
        try:
            for guild_id, data in (await self.config.all_guilds()).items():
                for watch in data["watches"]:
                    msg_id = watch["message"]
                    ch_id = watch["channel"]
                    server = watch["server"]

                    try:
                        channel = self.bot.get_channel(ch_id)
                        msg = await channel.fetch_message(msg_id)
                    except discord.NotFound:
                        # Message gone now, clear config I guess.
                        async with self.config.guild_from_id(
                            guild_id
                        ).watches() as w_config:
                            remove_list_elems(
                                w_config, lambda x: x["message"] == msg_id
                            )
                        continue

                    try:
                        fetched_data = await self.get_ss14_server_status(
                            data["servers"][server]
                        )
                    except StatusFetchError:
                        continue  # End the function early just because we can't fetch the status
                    view = SS14ServerStatus(
                        **fetched_data, color=await self.bot.get_embed_color(msg)
                    )
                    await msg.edit(
                        content="", view=view
                    )  # Ensure backwards compatability with old watches
        except discord.errors.HTTPException as e:
            log.exception(
                "Error happened while trying to execute gameserverstatus loop.",
                exc_info=e,
            )
        except Exception as e:
            log.exception(
                "An unexpected error occurred in the printer loop.", exc_info=e
            )

    @printer.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


def get_ss14_status_url(url: str) -> str:
    if "//" not in url:
        url = "//" + url

    parsed = urlparse(url, "ss14", allow_fragments=False)

    port = parsed.port
    if not port:
        if parsed.scheme == "ss14s":
            port = 443
        else:
            port = 1212

    if parsed.scheme == "ss14s":
        scheme = "https"
    else:
        scheme = "http"

    return urlunparse(
        (
            scheme,
            f"{parsed.hostname}:{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def legacy_embed(
    *,
    name: str,
    player_count: str,
    status: str,
    gamemap: str,
    preset: str,
    round_id: str,
    color: discord.Color,
) -> discord.Embed:
    embed = discord.Embed(color=color, title=name)
    embed.add_field(name="Players Online", value=player_count)
    embed.add_field(name="Status", value=status)
    embed.add_field(name="Round ID", value=round_id)
    embed.add_field(name="Map", value=gamemap)
    embed.add_field(name="Preset", value=preset)
    return embed


T = TypeVar("T")


# .NET List<T>.RemoveAll(Predicate<T>)
# O(n^2) worst case (.NET's is O(n))
def remove_list_elems(itter_list: List[T], pred: Callable[[T], bool]) -> None:
    for i in list(filter(pred, itter_list)):
        itter_list.remove(i)
