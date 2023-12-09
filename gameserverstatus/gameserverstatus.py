import asyncio
import logging
import aiohttp
import dateutil.parser
import struct
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, ParseResult, parse_qs
from typing import Dict, Any, Optional, Tuple, cast, Union, List, TypeVar, Callable
import discord
from discord import Embed, Color, TextChannel, Message
from discord.abc import Messageable
from discord.ext import tasks
from redbot.core import commands, bot, Config, checks
from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import pagify

log = logging.getLogger("red.wizard-cogs.gameserverstatus")

TYPE_SS14 = "ss14"
TYPE_SS13 = "ss13"

SS14_RUN_LEVEL_PREGAME = 0
SS14_RUN_LEVEL_GAME = 1
SS14_RUN_LEVEL_POSTGAME = 2

QSTAT_TYPES = {
    "a2s": "Half-Life 2 new server",
    "alienarenas": "Alien Arena server",
    "ams": "America's Army v2.x server",
    "bfbc2": "Battlefield Bad Company 2 server",
    "bfs": "BFRIS server",
    "cod2s": "Call of Duty 2 server",
    "cod4s": "Call of Duty 4 server",
    "cods": "Call of Duty server",
    "crs": "Command and Conquer: Renegade server",
    "crysis": "Crysis server",
    "cubes": "Sauerbraten server",
    "d3g": "Descent3 Gamespy Protocol server",
    "d3p": "Descent3 PXO protocol server",
    "d3s": "Descent3 server",
    "dirtybomb": "DirtyBomb server",
    "dm3s": "Doom 3 server",
    "efm": "Star Trek: Elite Force server",
    "efs": "Star Trek: Elite Force server",
    "etqws": "QuakeWars server",
    "eye": "All Seeing Eye Protocol server",
    "farmsim": "FarmingSimulator server",
    "fcs": "FarCry server",
    "fls": "Frontlines-Fuel of War server",
    "gps": "Gamespy Protocol server",
    "grs": "Ghost Recon server",
    "gs2": "Gamespy V2 Protocol server",
    "gs3": "Gamespy V3 Protocol server",
    "gs4": "Gamespy V4 Protocol server",
    "h2s": "Hexen II server",
    "hazes": "Haze Protocol server",
    "hl2s": "Half-Life 2 server",
    "hla2s": "Half-Life server",
    "hlqs": "Half-Life server",
    "hls": "Half-Life server",
    "hrs": "Heretic II server",
    "hws": "HexenWorld server",
    "iourts": "Urban Terror server",
    "jk2m": "Jedi Knight 2 server",
    "jk2s": "Jedi Knight 2 server",
    "jk3m": "Jedi Knight: Jedi Academy server",
    "jk3s": "Jedi Knight: Jedi Academy server",
    "kps": "Kingpin server",
    "ksp": "Kerbal Space Program server",
    "maqs": "Medal of Honor: Allied Assault (Q) server",
    "mas": "Medal of Honor: Allied Assault server",
    "mhs": "Medal of Honor: Allied Assault server",
    "mumble": "Mumble server",
    "netp": "NetPanzer server",
    "nexuizs": "Nexuiz server",
    "openarenas": "OpenArena server",
    "ottds": "OpenTTD server",
    "preys": "PREY server",
    "prs": "Pariah server",
    "q2s": "Quake II server",
    "q3rallys": "Q3 Rally server",
    "q3s": "Quake III: Arena server",
    "q4s": "Quake 4 server",
    "qs": "Quake server",
    "quetoos": "Quetoo server",
    "qws": "QuakeWorld server",
    "reactions": "Reaction server",
    "rss": "Ravenshield server",
    "rws": "Return to Castle Wolfenstein server",
    "sas": "Savage server",
    "sfs": "Soldier of Fortune server",
    "sgs": "Shogo: Mobile Armor Division server",
    "smokingunss": "Smokin' Guns server",
    "sms": "Serious Sam server",
    "sns": "Sin server",
    "sof2s": "Soldier of Fortune 2 server",
    "starmade": "StarMade server",
    "t2s": "Tribes 2 server",
    "tbs": "Tribes server",
    "tees": "Teeworlds server",
    "terraria": "Terraria server",
    "tf": "Titanfall server",
    "tf2": "Titanfall 2 server",
    "tf2e": "Titanfall 2 Protocol v2 server",
    "tm": "TrackMania server",
    "tremulousgpps": "Tremulous GPP server",
    "tremulouss": "Tremulous server",
    "ts2": "Teamspeak 2 server",
    "ts3": "Teamspeak 3 server",
    "turtlearenas": "Turtle Arena server",
    "uns": "Unreal server",
    "unvanquisheds": "Unvanquished server",
    "ut2004s": "UT2004 server",
    "ut2s": "Unreal Tournament 2003 server",
    "ut3s": "UT3 server",
    "vent": "Ventrilo server",
    "warsows": "Warsow server",
    "waws": "Call of Duty World at War server",
    "wics": "World in Conflict server",
    "woets": "Enemy Territory server",
    "wolfs": "Wolfenstein server",
    "wops": "World Of Padman server",
    "xonotics": "Xonotic server",
    "zeq2lites": "ZEQ2 Lite server"
}


