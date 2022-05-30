from datetime import datetime, timedelta, timezone

import disnake
import plotly.graph_objects as go
from disnake.ext import commands

from utils.arguments_parser import MyParser
from utils.discord_utils import format_number, image_to_file
from utils.image.image_utils import (
    get_builtin_palette,
    get_color,
    hex_to_rgb,
    is_dark,
    lighten_color,
    rgb_to_hex,
    v_concatenate,
)
from utils.plot_utils import add_glow, fig2img, get_theme
from utils.setup import db_stats, db_users, stats
from utils.table_to_image import table_to_image
from utils.time_converter import format_timezone, round_minutes_down, str_to_td
from utils.timezoneslib import get_timezone
from utils.utils import in_executor, shorten_list


class ColorsGraph(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="colorsgraph")
    async def _colorsgraph(
        self,
        inter: disnake.AppCmdInter,
        colors: str = None,
        placed: bool = False,
        last: str = None,
    ):
        """Show a graph of the canvas colors.

        Parameters
        ----------
        colors: List of pxls colors separated by a comma.
        placed: To show the graph for the non-virgin pixels only.
        last: Show the progress in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)
        """
        await inter.response.defer()
        args = ()
        if colors:
            args += (colors,)
        if placed:
            args += ("-placed",)
        if last:
            args += ("-last", last)
        await self.colorsgraph(inter, *args)

    @commands.command(
        name="colorsgraph",
        aliases=["colorgraph", "coloursgraph", "colourgraph", "cg"],
        description="Show a graph of the canvas colors.",
        usage="[colors] [-placed|-p] [-last ?y?mo?w?d?h?m?s]",
        help="""\t- `<colors>`: list of pxls colors separated by a comma
        \t- `[-placed|-p]`: only show the virgin pixels
        \t- `[-last ?y?mo?w?d?h?m?s]` Show the progress in the last x years/months/weeks/days/hours/minutes/seconds""",
    )
    async def p_colorsgraph(self, ctx, *args):
        async with ctx.typing():
            await self.colorsgraph(ctx, *args)

    async def colorsgraph(self, ctx, *args):
        "Show a graph of the canvas colors."

        discord_user = await db_users.get_discord_user(ctx.author.id)

        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("colors", type=str, nargs="*")
        parser.add_argument("-placed", action="store_true", default=False, required=False)
        parser.add_argument("-last", "-l", nargs="+", default=None)
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # check on 'last' param
        if parsed_args.last:
            input_time = str_to_td(parsed_args.last)
            if not input_time:
                return await ctx.send(
                    "❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
                )
            dt2 = datetime.now(timezone.utc)
            dt1 = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
            dt2 = None
            dt1 = None

        # format colors in a list
        colors = parsed_args.colors
        if parsed_args.colors:
            colors = " ".join(colors).split(",")
            colors = [c.strip() for c in colors]
            # search for a palette
            for color in colors[:]:
                found_palette = get_builtin_palette(color, as_rgba=False)
                if found_palette:
                    colors.remove(color)
                    colors += found_palette
            for i, c in enumerate(colors):
                try:
                    colors[i] = get_color(c, pxls_only=True)[0].lower()
                except Exception as e:
                    print(e)
                    return await ctx.send(f"❌ The color `{c}` is invalid.")
        # init the 'placed' option
        placed_opt = False
        if parsed_args.placed:
            placed_opt = True

        canvas_code = await stats.get_canvas_code()
        data = await db_stats.get_canvas_color_stats(canvas_code, dt1, dt2)

        palette = await db_stats.get_palette(canvas_code)

        # initialise a data dictionary for each color
        data_list = []
        for color in palette:
            color_id = color["color_id"]
            color_name = color["color_name"]
            color_hex = "#" + color["color_hex"]
            color_dict = dict(
                color_id=color_id,
                color_name=color_name,
                color_hex=color_hex,
                values=[],
                datetimes=[],
            )
            data_list.append(color_dict)

        # add the data to the dict
        for value in data:
            color_id = value["color_id"]
            dt = value["datetime"]
            if placed_opt:
                pixels = value["amount_placed"]
            else:
                pixels = value["amount"]

            data_list[color_id]["values"].append(pixels)
            data_list[color_id]["datetimes"].append(dt)

        if parsed_args.last:
            for d in data_list:
                d["values"] = [v - d["values"][0] for v in d["values"]]
        # create the graph and style
        fig = await make_color_graph(data_list, colors, discord_user["timezone"])
        if fig is None:
            return await ctx.send("❌ Invalid color name.")
        fig.update_layout(title="Colors Graph" + (" (non-virgin)" if placed_opt else ""))

        # format the table data
        table_rows = []
        for d in data_list:
            if len(colors) > 0 and d["color_name"].lower() not in colors:
                continue
            diff_time = d["datetimes"][-1] - d["datetimes"][0]
            diff_values = d["values"][-1] - d["values"][0]
            nb_hour = diff_time / timedelta(hours=1)
            speed_per_hour = diff_values / nb_hour
            speed_per_day = speed_per_hour * 24
            table_rows.append(
                (
                    d["color_name"],
                    diff_values,
                    format_number(round(speed_per_hour, 2)),
                    format_number(round(speed_per_day, 2)),
                    d["color_hex"],
                )
            )
        table_rows.sort(key=lambda x: x[1], reverse=True)
        table_colors = [row[-1] for row in table_rows]
        table_rows = [row[:-1] for row in table_rows]
        # format the 'progress' value
        for i, row in enumerate(table_rows):
            new_row = list(row)
            new_row[1] = format_number(row[1])
            table_rows[i] = new_row

        font = discord_user["font"]
        table_img = await table_to_image(
            table_rows,
            ["Color", "Progress", "px/h", "px/d"],
            alignments=["center", "right", "right", "right"],
            colors=table_colors,
            font=font,
        )

        files = await fig2file(fig, "colors_graph.png", table_img)
        await ctx.send(files=files)


