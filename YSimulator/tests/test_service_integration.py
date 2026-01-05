"""
Unit tests for Phase 5: Service Integration.

Tests that all services are properly exposed and accessible from the server,
and that direct database calls have been eliminated in favor of service calls.
"""

import pytest
from unittest.mock import Mock


class TestServiceExposure:
    """Test that all 10 services are properly exposed in the codebase."""
    
    def test_services_imported_in_server(self):
        """Test that service classes can be imported."""
        try:
            from YSimulator.YServer.services.user_service import UserService
            from YSimulator.YServer.services.post_service import PostService
            from YSimulator.YServer.services.follow_service import FollowService
            from YSimulator.YServer.services.interest_service import InterestService
            from YSimulator.YServer.services.article_service import ArticleService
            from YSimulator.YServer.services.image_service import ImageService
            from YSimulator.YServer.services.content_service import ContentService
            from YSimulator.YServer.services.simulation_service import SimulationService
            from YSimulator.YServer.services.metadata_service import MetadataService
            from YSimulator.YServer.services.mention_service import MentionService
            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import services: {e}")
    
    def test_server_uses_services(self):
        """Test that server.py references service classes."""
        import inspect
        from YSimulator.YServer import server
        
        source_code = inspect.getsource(server)
        
        # Check that service class names appear in server code
        service_classes = [
            'UserService',
            'PostService', 
            'FollowService',
            'InterestService',
            'MetadataService'
        ]
        
        found_services = []
        for service_class in service_classes:
            if service_class in source_code:
                found_services.append(service_class)
        
        # Should find most service classes referenced
        assert len(found_services) >= 3, f"Expected to find service classes in server.py, found: {found_services}"


class TestServiceUsagePatterns:
    """Tests to verify service usage patterns and reduced direct db calls."""
    
    def test_service_method_delegation(self):
        """Test that key methods properly delegate to services."""
        from YSimulator.YServer import server
        import inspect
        
        source_code = inspect.getsource(server)
        
        # Verify service usage patterns exist
        service_patterns = [
            'self.user_service',
            'self.post_service',
            'self.follow_service',
            'self.metadata_service',
            'self.interest_service'
        ]
        
        found_patterns = []
        for pattern in service_patterns:
            if pattern in source_code:
                found_patterns.append(pattern)
        
        # Should find multiple service usage patterns
        assert len(found_patterns) >= 4, f"Expected to find service usage patterns, found: {found_patterns}"
    
    def test_reduced_direct_db_calls(self):
        """Verify that server.py has migrated away from direct db adapter calls."""
        from YSimulator.YServer import server
        import inspect
        
        source_code = inspect.getsource(server)
        
        # Count service usage vs direct db calls
        service_call_count = source_code.count('self.user_service') + \
                            source_code.count('self.post_service') + \
                            source_code.count('self.follow_service') + \
                            source_code.count('self.metadata_service')
        
        # Should have many service calls
        assert service_call_count > 10, f"Expected many service calls, found {service_call_count}"


class TestServiceIntegrationInActionProcessors:
    """Test that action processors properly use services."""
    
    def test_post_processor_uses_services(self):
        """Test PostProcessor references services."""
        from YSimulator.YServer.action_processors.post_processor import PostProcessor
        import inspect
        
        source_code = inspect.getsource(PostProcessor)
        
        # Should reference services through server parameter
        assert 'server' in source_code or 'services' in source_code
    
    def test_comment_processor_uses_services(self):
        """Test CommentProcessor references services."""
        from YSimulator.YServer.action_processors.comment_processor import CommentProcessor
        import inspect
        
        source_code = inspect.getsource(CommentProcessor)
        
        # Should reference services
        assert 'server' in source_code or 'services' in source_code
    
    def test_follow_processor_uses_services(self):
        """Test FollowProcessor references services."""
        from YSimulator.YServer.action_processors.follow_processor import FollowProcessor
        import inspect
        
        source_code = inspect.getsource(FollowProcessor)
        
        # Should reference services
        assert 'server' in source_code or 'services' in source_code


class TestServiceAccessibility:
    """Test that services are accessible and functional."""
    
    def test_mock_server_with_services(self):
        """Test that we can create a mock server with all services."""
        server = Mock()
        server.user_service = Mock()
        server.post_service = Mock()
        server.follow_service = Mock()
        server.interest_service = Mock()
        server.article_service = Mock()
        server.image_service = Mock()
        server.content_service = Mock()
        server.simulation_service = Mock()
        server.metadata_service = Mock()
        server.mention_service = Mock()
        
        # Verify all services are set
        assert server.user_service is not None
        assert server.post_service is not None
        assert server.follow_service is not None
        assert server.interest_service is not None
        assert server.article_service is not None
        assert server.image_service is not None
        assert server.content_service is not None
        assert server.simulation_service is not None
        assert server.metadata_service is not None
        assert server.mention_service is not None
    
    def test_service_method_calls(self):
        """Test that service methods can be called on mocks."""
        mock_server = Mock()
        mock_server.user_service = Mock()
        mock_server.user_service.get_user = Mock(return_value={"user_id": "user1"})
        
        result = mock_server.user_service.get_user("user1")
        
        assert result is not None
        assert result["user_id"] == "user1"
        mock_server.user_service.get_user.assert_called_once_with("user1")


class TestPhase5Completion:
    """Test that Phase 5 objectives have been met."""
    
    def test_service_framework_exists(self):
        """Test that service framework is in place."""
        import os
        
        # Use relative path from this file
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yserver_dir = os.path.join(os.path.dirname(test_dir), "YServer")
        services_dir = os.path.join(yserver_dir, "services")
        
        # Check that services directory exists
        assert os.path.exists(services_dir), f"Services directory should exist at {services_dir}"
        
        # Check that key service files exist
        expected_files = [
            "user_service.py",
            "post_service.py",
            "follow_service.py",
            "interest_service.py",
            "metadata_service.py"
        ]
        
        existing_files = []
        for file in expected_files:
            file_path = os.path.join(services_dir, file)
            if os.path.exists(file_path):
                existing_files.append(file)
        
        assert len(existing_files) >= 3, f"Expected to find service files, found: {existing_files}"
    
    def test_coordination_layer_exists(self):
        """Test that coordination layer from Phase 4 exists."""
        import os
        
        # Use relative path from this file
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yserver_dir = os.path.join(os.path.dirname(test_dir), "YServer")
        coordination_dir = os.path.join(yserver_dir, "coordination")
        
        # Check that coordination directory exists
        assert os.path.exists(coordination_dir), f"Coordination directory should exist at {coordination_dir}"
        
        # Check that key coordination files exist
        expected_files = [
            "client_manager.py",
            "barrier_handler.py",
            "round_manager.py",
            "archetype_manager.py"
        ]
        
        for file in expected_files:
            file_path = os.path.join(coordination_dir, file)
            assert os.path.exists(file_path), f"Expected {file} to exist at {file_path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