class GameServerStatus(commands.Cog):
    def __init__(self, bot: bot.Red) -> None:
        self.config = Config.get_conf(self, identifier=5645456348)

        default_guild: Dict[str, Any] = {
            "servers": {},
            "watches": []
        }

        self.config.register_guild(**default_guild)

        self.printer.start()
        self.bot = bot

    def cog_unload(self) -> None:
        self.printer.cancel()

    @commands.group()
    @checks.admin()
    async def statuscfg(self, ctx: commands.Context) -> None:
        """
        Commands for configuring the status servers.
        """
        pass

    @commands.command()
    async def status(self, ctx: commands.Context, server: Optional[str]) -> None:
        """
        Shows status for a game server. Leave out server name to get a list of all servers.
        """
        if not server:
            await self.show_server_list(ctx);
            return

        async with ctx.typing():
            cfg = await self.config.guild(ctx.guild).servers()

            if server not in cfg:
                await ctx.send("That server does not exist!")
                return

            dat = cfg[server]

            embed = await self.create_embed(ctx, server, dat)

            await ctx.send(embed=embed)

    async def show_server_list(self, ctx: commands.Context) -> None:
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

    async def create_embed(self, ctx: Messageable, cfgname: str, dat: Dict[str, str]) -> Embed:
        embed = Embed()
        embed.color = Color.red()

        async def do_load() -> None:
            if dat["type"] == TYPE_SS14:
                await self.do_status_ss14(ctx, cast(str, cfgname), dat, embed)

            elif dat["type"] == TYPE_SS13:
                await self.do_status_ss13(ctx, cast(str, cfgname), dat, embed)

        try:
            await asyncio.wait_for(do_load(), timeout=5)

        except StatusException as e:
            embed.description = f"**{e.message}**"

        except asyncio.TimeoutError:
            embed.description = "**Server timed out**"

        except:
            embed.description = "**Unknown error occured**"
            log.exception("exception in status handler")

        else:
            embed.color = await self.bot.get_embed_color(ctx)

        return embed

    async def do_status_ss14(self, ctx: Messageable, cfgname: str, dat: Dict[str, str], embed: Embed) -> None:
        cfgurl = dat["address"]
        longname = dat.get("name")
        addr = get_ss14_status_url(cfgurl)
        log.debug(f"SS14 addr is {addr}")

        embed.set_footer(text=f"{cfgname}: {cfgurl}")
        embed.title = longname

        async with aiohttp.ClientSession() as session:
            async with session.get(addr + "/status") as resp:
                json = await resp.json()

            count = json["players"]
            countmax = json["soft_max_players"]
            name = json["name"]
            round_id = json["round_id"]
            gamemap = json["map"]

            if name:
                embed.title = name

            embed.add_field(name="Players Online", value=f"{count}/{countmax}")

            rlevel = json.get("run_level")
            if rlevel is not None:
                status = "Unknown"

                if rlevel == SS14_RUN_LEVEL_PREGAME:
                    status = "Pre game lobby"
                elif rlevel == SS14_RUN_LEVEL_GAME:
                    status = "In game"
                elif rlevel == SS14_RUN_LEVEL_POSTGAME:
                    status = "Post game"

                embed.add_field(name="Status", value=status)

            starttimestr = json.get("round_start_time")
            if starttimestr:
                starttime = dateutil.parser.isoparse(starttimestr)
                delta = datetime.now(timezone.utc) - starttime
                s = []
                if delta.days > 0:
                    s.append(f"{delta.days} days")

                minutes = delta.seconds // 60
                hours = minutes // 60
                if hours > 0:
                    s.append(f"{hours} hours")
                    minutes %= 60

                s.append(f"{minutes} minutes")

                embed.add_field(name="Round length", value=", ".join(s))

                embed.add_field(name="Round ID", value=round_id)

                embed.add_field(name="Map", value=gamemap)

                # Cause for some reason discord can't center divs we do it for themfi
                embed.add_field(name="", value="")

    async def do_status_ss13(self, ctx: Messageable, name: str, dat: Dict[str, str], embed: Embed) -> None:
        cfgurl = dat["address"]
        longname = dat.get("name")
        (addr, port) = get_ss13_status_addr(cfgurl)
        response = await byond_server_topic(addr, port, b"?status")

        embed.title = longname
        embed.set_footer(text=f"{name}: {cfgurl}")

        mapname: Optional[str]
        players: str
        admins: Optional[int] = None
        station_time: Optional[str]

        try:
            if not isinstance(response, Dict):
                raise NotImplementedError("Non-list returns are not accepted.")

            mapname = None
            if "map_name" in response:
                mapname = response["map_name"][0]
            station_time = None
            if "station_time" in response:
                station_time = response["station_time"][0]
            players = response["players"][0]

        except:
            log.exception("Got unsupported response")
            raise StatusException("Server sent unsupported response.")

        embed.add_field(name="Players Online", value=players)
        if mapname:
            embed.add_field(name="Map", value=mapname)

        if station_time:
            embed.add_field(name="Station Time", value=station_time)

    @statuscfg.group()
    async def addserver(self, ctx: commands.Context) -> None:
        """
        Adds a status server.
        """
        pass

    @statuscfg.command()
    async def removeserver(self, ctx: commands.Context, name: str) -> None:
        """
        Removes a status server.

        `<name>`: The name of the server to remove.
        """
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

    @addserver.command(name="ss14")
    async def addserver_ss14(self, ctx: commands.Context, name: str, address: str, longname: Optional[str]) -> None:
        """
        Adds an SS14-type server.

        `<name>`: The short name to refer to this server.
        `<address>`: The `ss14://` or `ss14s://` address of this server.
        `[longname]`: The "full name" of this server.
        """
        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name in cur_servers:
                await ctx.send("A server with that name already exists.")
                return

            cur_servers[name] = {
                "type": TYPE_SS14,
                "address": address,
                "name": longname
            }

        await ctx.tick()

    @addserver.command(name="ss13")
    async def addserver_ss13(self, ctx: commands.Context, name: str, address: str, longname: Optional[str]) -> None:
        """
        Adds an SS13-type server.

        `<name>`: The short name to refer to this server.
        `<address>`: The `byond://` address of this server.
        `[longname]`: The "full name" of this server.
        """
        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name in cur_servers:
                await ctx.send("A server with that name already exists.")
                return

            cur_servers[name] = {
                "type": TYPE_SS13,
                "address": address,
                "name": name
            }

        await ctx.tick()

    @addserver.command(name="qstat")
    async def addserver_qstat(self, ctx: commands.Context, name: str, address: str, longname: Optional[str]) -> None:
        """


        `<name>`: The short name to refer to this server.
        `<type>`: Server type.
        `<address>`: The `byond://` address of this server.
        `[longname]`: The "full name" of this server.
        """
        async with self.config.guild(ctx.guild).servers() as cur_servers:
            if name in cur_servers:
                await ctx.send("A server with that name already exists.")
                return

            cur_servers[name] = {
                "type": TYPE_SS13,
                "address": address,
                "name": name
            }

        await ctx.tick()

    @statuscfg.command()
    async def addwatch(self, ctx: commands.Context, name: str, channel: TextChannel) -> None:
        async with self.config.guild(ctx.guild).watches() as watches:
            servers = await self.config.guild(ctx.guild).servers()

            if name not in servers:
                await ctx.send("That server does not exist!")
                return

            embed = await self.create_embed(ctx, name, servers[name])
            msg: Message = await channel.send(embed=embed)

            watches.append({
                "message": msg.id,
                "server": name,
                "channel": channel.id
            })

    @statuscfg.command()
    async def remwatch(self, ctx: commands.Context, name: str, channel: TextChannel) -> None:
        async with self.config.guild(ctx.guild).watches() as watches:
            for w in watches:
                if w["server"] != name or w["channel"] != channel.id:
                    continue

                watches.remove(w)
                await self.remove_watch_message(ctx.guild, w)

        await ctx.tick()

    async def remove_watch_message(self, guild: discord.Guild, watch_data: Dict[str, Any]) -> None:
        channel: discord.TextChannel = guild.get_channel(watch_data["channel"])
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

        content = "\n".join(map(lambda
                                    w: f"<#{w['channel']}> - {w['server']} - [message](https://discord.com/channels/{ctx.guild.id}/{w['channel']}/{w['message']})",
                                watches))

        pages = list(pagify(content, page_length=1024))
        embed_pages = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title="Watch List",
                description=page,
                colour=await ctx.embed_colour(),
            )
            embed.set_footer(text="Page {num}/{total}".format(num=idx, total=len(pages)))
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages, menus.DEFAULT_CONTROLS)

    @tasks.loop(minutes=1)
    async def printer(self) -> None:
        try:
            for (g_id, dat) in (await self.config.all_guilds()).items():
                for watch in dat["watches"]:
                    msg_id = watch["message"]
                    ch_id = watch["channel"]
                    server = watch["server"]

                    try:
                        channel: TextChannel = self.bot.get_channel(ch_id)
                        msg: Message = await channel.fetch_message(msg_id)
                    except discord.NotFound:
                        # Message gone now, clear config I guess.
                        async with self.config.guild_from_id(g_id).watches() as w_config:
                            remove_list_elems(w_config, lambda x: x["message"] == msg_id)

                        continue

                    embed = await self.create_embed(channel, server, dat["servers"][server])

                    await msg.edit(embed=embed)

                    # Sleep between edits in an attempt to not get rate-limited.
                    await asyncio.sleep(2)

                    # Set back to default interval.
                    self.printer.change_interval(minutes=1)
        except discord.errors.HTTPException as ex:
            log.exception("Error happened while trying to execute gameserverstatus loop.")

            # Too Many Requests, wait double the time now.
            if (ex.code == 429):
                self.printer.change_interval(minutes=min(self.printer.minutes * 2, 10))

        except Exception:
            log.exception("Error happened while trying to execute gameserverstatus loop.")

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

    return urlunparse((scheme, f"{parsed.hostname}:{port}", parsed.path, parsed.params, parsed.query, parsed.fragment))


