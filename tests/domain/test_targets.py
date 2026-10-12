"""Targets are values; fixtures are an extensible family."""
from pylumencache.domain.classify import fixture_for, fixture_type, register_model
from pylumencache.domain.commands import SetFixture
from pylumencache.domain.events import FixtureChanged
from pylumencache.domain.model import Device, SystemModel
from pylumencache.domain.targets import Fixture, Light, TunableLight, Zone
from pylumencache.transports.mqtt.adapter import to_message


def test_targets_are_equal_by_kind_and_key_not_by_class():
    assert Zone(5) == Zone(5) and Zone(5) != Fixture(5) and Zone(5) != 5
    assert Light(14) == Fixture(14) == TunableLight(14)
    assert len({Zone(5), Fixture(5), Zone(5), Light(5)}) == 2


def test_a_subclass_states_what_it_can_do():
    assert (Fixture.dimmable, Fixture.color_temperature) == (True, False)
    assert (Light.color_temperature, TunableLight.color_temperature) == (False, True)


def test_state_stored_for_one_class_is_found_through_another():
    m = SystemModel()
    m.apply(FixtureChanged(Light(14), on=True, brightness=40, source="event"))
    assert m.state(Fixture(14)).brightness == 40 and m.state(Zone(14)).brightness is None


def test_a_subclass_is_commanded_like_its_base():
    assert to_message(SetFixture(TunableLight(14), 50, 3000)) == to_message(SetFixture(Fixture(14), 50, 3000))


def test_devices_are_classified_by_card_model():
    def kind(name):
        return fixture_type(Device(gid=1, path="x", name=name))

    assert kind("SC-CC2") is TunableLight and kind("sc-pv2") is TunableLight
    assert kind("SC-CC2-50W") is TunableLight and kind("SC-PV2-50W") is TunableLight
    assert kind("SC-PV1-50W") is Light and kind("SC-PV22") is Fixture
    assert kind("SC-PV1") is Light
    assert kind("SC-CV1") is Fixture and kind("SC-PV4") is Fixture and kind(None) is Fixture
    assert fixture_for(Device(gid=7, path="x", name="SC-CC2")) == TunableLight(7)


def test_a_registered_model_wins():
    class Fan(Fixture):
        dimmable = False

    register_model(r"SC-FAN\d", Fan)
    try:
        assert fixture_type(Device(gid=1, path="x", name="SC-FAN1")) is Fan
    finally:
        from pylumencache.domain import classify
        classify._RULES.pop(0)
