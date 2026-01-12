"""Load balancing tests."""

import pytest
from roadgateway_core.loadbalancing.balancer import (
    RoundRobinBalancer,
    WeightedRoundRobinBalancer,
    LeastConnectionsBalancer,
    BackendServer,
)


class TestRoundRobinBalancer:
    """Test round-robin balancer."""

    def test_round_robin_selection(self):
        """Test round-robin selection."""
        balancer = RoundRobinBalancer()
        balancer.add_server(BackendServer("server1", 8080))
        balancer.add_server(BackendServer("server2", 8080))

        # Should cycle through servers
        s1 = balancer.select()
        s2 = balancer.select()
        s3 = balancer.select()

        assert s1.host == "server1"
        assert s2.host == "server2"
        assert s3.host == "server1"

    def test_empty_balancer(self):
        """Test empty balancer returns None."""
        balancer = RoundRobinBalancer()
        assert balancer.select() is None


class TestLeastConnectionsBalancer:
    """Test least connections balancer."""

    def test_selects_least_connections(self):
        """Test selecting server with least connections."""
        balancer = LeastConnectionsBalancer()
        
        s1 = BackendServer("server1", 8080)
        s1.active_connections = 10
        
        s2 = BackendServer("server2", 8080)
        s2.active_connections = 5
        
        balancer.add_server(s1)
        balancer.add_server(s2)

        selected = balancer.select()
        assert selected.host == "server2"
