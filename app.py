import asyncio
import httpx
from pathlib import Path
from enum import Enum
import datetime
import aiofiles
import time
import logging
import io
from PIL import Image, ImageDraw, ImageFont


logging.basicConfig(level=logging.WARNING)
_LOGGER = logging.getLogger(__name__)
_LOGGER.level = logging.INFO


class Area(Enum):
    Austria = "at"
    France = "fr"
    Germany = "de"
    GreatBritain = "gb"
    Italy = "it"
    Latvia = "lv"
    Lithuania = "lt"
    Poland = "pl"
    Spain = "es"
    Sweden = "se"
    Switzerland = "ch"
    Turkey = "tr"
    Ukrain = "ua"


class AllergyType(Enum):
    AllergyRisk = "ar"
    Mugwort = "ARTE"
    Birch = "BETU"
    Alder = "ALNU"
    Grasses = "POAC"
    Olive = "OLEA"
    Ragweed = "AMBR"


class PollenInfoClient:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url="https://edi.polleninfo.org")

    async def get_data(
        self, type: AllergyType, area: Area, day: int = 0, lang: str = "en"
    ) -> bytes:
        assert 0 <= day <= 2, "only day between is supported"
        result = await self.client.get(
            "/dex/rest/geo/map",
            params={
                "type": type.value,
                "area": area.value,
                "day": day,
                "lang": lang,
            },
        )
        return result.content


class ImageCollection:
    def __init__(self, base_path: str = "collected-data"):
        self.base_path: Path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def draw_on_image(self, type: AllergyType, now: datetime.datetime, content: bytes) -> bytes:
        # Open image from bytes
        image = Image.open(io.BytesIO(content)).convert("RGBA")
        draw = ImageDraw.Draw(image)
        text = f"{now.strftime('%Y-%m-%d')} {type.name}"

        # Load default font
        font = ImageFont.load_default()

        # Position for text
        x, y = 10, 10

        # Draw translucent background shading behind text
        bbox = font.getbbox(text)
        padding = 4
        draw.rounded_rectangle(
            (x - bbox[0] - padding, y - bbox[1] - padding, x + bbox[2] + padding, y + bbox[3] + padding),
            radius=3,
            fill=(255, 255, 255, 1)
        )
        image.alpha_composite(image, )

        # Draw main text
        draw.text((x, y), text, font=font, fill=(255,255,255,255))

        # Save modified image to bytes
        output = io.BytesIO()
        image.save(output, format="PNG")

        return output.getvalue()        

    async def save_image(self, content: bytes, type: AllergyType, area: Area):
        now = datetime.datetime.now()
        folder = self.base_path / type.name / area.name / str(now.year) / str(now.month)
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / f"{now.day}.png"
        image_bytes = self.draw_on_image(type, now, content)
        async with aiofiles.open(file, "wb") as f:
            await f.write(image_bytes)


class Collector:
    def __init__(
        self,
        areas: list[Area],
        types: list[AllergyType],
        base_path: str = "collected-data",
    ):
        self.pollen_info_client = PollenInfoClient()
        self.image_collection = ImageCollection(base_path=base_path)
        self.areas = areas
        self.types = types

    async def run(self):
        _LOGGER.info("Started")
        while True:
            try:
                execution_time = await self._run_step()
                _LOGGER.info("Successfully fetched todays data")
            except Exception as e:
                _LOGGER.warning(f"Got error while executing step: {e}")
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(24 * 60 * 60 - execution_time)

    async def _run_step(self) -> float:
        cur_time = time.time()
        for area in self.areas:
            for type in self.types:
                try:
                    content = await self.pollen_info_client.get_data(type=type, area=area)
                    await self.image_collection.save_image(
                        content=content, type=type, area=area
                    )
                except Exception as e:
                    _LOGGER.warning(f"Got error while running for type='{type}' and area='{area}': {e}")

                await asyncio.sleep(5)

        return time.time() - cur_time


if __name__ == "__main__":
    collector = Collector(
        areas=list(Area),
        types=list(AllergyType),
        base_path="keker",
    )
    asyncio.new_event_loop().run_until_complete(
        collector.run(),
    )
