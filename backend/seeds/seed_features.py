from backend.database.session import SessionLocal
from backend.models.feature import Feature
from backend.repositories.feature_repository import FeatureRepository


FEATURES = (
    ("wifi", "Wi-Fi", "property", "Conectividad", 10),
    ("lavadora", "Lavadora", "property", "Equipamiento común", 20),
    ("cocina-equipada", "Cocina equipada", "property", "Equipamiento común", 30),
    ("ascensor", "Ascensor", "property", "Edificio", 40),
    ("calefaccion", "Calefacción", "both", "Climatización", 50),
    ("aire-acondicionado", "Aire acondicionado", "room", "Climatización", 60),
    ("terraza", "Terraza", "property", "Zonas comunes", 70),
    ("salon", "Salón", "property", "Zonas comunes", 80),
    ("cama-individual", "Cama individual", "room", "Dormitorio", 90),
    ("cama-doble", "Cama doble", "room", "Dormitorio", 100),
    ("escritorio", "Escritorio", "room", "Mobiliario", 110),
    ("armario", "Armario", "room", "Mobiliario", 120),
    ("bano-privado", "Baño privado", "room", "Privado", 130),
    ("balcon", "Balcón", "room", "Privado", 140),
    ("ventana-exterior", "Ventana exterior", "room", "Dormitorio", 150),
)


def seed_features(db) -> int:
    repository = FeatureRepository(); created = 0
    try:
        for slug, name, scope, category, order in FEATURES:
            if repository.by_slug(db, slug) is None:
                db.add(Feature(slug=slug, name=name, scope=scope, category=category, display_order=order, active=True)); created += 1
        db.commit(); return created
    except Exception:
        db.rollback(); raise


if __name__ == "__main__":
    with SessionLocal() as session:
        print(f"Features creadas: {seed_features(session)}")
