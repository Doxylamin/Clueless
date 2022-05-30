from io import BytesIO
from itertools import cycle

import plotly.express as px
import plotly.graph_objects as go
from matplotlib import cm as cm
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

from utils.image.image_utils import hex_to_rgb, is_dark, lighten_color, rgb_to_hex
from utils.utils import in_executor

""" Themes and util functions for the plotly plots """


def add_glow(
    fig: go.Figure,
    nb_glow_lines=10,
    diff_linewidth=1.5,
    alpha_lines=0.5,
    glow_color="line_color",
    dark_only=False,
):
    """Add a glow effect to all the lines in a Figure object.

    Each existing line is redrawn several times with increasing width and low
    alpha to create the glow effect.
    """
    alpha_value = alpha_lines / nb_glow_lines

    for trace in fig.select_traces():
        x = trace.x
        y = trace.y
        mode = trace.mode
        line_width = trace.line.width
        line_color = trace.marker.color
        if line_color.startswith("rgba"):
            rgba = eval(line_color[4:])
            rgb = rgba[:-1]
            line_color = rgb_to_hex(rgb)
        elif line_color.startswith("rgb"):
            line_color = rgb_to_hex(eval(line_color[3:]))

        # skip the color if dark_only is true and the color is not dark
        if dark_only and not is_dark(hex_to_rgb(line_color)):
            continue

        if glow_color == "line_color":
            color = line_color

        elif glow_color == "lighten_color":
            # lighten only the dark colors
            if is_dark(hex_to_rgb(line_color)):
                color = rgb_to_hex(lighten_color(hex_to_rgb(line_color), 0.2))
            else:
                color = line_color
        else:
            color = glow_color

        # add the glow
        for n in range(nb_glow_lines):
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode=mode,
                    line=dict(width=line_width + (diff_linewidth * n)),
                    marker=dict(color=hex_to_rgba_string(color, alpha_value)),
                )
            )

        # add the original trace over the glow
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode=mode,
                line=dict(width=line_width),
                marker=dict(color=line_color),
            )
        )


def hex_to_rgba_string(hex: str, alpha_value=1) -> str:
    """'#ffffff' -> 'rgba(255,255,255,alpha_value)'"""
    hex = hex.strip("#")

    rgb = tuple([int(hex[i : i + 2], 16) for i in range(0, len(hex), 2)])
    rgba = rgb + (alpha_value,)

    return "rgba" + str(rgba)


@in_executor()
def fig2img(fig, width=2000, height=900, scale=1):
    buf = BytesIO()
    fig.write_image(buf, format="png", width=width, height=height, scale=scale)
    img = Image.open(buf)
    return img


def matplotlib_to_plotly(cmap_name, nb_colors):
    """convert a matplotlib cmap to a list of colors in the format
    'rgba(r,g,b,a)'"""
    cmap = cm.get_cmap(cmap_name)
    cmap_rgba = []

    if nb_colors <= 1:
        rgba = cmap(0, bytes=True)
        rgb = rgba[:-1]
        hex = rgb_to_hex(rgb)
        cmap_rgba.append(hex)
    else:
        for i in range(0, nb_colors):
            rgba = cmap(i / (nb_colors - 1), bytes=True)
            rgb = rgba[:-1]
            hex = rgb_to_hex(rgb)
            cmap_rgba.append(hex)
    return cmap_rgba


def plotly_rgb_to_hex(plotly_palette):
    for i, c in enumerate(plotly_palette):
        if c.startswith("rgba"):
            rgba = eval(c[4:])
            rgb = rgba[:-1]
            plotly_palette[i] = rgb_to_hex(rgb)

        elif c.startswith("rgb"):
            plotly_palette[i] = rgb_to_hex(eval(c[3:]))
    return plotly_palette


def cycle_through_list(list, number_of_element: int):
    """loop through a list the desired amount of time
    example: cycle_through_list([1,2,3],6) -> [1,2,3,1,2,3]"""
    if len(list) == 0 or number_of_element == 0:
        return None
    list = cycle(list)
    res = []
    count = 0
    for i in list:
        res.append(i)
        count += 1
        if count == number_of_element:
            break
    return res


