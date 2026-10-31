"""The WAIT poll interval of the client simulator is configurable (default 1 s)."""
import inspect

from YSimulator.YClient.simulation import simulator as sim_mod


def test_default_is_one_second():
    param = inspect.signature(sim_mod.Simulator.__init__).parameters["barrier_poll_seconds"]
    assert param.default == 1.0


def test_wait_branch_uses_the_parameter():
    src = inspect.getsource(sim_mod.Simulator.run)
    assert "time.sleep(self.barrier_poll_seconds)" in src
    assert "time.sleep(1)" not in src


def test_client_reads_it_from_simulation_config():
    from YSimulator.YClient import client

    src = inspect.getsource(client)
    assert 'get("barrier_poll_seconds", 1.0)' in src
    assert "barrier_poll_seconds=self.barrier_poll_seconds" in src