@in_executor()
def make_color_graph(data_list, colors, user_timezone=None):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    layout = get_theme("default").get_layout(annotation_text=annotation_text)
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)

    colors_found = False
    for color in data_list:
        if len(colors) > 0 and color["color_name"].lower() not in colors:
            continue
        colors_found = True

        values = color["values"]
        dates = color["datetimes"]
        dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc), tz) for d in dates]

        # remove some data if we have too much
        limit = 200
        if len(values) > limit:
            values = shorten_list(values, limit)
            dates = shorten_list(dates, limit)

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines",
                name=color["color_name"],
                line=dict(width=4),
                marker=dict(color=color["color_hex"]),
            )
        )

        # add an annotation at the right with the color name
        if is_dark(hex_to_rgb(color["color_hex"])):
            # add an outline to the color name if it's too dark
            text = '<span style = "text-shadow:\
                -{2}px -{2}px 0 {0},\
                {2}px -{2}px 0 {0},\
                -{2}px {2}px 0 {0},\
                {2}px {2}px 0 {0},\
                0px {2}px 0px {0},\
                {2}px 0px 0px {0},\
                -{2}px 0px 0px {0},\
                0px -{2}px 0px {0};"><b>{1}</b></span>'.format(
                rgb_to_hex(lighten_color(hex_to_rgb(color["color_hex"]), 0.4)),
                color["color_name"],
                2,
            )
        else:
            text = "<b>%s</b>" % color["color_name"]

        fig.add_annotation(
            xanchor="left",
            xref="paper",
            yref="y",
            x=1.01,
            y=color["values"][-1],
            text=text,
            showarrow=False,
            font=dict(color=color["color_hex"], size=30),
        )

    if not colors_found:
        return None

    # add a marge at the right to avoid cropping color names
    longest_name = max([len(c["color_name"]) for c in data_list])
    fig.update_layout(margin=dict(r=(longest_name + 2) * 20))

    # add a glow to the dark colors
    add_glow(fig, glow_color="lighten_color", dark_only=True, nb_glow_lines=5)
    return fig


async def fig2file(fig, title, table_img):

    graph_img = await fig2img(fig)
    if table_img.size[0] > table_img.size[1]:
        res_img = await v_concatenate(table_img, graph_img, gap_height=20)
        res_file = await image_to_file(res_img, title)
        return [res_file]
    else:
        table_file = await image_to_file(table_img, "table.png")
        graph_file = await image_to_file(graph_img, title)
        return [table_file, graph_file]


def setup(bot: commands.Bot):
    bot.add_cog(ColorsGraph(bot))