def get_gradient_palette(color_list, nb_colors):
    """Generate a gradient with the colors of `color_list`
    as a list of hex colors and a size of `nb_colors`"""
    cmap = LinearSegmentedColormap.from_list(
        name="speed",
        colors=color_list,
    )
    color_list = []
    for i in range(nb_colors):
        rgba = cmap(i / (nb_colors - 1), bytes=True)
        rgb = rgba[:-1]
        hex = rgb_to_hex(rgb)
        color_list.append(hex)
    return color_list


class Theme:
    def __init__(
        self,
        name,
        description,
        background_color,
        headers_background_color,
        grid_color,
        font_color,
        table_outline_color,
        off_color,
        has_glow,
        has_underglow,
        palette,
        outline_dark,
        odd_row_color,
        table_outline_width,
        red_color,
    ):

        self.name = name
        self.description = description
        self.background_color = background_color
        self.headers_background_color = headers_background_color
        self.grid_color = grid_color
        self.font_color = font_color
        self.table_outline_color = table_outline_color
        self.off_color = off_color
        self.has_glow = has_glow
        self.has_underglow = has_underglow
        self.palette = palette
        self.outline_dark = outline_dark
        self.odd_row_color = odd_row_color
        self.table_outline_width = table_outline_width
        self.red_color = red_color

    def get_palette(self, nb_colors):
        if self.palette == "synthwave":
            colors = matplotlib_to_plotly("cool", nb_colors)
            return colors

        elif self.palette == "autumn":
            colors = matplotlib_to_plotly("autumn", nb_colors)
            return colors

        elif self.palette == "pastel":
            colors = px.colors.qualitative.Pastel1
            colors = colors[1:]
            colors = plotly_rgb_to_hex(colors)
            return cycle_through_list(colors, nb_colors)

        elif self.palette == "pxls":
            colors = [
                "#88FFF3",
                "#277E6C",
                "#FDE817",
                "#FFD5BC",
                "#F02523",
                "#BEFF40",
                "#FFA9D9",
                "#FFFFFF",
                "#70DD13",
                "#FFF491",
                "#D24CE9",
                "#32B69F",
                "#31A117",
                "#77431F",
                "#B11206",
                "#24B5FE",
                "#888888",
                "#FCA80E",
                "#0B5F35",
                "#FC7510",
                "#740C00",
                "#FFB783",
                "#FF59EF",
                "#CDCDCD",
                "#FF6474",
                "#B66D3D",
                "#8B2FA8",
                "#125CC7",
            ]
            return cycle_through_list(colors, nb_colors)

        elif self.palette == "discord":
            colors = [
                "#5866ef",
                "#3da560",
                "#f37b68",
                "#ec4145",
                "#9b84ec",
                "#f9a62b",
                "#0cba99",
                "#4f5d7e",
                "#fe73f6",
                "#583694",
                "#09b0f2",
            ]
            return cycle_through_list(colors, nb_colors)

        # default palette
        else:
            colors = px.colors.qualitative.Pastel
            colors = plotly_rgb_to_hex(colors)
            return cycle_through_list(colors, nb_colors)

    def get_layout(self, with_annotation=True, annotation_text=None):
        if not annotation_text:
            annotation_text = "Timezone: UTC"
        if with_annotation:
            layout = go.Layout(
                paper_bgcolor=self.background_color,
                plot_bgcolor=self.background_color,
                font_color=self.font_color,
                font_size=35,
                yaxis=dict(
                    showgrid=True,
                    gridwidth=1.5,
                    gridcolor=self.grid_color,
                    tickformat=",d",
                ),
                xaxis=dict(showgrid=True, gridwidth=1.5, gridcolor=self.grid_color),
                margin=dict(b=150),
                annotations=[
                    go.layout.Annotation(
                        x=1,
                        y=-0.1,
                        text=annotation_text,
                        showarrow=False,
                        xref="paper",
                        yref="paper",
                        xanchor="right",
                        yanchor="auto",
                        xshift=0,
                        yshift=-80,
                        font=dict(color=self.off_color),
                    )
                ],
            )
        else:
            layout = go.Layout(
                paper_bgcolor=self.background_color,
                plot_bgcolor=self.background_color,
                font_color=self.font_color,
                font_size=35,
                yaxis=dict(
                    showgrid=True,
                    gridwidth=1.5,
                    gridcolor=self.grid_color,
                    tickformat=",d",
                ),
                xaxis=dict(
                    showgrid=True,
                    gridwidth=1.5,
                    gridcolor=self.grid_color,
                ),
            )

        return layout