def get_ss13_status_addr(url: str) -> Tuple[str, int]:
    if "//" not in url:
        url = "//" + url

    parsed = urlparse(url, "byond", allow_fragments=False)

    port = parsed.port
    if not port:
        raise ValueError("No port specified!")

    return (cast(str, parsed.hostname), cast(int, parsed.port))


""" 
async def get_status_ss13(address: str, port: int, channel: MChannel, admindata: Optional[List[MIdentifier]]) -> None:
    response = await asyncio.wait_for(byond_server_topic(address, port, b"?status"), timeout=5)

    mapname: Optional[str]
    players: str
    admins: Optional[int] = None

    try:
        if not isinstance(response, Dict):
            raise NotImplementedError("Non-list returns are not accepted.")

        mapname = None
        if "map_name" in response:
            mapname = response["map_name"][0]
        station_time = None
        if "station_time" in response:
            station_time = response["station_time"][0]
        players = response["players"][0]
        if admindata and "admins" in response:
            for identifier in admindata:
                if channel.is_identifier(identifier):
                    admins = int(response["admins"][0])
                    break

    except:
        await channel.send("Server sent unsupported response.")
        log.exception("Got unsupported response")
        return

    out = f"{players} players online"

    if mapname:
        out += f", map is {mapname}"

    if station_time:
        out += f", station time: {station_time}"

    if admins is not None:
        out += f", **{admins}** admins online. *Note: unable to provide AFK statistics for administrators.*"

    else:
        out += "."

    await channel.send(out)
 """


