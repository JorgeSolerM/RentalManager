from backend.models.feature import Feature
from backend.models.property import Property
from backend.seeds.seed_features import FEATURES, seed_features
from backend.services.feature_service import FeatureService


def test_seed_is_idempotent(db_session):
    assert seed_features(db_session) == len(FEATURES)
    assert seed_features(db_session) == 0
    assert db_session.query(Feature).count() == len(FEATURES)
    scopes = {feature.slug: feature.scope for feature in db_session.query(Feature).all()}
    assert scopes["wifi"] == "property"
    assert scopes["aire-acondicionado"] == "room"


def test_feature_catalog_create_update_and_in_use_delete_policy(db_session):
    service = FeatureService()
    result = service.save(db_session, None, name="Wi-Fi", slug="wifi", scope="both", category="Conectividad", icon_key="wifi", display_order=1, active=True)
    assert result.success
    feature = result.data
    assert service.save(db_session, feature.id, name="Wifi", slug="wifi", scope="both", category="Conectividad", icon_key=None, display_order=2, active=False).success
    prop = Property(name="P", address="A", city="C", owner="O", active=True, features=[feature])
    db_session.add(prop); db_session.commit()
    assert service.delete(db_session, feature.id).message == "feature_in_use"
    prop.features.clear(); db_session.commit()
    assert service.delete(db_session, feature.id).success


def test_feature_validation_and_duplicate_slug(db_session):
    service = FeatureService()
    assert service.save(db_session, None, name="X", slug="Bad Slug", scope="room", category="C", icon_key=None, display_order=0, active=True).message == "feature_invalid"
    assert service.save(db_session, None, name="X", slug="x", scope="room", category="C", icon_key=None, display_order=0, active=True).success
    assert service.save(db_session, None, name="Y", slug="x", scope="property", category="C", icon_key=None, display_order=0, active=True).message == "feature_slug_exists"