default_theme = Theme(
    name="default",
    description="Pastel colors, dark background.",
    background_color="#202225",
    headers_background_color="#000000",
    grid_color="#393b40",
    font_color="#b9bbbe",
    table_outline_color="#000000",
    off_color="#696969",
    has_glow=False,
    has_underglow=False,
    palette="default",
    outline_dark=True,
    odd_row_color="#000000",
    table_outline_width=3,
    red_color="#d13030",
)

synthwave_theme = Theme(
    name="synthwave",
    description="Neon colors, dark/blue background (can be slower).",
    background_color="#1d192c",
    headers_background_color="#000000",
    grid_color="#514384",
    font_color="#c1ebff",
    table_outline_color="#000000",
    off_color="#6954b7",
    has_glow=True,
    has_underglow=True,
    palette="synthwave",
    outline_dark=True,
    odd_row_color="#000000",
    table_outline_width=3,
    red_color="#f20055",
)

synthwave_noglow_theme = Theme(
    name="synthwave-noglow",
    description="Same as `synthwave` but without glow which makes it faster.",
    background_color="#1d192c",
    headers_background_color="#000000",
    grid_color="#514384",
    font_color="#c1ebff",
    table_outline_color="#000000",
    off_color="#6954b7",
    has_glow=False,
    has_underglow=False,
    palette="synthwave",
    outline_dark=True,
    odd_row_color="#000000",
    table_outline_width=3,
    red_color="#f20055",
)

pxls_theme = Theme(
    name="pxls",
    description="Similar to the pxls purple theme, uses the pxls palette for the lines/bars.",
    background_color="#3d204d",
    headers_background_color="#341943",
    grid_color="#693684",
    font_color="#dddddd",
    table_outline_color="#2a1436",
    off_color="#733a92",
    has_glow=False,
    has_underglow=False,
    palette="pxls",
    outline_dark=False,
    odd_row_color="#341943",
    table_outline_width=3,
    red_color="#f02523",
)

pastel_theme = Theme(
    name="pastel",
    description="Pastel colors, light-purple background.",
    background_color="#937ac3",
    headers_background_color="#7f65b1",
    grid_color="#fac4ff",
    font_color="#fac4ff",
    table_outline_color="#725c9d",
    off_color="#bcaad0",
    has_glow=False,
    has_underglow=False,
    palette="pastel",
    outline_dark=True,
    odd_row_color="#7f65b1",
    table_outline_width=3,
    red_color="#fbb4ae",
)

red_theme = Theme(
    name="red",
    description="It's red.",
    background_color="#1e0300",
    headers_background_color="#000000",
    grid_color="#7b0001",
    font_color="#ffbbb9",
    table_outline_color="#000000",
    off_color="#7b0001",
    has_glow=False,
    has_underglow=True,
    palette="autumn",
    outline_dark=False,
    odd_row_color="#000000",
    table_outline_width=3,
    red_color="#d00200",
)

light_theme = Theme(
    name="light",
    description="To burn your eyes.",
    background_color="#d4ddeb",
    headers_background_color="#adbbce",
    grid_color="#f2f3f5",
    font_color="#23272a",
    table_outline_color="#f2f3f5",
    off_color="#9cb3d1",
    has_glow=False,
    has_underglow=False,
    palette="discord",
    outline_dark=False,
    odd_row_color="#adbbce",
    table_outline_width=0,
    red_color="#ec4145",
)

theme_list = [
    default_theme,
    synthwave_theme,
    synthwave_noglow_theme,
    pastel_theme,
    pxls_theme,
    red_theme,
    light_theme,
]


def get_theme(theme_name) -> Theme:
    for theme in theme_list:
        if theme.name.lower() == theme_name.lower():
            return theme
    return None