async def byond_server_topic(address: str, port: int, message: bytes) -> Union[float, Dict[str, List[str]]]:
    if message[0] != 63:
        message = b"?" + message

    # Send a packet to trick BYOND into doing a world.Topic() call.
    # https://github.com/N3X15/ss13-watchdog/blob/master/Watchdog.py#L582
    packet = b"\x00\x83"
    packet += struct.pack(">H", len(message) + 6)
    packet += b"\x00" * 5
    packet += message
    packet += b"\x00"

    reader, writer = await asyncio.open_connection(address, port)
    writer.write(packet)

    await writer.drain()

    if await reader.read(2) != b"\x00\x83":
        raise IOError("BYOND server returned data invalid.")

    # Read response
    size = struct.unpack(">H", await reader.read(2))[0]
    response = await reader.read(size)
    # logger.info(response)
    writer.close()

    ret = byond_decode_packet(response)
    if isinstance(ret, str):
        return parse_qs(ret)

    return ret


# Turns the BYOND packet into either a string or a float.
def byond_decode_packet(packet: bytes) -> Union[float, str]:
    if packet[0] == 0x2a:
        return cast(float, struct.unpack(">f", packet[1:5])[0])

    elif packet[0] == 0x06:
        return packet[1:-1].decode("ascii")

    raise NotImplementedError(f"Unknown BYOND data code: 0x{packet[0]:x}")


class StatusException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

        self.message = message


T = TypeVar("T")


# .NET List<T>.RemoveAll(Predicate<T>)
# O(n^2) worst case (.NET's is O(n))
def remove_list_elems(l: List[T], pred: Callable[[T], bool]) -> None:
    for i in list(filter(pred, l)):
        l.remove(i)
