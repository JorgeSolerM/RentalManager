from sqlalchemy import select

from backend.database.session import SessionLocal
from backend.models.platform import Platform
from backend.core.platform_favicons import PLATFORM_FAVICONS


PLATFORMS = [

    {
        "name": "Manual",
        "slug": "manual",
        "supports_import": False,
        "supports_export": False,
    },

    {
        "name": "HousingAnywhere",
        "slug": "housinganywhere",
        "supports_import": True,
        "supports_export": True,
    },

    {
        "name": "Flatio",
        "slug": "flatio",
        "supports_import": True,
        "supports_export": True,
    },

    {
        "name": "Spotahome",
        "slug": "spotahome",
        "supports_import": True,
        "supports_export": True,
    },

    {
        "name": "Uniplaces",
        "slug": "uniplaces",
        "supports_import": True,
        "supports_export": False,
    },

    {
        "name": "Homyspace",
        "slug": "homyspace",
        "supports_import": True,
        "supports_export": False,
    },

]


def seed_platforms():

    db = SessionLocal()

    try:

        for item in PLATFORMS:

            existing = db.scalar(

                select(Platform).where(
                    Platform.slug == item["slug"]
                )

            )

            if existing:

                continue

            db.add(

                Platform(

                    name=item["name"],

                    slug=item["slug"],

                    favicon=PLATFORM_FAVICONS.get(item["slug"]),

                    supports_import=item["supports_import"],

                    supports_export=item["supports_export"],

                    active=True,

                )

            )

        db.commit()

    finally:

        db.close()


if __name__ == "__main__":

    seed_platforms()

    print("Plataformas creadas correctamente.")
