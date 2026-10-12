"""Listeners: failures are contained, coroutines are run, removal is safe to repeat."""
import asyncio

from pylumencache.listeners import Listeners


def test_a_failing_listener_does_not_stop_the_others():
    listeners, seen = Listeners(), []

    def broken(_):
        raise RuntimeError("bad")

    listeners.add(broken)
    listeners.add(seen.append)
    listeners.call(1)
    assert seen == [1]


def test_removing_twice_is_harmless_and_one_registration_does_not_remove_another():
    listeners, seen = Listeners(), []
    first = listeners.add(seen.append)
    listeners.add(seen.append)   # the same callback again
    first()
    first()
    listeners.call(1)
    assert seen == [1] and len(listeners) == 1


def test_coroutine_listeners_are_run():
    async def scenario():
        listeners, seen = Listeners(), []

        async def later(value):
            seen.append(value)

        listeners.add(later)
        listeners.call(7)
        await asyncio.sleep(0)
        assert seen == [7]
    asyncio.run(scenario())


def test_a_failing_coroutine_listener_is_logged_not_raised(caplog):
    async def scenario():
        listeners = Listeners()

        async def broken(_):
            raise RuntimeError("bad")

        listeners.add(broken)
        listeners.call(1)
        await asyncio.sleep(0)
    asyncio.run(scenario())
    assert "An async listener raised an exception" in caplog.text
