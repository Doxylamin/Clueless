from datetime import datetime, timedelta, timezone

import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image, ImageEnhance

from cogs.pixel_art.color_breakdown import _colors
from cogs.pixel_art.highlight import _highlight
from utils.arguments_parser import MyParser
from utils.discord_utils import (
    STATUS_EMOJIS,
    UserinfoView,
    autocomplete_pxls_name,
    format_number,
    image_to_file,
)
from utils.plot_utils import matplotlib_to_plotly
from utils.pxls.cooldown import get_best_possible
from utils.setup import db_conn, db_stats, db_users, stats
from utils.time_converter import format_datetime, round_minutes_down, td_format
from utils.utils import make_progress_bar


class PxlsStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="generalstats")
    async def _generalstats(self, inter: disnake.AppCmdInter):
        """Show some general stats about the canvas."""
        await inter.response.defer()
        await self.generalstats(inter)

    @commands.command(
        name="generalstats",
        description="Show some general stats about the canvas.",
        aliases=["gstats", "gs", "canvasinfo"],
    )
    async def p_generalstats(self, ctx):
        async with ctx.typing():
            await self.generalstats(ctx)

    async def generalstats(self, ctx):
        # getting the general stats from pxls.space/stats
        gen_stats = stats.get_general_stats()
        total_users = gen_stats["total_users"]
        total_factions = gen_stats["total_factions"]
        total_placed = gen_stats["total_pixels_placed"]
        active_users = gen_stats["users_active_this_canvas"]

        # calculate canvas stats
        board = stats.board_array
        virginmap = stats.virginmap_array
        placemap = stats.placemap_array
        total_amount = board.shape[0] * board.shape[1]
        total_placeable = np.sum(placemap != 255)
        total_non_virgin = np.sum(np.logical_and(virginmap == 0, placemap == 0))
        pixel_per_user = int(total_placed) / int(active_users)

        # get canvas info
        canvas_code = await stats.get_canvas_code()
        last_updated = stats.last_updated_to_date(stats.get_last_updated())
        # find the earliest datetime for the current canvas
        sql = "SELECT MIN(datetime),datetime FROM record WHERE canvas_code = ?"
        start_date = await db_conn.sql_select(sql, canvas_code)
        start_date = start_date[0]["datetime"]

        # get average cd/online
        data = await db_stats.get_general_stat(
            "online_count", datetime.min, datetime.max, canvas_code=canvas_code
        )
        online_counts = [int(e[0]) for e in data if e[0] is not None]
        cooldowns = [stats.get_cd(count) for count in online_counts]
        average_online = sum(online_counts) / len(online_counts)
        min_online = min(online_counts)
        max_online = max(online_counts)
        average_cd = sum(cooldowns) / len(cooldowns)

        # calculate the filling speed
        canvas_time = (datetime.utcnow() - start_date) / timedelta(days=1)
        canvas_fill_speed = total_non_virgin / canvas_time  # in px/day

        # calculate the ETA with the filling speed in the last 2 days
        goal = 95  # % of canvas filled
        time_interval = 1  # number of days to calculate the recent filling speed
        time_to_search = round_minutes_down(
            datetime.utcnow() - timedelta(days=time_interval) - timedelta(minutes=1)
        )
        record = await db_stats.find_record(time_to_search, canvas_code)
        record_time = round_minutes_down(record["datetime"].replace(tzinfo=timezone.utc))
        sql = (
            "SELECT SUM(amount_placed) AS non_virgin FROM color_stat WHERE record_id = ?"
        )
        non_virgin_interval = await db_stats.db.sql_select(sql, record["record_id"])
        time_diff = round_minutes_down(last_updated) - record_time

        if non_virgin_interval[0]["non_virgin"] is None:
            filling_progress = None
            canvas_fill_speed_interval = None
            pixels_until_goal = None
            eta = None
        else:
            filling_progress = total_non_virgin - non_virgin_interval[0]["non_virgin"]
            canvas_fill_speed_interval = filling_progress / (
                time_diff / timedelta(days=1)
            )
            pixels_until_goal = (total_placeable * goal / 100) - total_non_virgin
            eta = pixels_until_goal / canvas_fill_speed_interval
            if eta <= 0:
                goal = 100
                pixels_until_goal = (total_placeable * goal / 100) - total_non_virgin
                eta = pixels_until_goal / canvas_fill_speed_interval

        if eta is None:
            pass
        elif eta <= 0:
            eta = "where reset 💀"
        else:
            td_eta = timedelta(days=eta)
            days = td_eta.days
            seconds = td_eta.seconds
            hours = round(seconds / 3600)
            eta_array = []
            if days:
                eta_array.append(f"{days} day{'s' if days > 1 else ''}")
            if hours or days == 0:
                if hours == 0 and days == 0:
                    eta_array.append("< 1 hour")
                else:
                    eta_array.append(f"{hours} hour{'s' if hours > 1 else ''}")
            eta = ", ".join(eta_array)

        general_stats_text = "• Total Users: `{}`\n• Total Factions: `{}`".format(
            format_number(total_users), format_number(total_factions)
        )

        info_text = "• Canvas Code: `{}`\n• Start Date: {}\n• Time Elapsed: {}\n• Dimensions: `{} x {}`\n• Total Pixels: `{}`/`{}` (`{}%` placeable)\n".format(
            canvas_code,
            format_datetime(start_date),
            td_format(datetime.utcnow() - start_date, hide_seconds=True, max_unit="day"),
            board.shape[1],
            board.shape[0],
            format_number(int(total_placeable)),
            format_number(total_amount),
            format_number(total_placeable / total_amount * 100),
        )

        canvas_stats_text = """
        • Canvas Users: `{}`\n• Average online: `{}` users (min: `{}`, max: `{}`)\n• Average cooldown: `{}s`\n• Total Placed: `{}`\n• Average pixels per user: `{}`""".format(
            active_users,
            round(average_online, 2),
            min_online,
            max_online,
            round(average_cd, 2),
            format_number(total_placed),
            format_number(int(pixel_per_user)),
        )

        completion_text = """
        • Total Non-Virgin: `{}`/`{}`\n• Average filling speed: `{}` px/day\n(last {}: `{}` px/day)\n• Percentage Non-Virgin:\n**|**{}**|** `{}%`\nReset ETA (until {}% full): ~`{}`
        """.format(
            format_number(int(total_non_virgin)),
            format_number(int(total_placeable)),
            format_number(canvas_fill_speed),
            td_format(time_diff, hide_seconds=True),
            format_number(canvas_fill_speed_interval),
            f"`{make_progress_bar(total_non_virgin/total_placeable*100)}`",
            format_number(total_non_virgin / total_placeable * 100),
            goal,
            eta or "N/A",
        )

        # create an embed with all the infos
        emb = disnake.Embed(title="Pxls.space Stats", color=0x66C5CC)
        emb.add_field(name="**General Stats**", value=general_stats_text, inline=False)
        emb.add_field(name="**Canvas Info**", value=info_text, inline=False)
        emb.add_field(name="**Canvas Stats**", value=canvas_stats_text, inline=False)
        emb.add_field(name="**Canvas Completion**", value=completion_text, inline=False)

        emb.add_field(
            name="\u200b",
            value="Last updated: " + format_datetime(last_updated, "R"),
            inline=False,
        )

        # set the board image as thumbnail
        board_array = stats.palettize_array(board)
        board_img = Image.fromarray(board_array)
        f = await image_to_file(board_img, "board.png")
        emb.set_thumbnail(url="attachment://board.png")

        await ctx.send(embed=emb, file=f)

    @commands.slash_command(name="userinfo")
    async def _userinfo(
        self,
        inter: disnake.AppCmdInter,
        username: str = commands.Param(default=None, autocomplete=autocomplete_pxls_name),
    ):
        """Show some information about a pxls user.

        Parameters
        ----------
        username: A pxls username."""
        await inter.response.defer()
        await self.userinfo(inter, username)

    @commands.command(
        name="userinfo",
        aliases=["uinfo", "status"],
        usage="<username>",
        description="Show some information about a pxls user.",
        help=f"""
        -`<username>`: a pxls username (will use your set username if set)\n
        **Status explanation:**
        {STATUS_EMOJIS["bot"]} `online (botting)`: the user is placing more than the best possible
        {STATUS_EMOJIS["fast"]}`online (fast)`: the user is close to the best possible in the last 15 minutes
        {STATUS_EMOJIS["online"]}`online`: the user placed in the last 15 minutes
        {STATUS_EMOJIS["idle"]}`idle`: the user stopped placing 15/30 minutes ago
        {STATUS_EMOJIS["offline"]}`offline`: The user hasn't placed in the last 30 minutes
        {STATUS_EMOJIS["inactive"]}`inactive`: The user hasn't placed on the current canvas
        """,
    )
    async def p_userinfo(self, ctx, username=None):
        async with ctx.typing():
            await self.userinfo(ctx, username)

    async def userinfo(self, ctx, name=None):
        "Show some information about a pxls user."
        if name is None:
            # select the discord user's pxls username if it has one linked
            discord_user = await db_users.get_discord_user(ctx.author.id)
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id is None:
                is_slash = not isinstance(ctx, commands.Context)
                cmd_name = "user setname" if is_slash else "setname"
                prefix = "/" if is_slash else ctx.prefix
                return await ctx.send(
                    f"❌ You need to specify a pxls username.\n(You can set your default username with `{prefix}{cmd_name} <username>`)"
                )
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                user_id = pxls_user_id
        else:
            user_id = await db_users.get_pxls_user_id(name)
            if user_id is None:
                return await ctx.send("❌ User not found.")

        # get current pixels and leaderboard place
        last_leaderboard = await db_stats.get_last_leaderboard()
        user_row = None
        for row in last_leaderboard:
            if row["name"] == name:
                user_row = row
                break

        if user_row is None:
            # if the user isn't on the last leaderboard
            alltime_rank = canvas_rank = ">1000"
            alltime_count = canvas_count = None
            last_updated = "-"
        else:
            alltime_rank = user_row["alltime_rank"]
            if alltime_rank > 1000:
                alltime_rank = ">1000"
            alltime_count = user_row["alltime_count"]

            canvas_rank = user_row["canvas_rank"]
            if canvas_rank > 1000:
                canvas_rank = ">1000"
            canvas_count = user_row["canvas_count"]
            if canvas_count == 0:
                canvas_rank = "N/A"

            last_updated = format_datetime(user_row["datetime"], "R")

        alltime_text = "• Rank: `{}`\n• Pixels: `{}`".format(
            alltime_rank, format_number(alltime_count)
        )
        canvas_text = "• Rank: `{}`\n• Pixels: `{}`".format(
            canvas_rank, format_number(canvas_count)
        )

        # get the recent activity stats
        time_intervals = [0.25, 1, 24, 24 * 7]  # in hours
        time_intervals.append(0.5)
        interval_names = ["15 min", "hour", "day", "week"]
        record_id_list = []
        record_list = []
        now_time = datetime.now(timezone.utc)
        current_canvas_code = await stats.get_canvas_code()
        for time_interval in time_intervals:
            time = now_time - timedelta(hours=time_interval) - timedelta(minutes=1)
            time = round_minutes_down(time)
            record = await db_stats.find_record(time, current_canvas_code)
            record_id = record["record_id"]
            record_id_list.append(record_id)
            record_list.append(record)

        sql = """
            SELECT canvas_count, alltime_count, record_id
            FROM pxls_user_stat
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE pxls_user_id = ?
            AND record_id IN ({})
            ORDER BY record_id
        """.format(
            ", ".join(["?"] * len(record_id_list))
        )
        rows = await db_conn.sql_select(sql, (user_id,) + tuple(record_id_list))

        diff_list = []
        for id in record_id_list:
            diff = None
            for row in rows:
                # calcluate the difference for each time if the value is not null
                # and compare the canvas count if the alltime count is null
                if row["record_id"] == id:
                    if alltime_count is not None and row["alltime_count"] is not None:
                        diff = alltime_count - row["alltime_count"]
                    elif canvas_count is not None and row["canvas_count"] is not None:
                        diff = canvas_count - row["canvas_count"]
            diff_list.append(diff)

        recent_activity = [
            f"• Last {interval_names[i]}: `{format_number(diff_list[i])}`"
            for i in range(len(diff_list) - 1)
        ]
        recent_activity_text = "\n".join(recent_activity)
        recent_activity_text += f"\n\nLast updated: {last_updated}"

        # get the status
        last_15m = diff_list[0]
        last_30m = diff_list[-1]
        last_online_date = None
        session_start_str = None

        # online
        if last_15m is not None and last_15m != 0:
            # get the session duration
            session_start = await db_stats.get_session_start_time(
                user_id, not (bool(alltime_count))
            )
            if session_start is not None:
                session_start_dt = session_start["datetime"]
                session_start_str = format_datetime(session_start_dt, "R")

            # if the amount placed in the last 15m is at least 95% of the
            # best possible, the status is 'online (fast)'
            dt2 = user_row["datetime"]
            dt1 = record_list[0]["datetime"]
            best_possible, average_cooldown = await get_best_possible(dt1, dt2)
            fast_amount = int(best_possible * 0.95)

            if last_15m > best_possible:
                status = "online (botting)"
                status_emoji = STATUS_EMOJIS["bot"]
                embed_color = 0x7CE1EC
            elif last_15m >= fast_amount:
                status = "online (fast)"
                status_emoji = STATUS_EMOJIS["fast"]
                embed_color = 0x9676CB
            else:
                status = "online"
                status_emoji = STATUS_EMOJIS["online"]
                embed_color = 0x43B581
        # idle
        elif last_30m is not None and last_30m != 0:
            status = "idle"
            status_emoji = STATUS_EMOJIS["idle"]
            embed_color = 0xFCC15E

        else:
            # search for the last online time
            canvas = not (bool(alltime_count)) if canvas_count or alltime_count else None
            last_online = await db_stats.get_last_online(
                user_id,
                canvas,
                alltime_count or canvas_count,
                current_canvas_code,
            )
            if last_online is not None:
                last_online_date = f"*{format_datetime(last_online['datetime'], 'R')}*"
                canvas_code = last_online["canvas_code"]
                if canvas_code != current_canvas_code:
                    last_online_date += f" `(c{canvas_code})`"
            else:
                last_online_date = await db_stats.find_record(datetime.min)
                last_online_date = last_online_date["datetime"]
                last_online_date = f"*over {format_datetime(last_online_date, 'R')}*"
            # inactive
            if canvas_count == 0 or canvas_count is None:
                status = "inactive"
                status_emoji = STATUS_EMOJIS["inactive"]
                embed_color = 0x484848
            # offline
            else:
                status = "offline"
                status_emoji = STATUS_EMOJIS["offline"]
                embed_color = 0x747F8D

        # get the profile page
        profile_url = "https://pxls.space/profile/{}".format(name)

        description = f"**Status**: {status_emoji} `{status}`\n"
        if session_start_str is not None:
            description += f"*Started placing: {session_start_str}*\n"
        if last_online_date is not None:
            description += f"*Last pixel:* {last_online_date}\n"

        # create and send the embed
        emb = disnake.Embed(
            title=f"User Info for `{name}`", color=embed_color, description=description
        )
        emb.add_field(name="**Canvas stats**", value=canvas_text, inline=True)
        emb.add_field(name="**All-time stats**", value=alltime_text, inline=True)
        emb.add_field(
            name="**Recent activity**", value=recent_activity_text, inline=False
        )
        speed_func = self.bot.get_cog("PxlsSpeed").speed
        view = UserinfoView(ctx.author, profile_url, speed_func, name, bool(canvas_count))
        view.message = await ctx.send(embed=emb, view=view)
        if isinstance(ctx, disnake.AppCmdInter):
            view.message = await ctx.original_message()

    choices = ["heatmap", "virginmap", "nonvirgin", "initial"]

    @commands.slash_command(name="board")
    async def _board(
        self,
        inter: disnake.AppCmdInter,
        display: str = commands.param(default=None, choices=choices),
        opacity: int = commands.Param(default=None, ge=0, le=100),
    ):
        """Get the current pxls board.

        Parameters
        ----------
        display: How to display the canvas.
        opacity: The opacity of the background behind the heatmap between 0 and 100. (default: 20)"""
        await inter.response.defer()
        args = ()
        if display == "heatmap":
            args += ("-heatmap",)
            if opacity is not None:
                args += (str(opacity),)
        elif display:
            args += ("-" + display,)
        await self.board(inter, *args)

    @commands.command(
        name="board",
        description="Get the current pxls board.",
        usage="[-virginmap] [-nonvirgin] [-heatmap [opacity]]",
        help="""
        - `[-virginmap]`: show a map of the virgin pixels (white = virgin)
        - `[-nonvirgin]`: show the board without the virgin pixels
        - `[-heatmap [opacity]]`: show the heatmap on top of the canvas\
            (the opacity value should be between 0 and 100, the default value is 20)
        - `[-initial]`: show the initial state of the canvas""",
    )
    async def p_board(self, ctx, *options):
        async with ctx.typing():
            await self.board(ctx, *options)

    async def board(self, ctx, *args):
        # parse the args
        parser = MyParser(add_help=False)
        parser.add_argument(
            "-heatmap", action="store", default=None, nargs="*", required=False
        )
        parser.add_argument(
            "-nonvirgin", action="store_true", default=False, required=False
        )
        parser.add_argument(
            "-virginmap", action="store_true", default=False, required=False
        )
        parser.add_argument(
            "-initial", action="store_true", default=False, required=False
        )

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        heatmap_opacity = None
        if parsed_args.heatmap is not None:
            # check on the opacity argument
            if len(parsed_args.heatmap) == 0:
                heatmap_opacity = 20
            else:
                heatmap_opacity = parsed_args.heatmap[0]
                try:
                    heatmap_opacity = int(heatmap_opacity)
                except ValueError:
                    return await ctx.send("❌ The opacity value must be an integer.")
                if heatmap_opacity < 0 or heatmap_opacity > 100:
                    return await ctx.send(
                        "❌ The opacity value must be between 0 and 100."
                    )

        # virginmap
        if parsed_args.virginmap:
            array = stats.virginmap_array.copy()
            array[array == 255] = 1
            array[stats.placemap_array != 0] = 255
            array = stats.palettize_array(array, palette=["#000000", "#00DD00"])
            title = "Canvas Virginmap"
        # heatmap
        elif heatmap_opacity is not None:
            # get the heatmap
            array = await stats.fetch_heatmap()
            # invert the values to have the inactive pixels at 255 (which is the default transparent value)
            array = 255 - array
            heatmap_palette = matplotlib_to_plotly("plasma_r", 255)
            array = stats.palettize_array(array, heatmap_palette)
            # get the canvas board
            canvas_array = stats.board_array
            canvas_array = stats.palettize_array(canvas_array)
            title = "Canvas Heatmap"
        # non-virgin board
        elif parsed_args.nonvirgin:
            placeable_board = await stats.get_placable_board()
            virgin_array = stats.virginmap_array
            array = placeable_board.copy()
            array[virgin_array != 0] = 255
            array[virgin_array == 0] = placeable_board[virgin_array == 0]
            array = stats.palettize_array(array)
            title = "Current Board (non-virgin pixels)"
        # initial board
        elif parsed_args.initial:
            array = await stats.fetch_initial_canvas()
            array = stats.palettize_array(array)
            title = "Initial Board"
        # current board
        else:
            array = stats.board_array
            array = stats.palettize_array(array)
            title = "Current Board"

        if heatmap_opacity is not None:
            # paste the heatmap image on top of the darken board
            heatmap_img = Image.fromarray(array)
            board_img = Image.fromarray(canvas_array)
            enhancer = ImageEnhance.Brightness(board_img)
            board_img = enhancer.enhance(heatmap_opacity / 100)
            board_img.paste(heatmap_img, (0, 0), heatmap_img)
        else:
            board_img = Image.fromarray(array)
        embed = disnake.Embed(title=title, color=0x66C5CC)
        embed.timestamp = datetime.now(timezone.utc)
        file = await image_to_file(board_img, "board.png", embed)
        await ctx.send(file=file, embed=embed)

    @commands.slash_command(name="canvascolors")
    async def _canvascolors(self, inter: disnake.AppCmdInter, nonvirgin: bool = False):
        """Show the amount for each color on the canvas.

        Parameters
        ----------
        nonvirgin: To show the amount on the 'non-virgin' pixels only."""
        await inter.response.defer()
        await self.canvascolors(inter, "-placed" if nonvirgin else None)

    @commands.command(
        name="canvascolors",
        description="Show the amount for each color on the canvas.",
        aliases=["canvascolours", "cc"],
        usage="[-placed|-p]",
    )
    async def p_canvascolors(self, ctx, *options):
        async with ctx.typing():
            await self.canvascolors(ctx, *options)

    async def canvascolors(self, ctx, *options):
        """Show the canvas colors."""
        # get the board with the placeable pixels only
        placeable_board = await stats.get_placable_board()

        if "-placed" in options or "-p" in options:
            # use the virgin map as a mask to get the board with placed pixels
            virgin_array = stats.virginmap_array
            placed_board = placeable_board.copy()
            placed_board[virgin_array != 0] = 255
            placed_board[virgin_array == 0] = placeable_board[virgin_array == 0]
            img = Image.fromarray(stats.palettize_array(placed_board))
            title = "Canvas colors breakdown (non-virgin pixels only)"
        else:
            img = Image.fromarray(stats.palettize_array(placeable_board))
            title = "Canvas color breakdown"

        await _colors(self.bot, ctx, img, title)

    @commands.slash_command(name="canvashighlight")
    async def _canvashighlight(
        self,
        inter: disnake.AppCmdInter,
        colors: str,
        bgcolor: str = None,
        placed: bool = False,
    ):
        """Highlight the selected colors on the canvas.

        Parameters
        ----------
        colors: List of pxls colors separated by a comma.
        bgcolor: To display behind the selected colors (can be a color name, hex color, 'none', 'light' or 'dark')
        placed: To highlight the colors only on the non-virgin pixels."""
        await inter.response.defer()
        args = (colors,)
        if bgcolor:
            args += ("-bgcolor", bgcolor)
        if placed:
            args += ("-placed",)
        await self.canvashighlight(inter, *args)

    @commands.command(
        name="canvashighlight",
        description="Highlight the selected colors on the canvas.",
        aliases=["chl", "canvashl"],
        usage="<colors> [-bgcolor|-bg <color>] [-placed]",
        help="""
            - `<colors>`: list of pxls colors separated by a comma
            - `[-bgcolor|bg <color>]`: the color to display behind the higlighted colors, it can be:
                • a pxls name color (ex: "red")
                • a hex color (ex: "#ff000")
                • "none": to have a transparent background
                • "dark": to have the background darkened
                • "light": to have the background lightened
            - `[-placed|-p]`: highlight the colors only on the non-virgin pixels.
        """,
    )
    async def p_canvashighlight(self, ctx, *, args):
        args = args.split(" ")
        async with ctx.typing():
            await self.canvashighlight(ctx, *args)

    async def canvashighlight(self, ctx, *args):
        "Highlight the selected colors on the canvas"
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("colors", type=str, nargs="+")
        parser.add_argument(
            "-bgcolor", "-bg", nargs="*", type=str, action="store", required=False
        )
        parser.add_argument("-placed", action="store_true", default=False, required=False)
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # get the board with the placeable pixels only
        canvas_array_idx = await stats.get_placable_board()
        if parsed_args.placed:
            # only keep virgin pixels
            virgin_array = stats.virginmap_array
            canvas_array_idx[virgin_array != 0] = 255
        array = stats.palettize_array(canvas_array_idx)
        await _highlight(ctx, array, parsed_args.colors.copy(), parsed_args.bgcolor)


def setup(bot: commands.Bot):
    bot.add_cog(PxlsStats(bot))
