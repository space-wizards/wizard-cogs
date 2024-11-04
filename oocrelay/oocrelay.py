from redbot.core import commands, Config
from aiohttp import web, ClientSession
import asyncio
import logging
import discord

log = logging.getLogger("red.simyon264.oocrelay")


class Button(discord.ui.View):
    """Brings up the "add relay" button."""

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

class Input(discord.ui.Modal, title='Input server details'):
    """The actual modal that pops up when the button is clicked."""

    name = discord.ui.TextInput(label='Path', 
                                placeholder='my_awesome_server', 
                                required=True)
    password = discord.ui.TextInput(label='Password',
                               placeholder='Server password (Needs to match status.mommipassword)',
                               required=True)
    
    channel = discord.ui.TextInput(label='Channel ID',
                                 placeholder='Channel ID to send messages to (and from)',
                                 required=True)
    
    server_ip = discord.ui.TextInput(label='Server IP',
                                    placeholder='Server IP (http(s)://localhost:port)',
                                    required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Processing...", ephemeral=True)
        self.stop()

class OocRelay(commands.Cog):
    """
    Replaces Mommi by being actually easy to setup.
    Listens to specified port on all paths. Use this to relay OOC messages to a web server.
    So set cvar status.mommiurl to http://localhost:9080/server_name" and you are good to go. Replace server_name with the name of your server.
    This is used to identify to which channel the message should be sent. Your message will be rejected if no matching server is found in the config.

    This cog only has global settings, which is the reason why only the owner can use the commands. 
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8092547339, force_registration=True)

        default_global = {
            "port": 9080,
            "ip": "localhost",  # Change this to your server's IP if you want it to be accessible from other devices
            "servers": [],
        }

        self.config.register_global(**default_global)
        self.runner = None
        self.bot.loop.create_task(self.start_http_server())

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()
            log.info("Server stopped")

    async def start_http_server(self):
        ip = await self.config.ip()
        port = await self.config.port()

        port = int(port)

        app = web.Application()
        app.router.add_route('*', '/{tail:.*}', self.handle_request)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, ip, port)
        await site.start()
        log.info(f"Server started on {ip}:{port}")

    async def handle_request(self, request: web.Request):
        method = request.method
        path = request.path
        try:
            data = await request.json() if request.can_read_body else None
        except Exception:
            data = None

        if data is None:
            return web.Response(text="Invalid request", status=400)
        
        servers = await self.config.servers()
        server = next((server for server in servers if server["name"] == path[1:]), None)
        if server is None:
            log.debug(f"Server not found for path {path}")
            return web.Response(text="Server not found", status=404)

        # ensure authentication
        if data.get("password") != server["password"]:
            log.debug(f"Invalid password for path {path}")
            return web.Response(text="Invalid password", status=401)
        
        # ensure type is correct
        # im not actually sure if mommi ever sends anything other than "ooc" but just in case
        if data.get("type") != "ooc":
            log.debug(f"Unsupported type for path {path}")
            return web.Response(text="Type is unsupported", status=400)
        
        # get the channel
        channel = self.bot.get_channel(int(server["channel"]))
        if channel is None:
            log.error(f"Channel not found for path {path}")
            return web.Response(text="Relay not set up correctly", status=500)

        # send the message
        await channel.send(f"**OOC**: `{data['contents']['sender']}`: {data['contents']['contents']}", allowed_mentions=discord.AllowedMentions.none())
        log.debug(f"Message sent to channel {channel.id}")

        return web.Response(text="Message sent", status=200)        

    async def send_message(self, server, message: discord.Message):
        async with ClientSession() as session:
            try:
                await session.post(server["server_ip"] + "ooc", json={
                    "password": server["password"],
                    "sender": message.author.name,
                    "contents": message.content
                })
            except Exception as e:
                log.error(f"Failed to send message to {server['name']}: {e}")


    @commands.hybrid_command()
    @commands.is_owner()
    async def oocrelay(self, ctx: commands.Context, port: int, ip: str):
        """
        Set the port and IP for the OOC relay server.
        """
        await self.config.ip.set(ip)
        await self.config.port.set(port)
        await ctx.send(f"OOC relay server set to {ip}:{port}")

    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def addrelay(self, ctx: commands.Context):
        """
        Add a server to the relay.
        """
        
        view = Button(member=ctx.author)

        await ctx.send("To add an ooc relay press this button.", view=view)
        await view.wait()
        if view.modal is None:
            return

        if not view.modal.name.value:
            return

        async with self.config.servers() as cur_servers:
            server_name = view.modal.name.value
            server_password = view.modal.password.value
            server_channel = view.modal.channel.value
            server_ip = view.modal.server_ip.value

            # final server format: {"name": "server_name", "password": "password", "channel": "channel_id"}
            if any(server["name"] == server_name for server in cur_servers):
                return await ctx.send("Server already exists.")
            
            # http paths can only contain letters, numbers, and underscores
            if not server_name.isalnum():
                return await ctx.send("Server name can only contain letters and numbers.")
                
            # check if the channel exists
            try:
                channel = ctx.guild.get_channel(int(server_channel))
            except ValueError:
                return await ctx.send("Invalid channel ID.")
            
            if channel is None:
                return await ctx.send("Channel not found.")
            
            # ensure the channel is a text channel
            if channel.type != discord.ChannelType.text:
                return await ctx.send("Channel must be a text channel.")
            
            # ensure the server ip is valid
            # it must end with a slash and must be http or https
            if not server_ip.endswith("/") or not server_ip.startswith(("http://", "https://")):
                return await ctx.send("Invalid server IP.")

            cur_servers.append({"name": server_name, "password": server_password, "channel": server_channel, "server_ip": server_ip})

        await ctx.send("Server added successfully.")

    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def removerelay(self, ctx: commands.Context, server_name: str):
        """
        Remove a server from the relay.
        """
        async with self.config.servers() as cur_servers:
            server = next((server for server in cur_servers if server["name"] == server_name), None)
            if server is None:
                return await ctx.send("Server not found.")
            
            cur_servers.remove(server)

        await ctx.send("Server removed successfully.")
    
    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def listrelays(self, ctx: commands.Context):
        """
        List all servers that are being relayed.
        """
        servers = await self.config.servers()
        if not servers:
            return await ctx.send("No servers found.")
        
        server_list = "\n".join(f"{server['name']} - <#{server['channel']}> - `{server['server_ip']}`" for server in servers)
        await ctx.send(f"**Servers:**\n{server_list}")


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.type != discord.ChannelType.text:
            return

        servers = await self.config.servers()
        server = next((server for server in servers if server["channel"] == str(message.channel.id)), None)
        if server is None:
            return

        await self.send_message(server, message)