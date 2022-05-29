import time

import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from utils.arguments_parser import MyParser
from utils.discord_utils import (
    InterImage,
    ResizeView,
    format_number,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.image.image_utils import (
    get_image_scale,
    get_visible_pixels,
    remove_white_space,
)
from utils.pxls.template_manager import detemplatize, parse_template


class Scale(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="downscale")
    async def _downscale(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage,
        pixel_size: int = commands.Param(name="pixel-size", default=None, gt=1),
    ):
        """Downscale an upscaled pixel art.

        Parameters
        ----------
        pixel_size: The current size of the pixels (e.g. "2" means  the pixels are 2x2).
        """
        await inter.response.defer()
        await self.downscale(inter, image.url, pixel_size)

    @commands.command(
        name="downscale",
        usage="<image|url> [pixel size]",
        description="Downscale an upscaled pixel art.",
        help="""
        - `<url|image>`: an image URL or an attached image
        - `[pixel size]`: The current size of the pixels (e.g. "2" means  the pixels are 2x2).
        """,
    )
    async def p_downscale(self, ctx, *args):
        args, urls = get_urls_from_list(args)
        pixel_size = args[0] if args else None
        url = urls[0] if urls else None
        async with ctx.typing():
            await self.downscale(ctx, url, pixel_size)

    async def downscale(self, ctx, url=None, pixel_size=None):
        # check on the pixel_size
        if pixel_size is not None:
            err_msg = "The pixel size must be an integer greater than 1."
            try:
                pixel_size = int(pixel_size)
            except ValueError:
                return await ctx.send(f"❌ {err_msg}")
            if pixel_size < 2:
                return await ctx.send(f"❌ {err_msg}")

        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        input_image = remove_white_space(input_image)  # Remove extra space
        input_image_array = np.array(input_image)
        start = time.time()
        if pixel_size is None:
            scale = await self.bot.loop.run_in_executor(
                None, get_image_scale, input_image_array
            )
        else:
            scale = pixel_size

        if not scale or scale == 1:
            resize_command = (
                "/resize"
                if isinstance(ctx, disnake.AppCmdInter)
                else f"{ctx.prefix}resize"
            )
            msg = f"If your image is NOT a pixel art, use `{resize_command}` instead.\n\n"
            msg += "If it is, make sure that:\n"
            msg += "- The image doesn't have artifacts (it needs to be a good quality image)\n"
            msg += "- The image isn't already at its smallest possible scale\n"

            downscale_command = (
                "/downscale image:... pixel-size:..."
                if isinstance(ctx, disnake.AppCmdInter)
                else f"{ctx.prefix}downscale <image> <pixel size>"
            )
            msg += f"\n*Note: If you know the scale factor (how big each pixel is), you can try\n`{downscale_command}`*\n"

            error_embed = disnake.Embed(
                title=":x: **Couldn't downscale that image**",
                description=msg,
                color=0xFF3621,
            )
            return await ctx.send(embed=error_embed)

        true_width = input_image.width // scale
        downscaled_array = await self.bot.loop.run_in_executor(
            None, detemplatize, input_image_array, true_width
        )
        end = time.time()
        downscaled_image = Image.fromarray(downscaled_array)

        embed = disnake.Embed(title="Downscale", color=0x66C5CC)
        embed.description = "• Original pixel size: **{0}x{0}**\n".format(scale)
        embed.description += "• Image size: `{0.shape[1]}x{0.shape[0]}` → `{1.shape[1]}x{1.shape[0]}`\n".format(
            input_image_array, downscaled_array
        )
        embed.description += (
            f"• Pixels: `{format_number(get_visible_pixels(downscaled_image))}`"
        )
        embed.set_footer(text=f"Downscaled in {round((end - start), 3)}s")
        downscaled_file = await image_to_file(
            downscaled_image, "downscaled.png", embed=embed
        )
        await ctx.send(embed=embed, file=downscaled_file)

    @commands.slash_command(name="upscale")
    async def _upscale(self, inter: disnake.AppCmdInter, scale: int, image: InterImage):
        """Upscale an image to the desired scale.

        Parameters
        ----------
        scale: The new scale for the image (ex: 2 means the image will be 2x bigger).
        """
        await inter.response.defer()
        await self.upscale(inter, scale, image.url)

    @commands.command(
        name="upscale",
        usage="<scale> <image|url>",
        description="Upscale an image to the desired scale.",
        help="""- `scale`: the new scale for the image (ex: 2 means the image will be 2x bigger)
                - `<url|image>`: an image URL or an attached image""",
    )
    async def p_upscale(self, ctx, scale, url=None):
        async with ctx.typing():
            await self.upscale(ctx, scale, url)

    async def upscale(self, ctx, scale, url=None):
        # check on the scale
        err_msg = "The scale value must be an integer."
        try:
            scale = int(scale)
        except ValueError:
            return await ctx.send(f"❌ {err_msg}")
        if scale < 1:
            return await ctx.send(f"❌ {err_msg}")

        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # check that the image won't be too big
        final_width = scale * input_image.width
        final_height = scale * input_image.height
        limit = 6000
        if final_width > limit or final_height > limit:
            err_msg = (
                "The resulting image would be too big with this scale ({}x{}).".format(
                    final_width, final_height
                )
            )
            return await ctx.send(f"❌ {err_msg}")

        res_image = input_image.resize((final_width, final_height), Image.NEAREST)

        embed = disnake.Embed(title="Upscale", color=0x66C5CC)
        embed.description = "• Final pixel size: **{0}x{0}**\n".format(scale)
        embed.description += (
            "• Image size: `{0.width}x{0.height}` → `{1.width}x{1.height}`\n".format(
                input_image, res_image
            )
        )
        embed.description += f"• Pixels: `{format_number(get_visible_pixels(res_image))}`"
        res_file = await image_to_file(res_image, "upscaled.png", embed=embed)
        await ctx.send(embed=embed, file=res_file)

    resamples = {
        "Nearest": Image.NEAREST,
        "Lanczos": Image.LANCZOS,
        "Bilinear": Image.BILINEAR,
        "Bicubic": Image.BICUBIC,
        "Box": Image.BOX,
        "Hamming": Image.HAMMING,
    }

    @commands.slash_command(name="resize")
    async def _resize(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage,
        width: int = 100,
        resample=commands.Param(choices=resamples.keys(), default="Nearest"),
    ):
        """Change an image's width.

        Parameters
        ----------
        width: The new width for the image.
        image: The URL of the image.
        resample: A resampling filter. (default: Nearest)
        """
        await inter.response.defer()
        await self.resize(inter, width, image.url, resample)

    @commands.command(
        name="resize",
        usage="<image|url> [width] [-resample ...]",
        description="Change an image's width.",
        help="""
            - `<url|image>`: an image URL or an attached image
            - `[width]`: the new width for the image (default: 100)
            - `[-resample nearest|lanczos|bilinear|bicubic|box|hamming]`: a resampling filter (default: nearest)""",
    )
    async def p_resize(self, ctx, *args):
        parser = MyParser(add_help=False)
        parser.add_argument("args", type=str, nargs="*")
        parser.add_argument(
            "-resample",
            choices=[r.lower() for r in self.resamples.keys()],
            default="Nearest",
            type=lambda s: s.lower(),
        )
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        texts, urls = get_urls_from_list(parsed_args.args)
        url = urls[0] if urls else None
        width = texts[0] if texts else 100
        async with ctx.typing():
            await self.resize(ctx, width, url, parsed_args.resample)

    async def resize(self, ctx, width, url=None, resample="Nearest"):
        # check on the resample
        if resample.title() not in self.resamples:
            return await ctx.send(f"Unknown resampling filter ({resample}).")
        resample_enum = self.resamples.get(resample.title())

        # check on the width
        def _check_width(width):
            err_msg = f"Invalid width `{width}`: The width must be a positive integer."
            try:
                width = int(width)
            except ValueError:
                raise ValueError(err_msg)
            if width <= 0:
                raise ValueError(err_msg)
            return width

        try:
            width = _check_width(width)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async def _resize(width):
            # checks on the width
            width = _check_width(width)
            limit = 7e6
            ratio = input_image.width / width
            new_height = int(input_image.height / ratio)
            if new_height * width > limit:
                err_msg = "The resulting image would be too big with this width ({} pixels, {}x{}).".format(
                    format_number(width * new_height),
                    format_number(width),
                    format_number(new_height),
                )
                raise ValueError(err_msg)

            # resize the input image
            res_image = input_image.resize((width, new_height), resample_enum)
            visible_pixels = get_visible_pixels(res_image)
            embed = disnake.Embed(title="Resize", color=0x66C5CC)
            embed.description = (
                "• Size: `{0.width}x{0.height}` → `{1.width}x{1.height}`\n".format(
                    input_image, res_image
                )
            )
            embed.description += "• Pixels: `{}`\n".format(format_number(visible_pixels))
            embed.description += "• Resample: `{}`".format(resample.title())

            res_file = await image_to_file(res_image, "resized.png", embed=embed)
            return embed, res_file

        try:
            embed, res_file = await _resize(width)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        view = ResizeView(ctx.author, width, _resize)
        view.message = await ctx.send(embed=embed, file=res_file, view=view)
        if isinstance(ctx, disnake.AppCmdInter):
            view.message = await ctx.original_message()

    @commands.slash_command(name="size")
    async def _size(self, inter: disnake.AppCmdInter, image: InterImage):
        """To quickly get the size of an image."""
        await inter.response.defer()
        await self.size(inter, image.url)

    @commands.command(
        name="size",
        usage="<image|url>",
        description="To quickly get the size of an image.",
        help="""`<url|image>`: an image URL or an attached image""",
    )
    async def p_size(self, ctx, url=None):
        async with ctx.typing():
            await self.size(ctx, url)

    async def size(self, ctx, url=None):
        # get the input image
        send_file = url and parse_template(url)
        try:
            image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        width = image.width
        height = image.height
        total_size = width * height
        total_visible = get_visible_pixels(image)
        image_colors = image.getcolors(total_size)
        image_colors = [c for c in image_colors if (len(c[1]) != 4 or c[1][3] > 128)]
        total_colors = len(image_colors)

        embed = disnake.Embed(title="Size", color=0x66C5CC)
        embed.description = f" • Visible pixels: `{format_number(total_visible)}`\n"
        embed.description += f" • Number of colors: `{format_number(total_colors)}`\n"
        embed.description += "• Size: `{} x {}` (`{}` pixels)".format(
            format_number(width),
            format_number(height),
            format_number(total_size),
        )
        if send_file:
            file = await image_to_file(image, "input.png")
            embed.set_thumbnail(url="attachment://input.png")
            await ctx.send(embed=embed, file=file)
        else:
            embed.set_thumbnail(url=url)
            await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Scale(bot))
