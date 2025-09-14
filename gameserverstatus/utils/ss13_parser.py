"""
Unused parrts of the SS13 server status parser. Its very unlikely to be used and is here for archival purposes.
In case someone ever wants to build it into its own thing again (Why? Just use Crossedfall's Cog)
"""


from typing import Tuple, Union, Dict, List, Optional, cast
import struct
import asyncio
from urllib.parse import urlparse, parse_qs
from discord.abc import Messageable
from discord import Embed


async def do_status_ss13(
    self, ctx: Messageable, name: str, dat: Dict[str, str], embed: Embed
) -> None:
    cfgurl = dat["address"]
    longname = dat.get("name")
    (addr, port) = get_ss13_status_addr(cfgurl)
    response = await byond_server_topic(addr, port, b"?status")

    embed.title = longname
    embed.set_footer(text=f"{name}: {cfgurl}")

    mapname: Optional[str]
    players: str
    admins: Optional[int] = None  # noqa: F841
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


async def byond_server_topic(
    address: str, port: int, message: bytes
) -> Union[float, Dict[str, List[str]]]:
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
    if packet[0] == 0x2A:
        return cast(float, struct.unpack(">f", packet[1:5])[0])

    elif packet[0] == 0x06:
        return packet[1:-1].decode("ascii")

    raise NotImplementedError(f"Unknown BYOND data code: 0x{packet[0]:x}")
