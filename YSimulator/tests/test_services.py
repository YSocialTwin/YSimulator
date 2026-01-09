"""
Tests for service layer implementations.

This test suite validates the service layer that coordinates
between multiple repositories to implement business logic.
"""

import pytest
from unittest.mock import Mock, MagicMock

from YSimulator.YServer.services.user_service import UserService
from YSimulator.YServer.services.post_service import PostService
from YSimulator.YServer.services.recommendation_service import RecommendationService
from YSimulator.YServer.services.article_service import ArticleService
from YSimulator.YServer.services.image_service import ImageService


# ============================================================================
# UserService Tests
# ============================================================================


class TestUserService:
    """Test suite for UserService."""

    @pytest.fixture
    def mock_user_repo(self):
        """Create a mock UserRepository."""
        return Mock()

    @pytest.fixture
    def mock_interest_repo(self):
        """Create a mock InterestRepository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_user_repo, mock_interest_repo):
        """Create a UserService instance."""
        return UserService(mock_user_repo, mock_interest_repo)

    def test_register_user_success(self, service, mock_user_repo):
        """Test successful user registration."""
        user_data = {"id": "user1", "username": "testuser"}
        mock_user_repo.register_user.return_value = True

        result = service.register_user(user_data)

        assert result is True
        mock_user_repo.register_user.assert_called_once_with(user_data)

    def test_register_user_failure(self, service, mock_user_repo):
        """Test user registration failure."""
        user_data = {"id": "user1", "username": "testuser"}
        mock_user_repo.register_user.return_value = False

        result = service.register_user(user_data)

        assert result is False
        mock_user_repo.register_user.assert_called_once_with(user_data)

    def test_register_users_batch(self, service, mock_user_repo):
        """Test batch user registration."""
        users_data = [
            {"id": "user1", "username": "user1"},
            {"id": "user2", "username": "user2"},
        ]
        mock_user_repo.register_users_batch.return_value = (2, {"user1", "user2"})

        count, ids = service.register_users_batch(users_data)

        assert count == 2
        assert len(ids) == 2
        mock_user_repo.register_users_batch.assert_called_once_with(users_data)

    def test_get_user_success(self, service, mock_user_repo):
        """Test getting a user."""
        user_id = "user1"
        expected_user = {"id": user_id, "username": "testuser"}
        mock_user_repo.get_user.return_value = expected_user

        result = service.get_user(user_id)

        assert result == expected_user
        mock_user_repo.get_user.assert_called_once_with(user_id)

    def test_get_user_not_found(self, service, mock_user_repo):
        """Test getting a non-existent user."""
        mock_user_repo.get_user.return_value = None

        result = service.get_user("nonexistent")

        assert result is None

    def test_get_all_users(self, service, mock_user_repo):
        """Test getting all users."""
        expected_users = [
            {"id": "user1", "username": "user1"},
            {"id": "user2", "username": "user2"},
        ]
        mock_user_repo.get_all_users.return_value = expected_users

        result = service.get_all_users()

        assert result == expected_users
        assert len(result) == 2

    def test_update_user_archetype(self, service, mock_user_repo):
        """Test updating user archetype."""
        user_id = "user1"
        new_archetype = "updated"
        mock_user_repo.update_user_archetype.return_value = True

        result = service.update_user_archetype(user_id, new_archetype)

        assert result is True
        mock_user_repo.update_user_archetype.assert_called_once_with(user_id, new_archetype)

    def test_get_user_interests(self, service, mock_interest_repo):
        """Test getting user interests."""
        user_id = "user1"
        start_round = 1
        end_round = 10
        expected_interests = ["interest1", "interest2"]
        mock_interest_repo.get_user_interests_in_window.return_value = expected_interests

        result = service.get_user_interests(user_id, start_round, end_round)

        assert result == expected_interests
        mock_interest_repo.get_user_interests_in_window.assert_called_once_with(
            user_id, start_round, end_round
        )

    def test_get_user_interests_no_repo(self, mock_user_repo):
        """Test getting user interests without interest repository."""
        service = UserService(mock_user_repo, interest_repository=None)

        result = service.get_user_interests("user1", 1, 10)

        assert result == []

    def test_add_user_interest(self, service, mock_interest_repo):
        """Test adding user interest."""
        user_id = "user1"
        interest_id = "interest1"
        round_id = "round1"
        mock_interest_repo.add_user_interest.return_value = True

        result = service.add_user_interest(user_id, interest_id, round_id)

        assert result is True
        mock_interest_repo.add_user_interest.assert_called_once_with(user_id, interest_id, round_id)

    def test_health_check(self, service, mock_user_repo):
        """Test health check."""
        mock_user_repo.health_check.return_value = True

        result = service.health_check()

        assert result is True
        mock_user_repo.health_check.assert_called_once()


# ============================================================================
# PostService Tests
# ============================================================================


class TestPostService:
    """Test suite for PostService."""

    @pytest.fixture
    def mock_post_repo(self):
        """Create a mock PostRepository."""
        return Mock()

    @pytest.fixture
    def mock_interest_repo(self):
        """Create a mock InterestRepository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_post_repo, mock_interest_repo):
        """Create a PostService instance."""
        return PostService(mock_post_repo, mock_interest_repo)

    def test_create_post_success(self, service, mock_post_repo):
        """Test creating a post."""
        post_data = {"id": "post1", "author": "user1", "text": "Test"}
        mock_post_repo.add_post.return_value = "post1"

        result = service.create_post(post_data)

        assert result == "post1"
        mock_post_repo.add_post.assert_called_once_with(post_data)

    def test_create_post_failure(self, service, mock_post_repo):
        """Test post creation failure."""
        post_data = {"id": "post1", "author": "user1", "text": "Test"}
        mock_post_repo.add_post.return_value = None

        result = service.create_post(post_data)

        assert result is None

    def test_get_post_success(self, service, mock_post_repo):
        """Test getting a post."""
        post_id = "post1"
        expected_post = {"id": post_id, "author": "user1", "text": "Test"}
        mock_post_repo.get_post.return_value = expected_post

        result = service.get_post(post_id)

        assert result == expected_post
        mock_post_repo.get_post.assert_called_once_with(post_id)

    def test_get_recent_posts(self, service, mock_post_repo):
        """Test getting recent posts."""
        expected_posts = ["post1", "post2", "post3"]
        mock_post_repo.get_recent_posts.return_value = expected_posts

        result = service.get_recent_posts(limit=3)

        assert result == expected_posts
        mock_post_repo.get_recent_posts.assert_called_once_with(3)

    def test_get_thread_context(self, service, mock_post_repo):
        """Test getting thread context."""
        post_id = "post1"
        expected_thread = [
            {"id": "post0", "text": "Root"},
            {"id": "post1", "text": "Reply"},
        ]
        mock_post_repo.get_thread_context.return_value = expected_thread

        result = service.get_thread_context(post_id, max_length=5)

        assert result == expected_thread
        mock_post_repo.get_thread_context.assert_called_once_with(post_id, 5)

    def test_add_reaction_success(self, service, mock_post_repo):
        """Test adding a reaction."""
        interaction_data = {"id": "reaction1", "post_id": "post1", "user_id": "user1"}
        mock_post_repo.add_interaction.return_value = True
        mock_post_repo.increment_post_reaction_count.return_value = True

        result = service.add_reaction(interaction_data)

        assert result is True
        mock_post_repo.add_interaction.assert_called_once_with(interaction_data)
        mock_post_repo.increment_post_reaction_count.assert_called_once_with("post1")

    def test_add_reaction_failure(self, service, mock_post_repo):
        """Test reaction addition failure."""
        interaction_data = {"id": "reaction1", "post_id": "post1"}
        mock_post_repo.add_interaction.return_value = False

        result = service.add_reaction(interaction_data)

        assert result is False
        mock_post_repo.increment_post_reaction_count.assert_not_called()

    def test_add_post_topic(self, service, mock_post_repo):
        """Test adding a post topic."""
        post_id = "post1"
        topic_id = "topic1"
        mock_post_repo.add_post_topic.return_value = True

        result = service.add_post_topic(post_id, topic_id)

        assert result is True
        mock_post_repo.add_post_topic.assert_called_once_with(post_id, topic_id)

    def test_get_post_topics(self, service, mock_post_repo):
        """Test getting post topics."""
        post_id = "post1"
        expected_topics = ["topic1", "topic2"]
        mock_post_repo.get_post_topics.return_value = expected_topics

        result = service.get_post_topics(post_id)

        assert result == expected_topics
        mock_post_repo.get_post_topics.assert_called_once_with(post_id)

    def test_search_posts_by_topic(self, service, mock_post_repo):
        """Test searching posts by topic."""
        topic_id = "topic1"
        agent_id = "user1"
        expected_posts = ["post1", "post2"]
        mock_post_repo.search_posts_by_topic.return_value = expected_posts

        result = service.search_posts_by_topic(topic_id, agent_id, limit=10)

        assert result == expected_posts
        mock_post_repo.search_posts_by_topic.assert_called_once_with(topic_id, agent_id, 10)

    def test_get_topic_by_name(self, service, mock_interest_repo):
        """Test getting topic by name."""
        topic_name = "politics"
        topic_id = "topic1"
        mock_interest_repo.get_topic_id_by_name.return_value = topic_id

        result = service.get_topic_by_name(topic_name)

        assert result == topic_id
        mock_interest_repo.get_topic_id_by_name.assert_called_once_with(topic_name)

    def test_add_or_get_topic(self, service, mock_interest_repo):
        """Test adding or getting a topic."""
        topic_name = "politics"
        topic_id = "topic1"
        mock_interest_repo.add_or_get_interest.return_value = topic_id

        result = service.add_or_get_topic(topic_name)

        assert result == topic_id
        mock_interest_repo.add_or_get_interest.assert_called_once_with(topic_name)

    def test_health_check(self, service, mock_post_repo):
        """Test health check."""
        mock_post_repo.health_check.return_value = True

        result = service.health_check()

        assert result is True
        mock_post_repo.health_check.assert_called_once()


# ============================================================================
# RecommendationService Tests
# ============================================================================


class TestRecommendationService:
    """Test suite for RecommendationService."""

    @pytest.fixture
    def mock_rec_repo(self):
        """Create a mock RecommendationRepository."""
        return Mock()

    @pytest.fixture
    def mock_follow_repo(self):
        """Create a mock FollowRepository."""
        return Mock()

    @pytest.fixture
    def mock_interest_repo(self):
        """Create a mock InterestRepository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_rec_repo, mock_follow_repo, mock_interest_repo):
        """Create a RecommendationService instance."""
        return RecommendationService(
            mock_rec_repo,
            follow_repository=mock_follow_repo,
            interest_repository=mock_interest_repo,
        )

    def test_get_or_create_round(self, service, mock_rec_repo):
        """Test getting or creating a round."""
        day = 1
        hour = 10
        round_id = "round1"
        mock_rec_repo.get_or_create_round.return_value = round_id

        result = service.get_or_create_round(day, hour)

        assert result == round_id
        mock_rec_repo.get_or_create_round.assert_called_once_with(day, hour)

    def test_add_follow_relationship(self, service, mock_follow_repo):
        """Test adding a follow relationship."""
        follower_id = "user1"
        followee_id = "user2"
        mock_follow_repo.add_follow.return_value = True

        result = service.add_follow_relationship(follower_id, followee_id)

        assert result is True
        mock_follow_repo.add_follow.assert_called_once()
        call_args = mock_follow_repo.add_follow.call_args[0][0]
        assert call_args["follower_id"] == follower_id
        assert call_args["followee_id"] == followee_id

    def test_add_follow_relationship_no_repo(self, mock_rec_repo):
        """Test adding follow relationship without follow repository."""
        service = RecommendationService(mock_rec_repo, follow_repository=None)

        result = service.add_follow_relationship("user1", "user2")

        assert result is False

    def test_add_follows_batch(self, service, mock_follow_repo):
        """Test batch adding follow relationships."""
        follows_data = [
            {"follower_id": "user1", "followee_id": "user2"},
            {"follower_id": "user1", "followee_id": "user3"},
        ]
        mock_follow_repo.add_follows_batch.return_value = 2

        result = service.add_follows_batch(follows_data)

        assert result == 2
        mock_follow_repo.add_follows_batch.assert_called_once_with(follows_data)

    def test_add_agent_opinion(self, service, mock_interest_repo):
        """Test adding an agent opinion."""
        agent_id = "agent1"
        topic_id = "topic1"
        opinion = 0.8
        round_id = "round1"
        mock_interest_repo.add_agent_opinion.return_value = True

        result = service.add_agent_opinion(agent_id, topic_id, opinion, round_id)

        assert result is True
        mock_interest_repo.add_agent_opinion.assert_called_once_with(
            agent_id, topic_id, opinion, round_id
        )

    def test_get_latest_agent_opinion(self, service, mock_interest_repo):
        """Test getting latest agent opinion."""
        agent_id = "agent1"
        topic_id = "topic1"
        expected_opinion = 0.8
        mock_interest_repo.get_latest_agent_opinion.return_value = expected_opinion

        result = service.get_latest_agent_opinion(agent_id, topic_id)

        assert result == expected_opinion
        mock_interest_repo.get_latest_agent_opinion.assert_called_once_with(agent_id, topic_id)

    def test_cleanup_old_data(self, service, mock_rec_repo):
        """Test cleaning up old data."""
        current_day = 5
        current_slot = 10
        expected_result = {"status": "success", "deleted": 100}
        mock_rec_repo.cleanup_old_posts_from_redis.return_value = expected_result

        result = service.cleanup_old_data(current_day, current_slot)

        assert result == expected_result
        mock_rec_repo.cleanup_old_posts_from_redis.assert_called_once_with(
            current_day, current_slot
        )

    def test_consolidate_data(self, service, mock_rec_repo):
        """Test consolidating data."""
        day = 5
        expected_result = {"status": "success", "records": 1000}
        mock_rec_repo.consolidate_redis_to_sqlite.return_value = expected_result

        result = service.consolidate_data(day)

        assert result == expected_result
        mock_rec_repo.consolidate_redis_to_sqlite.assert_called_once_with(day)

    def test_health_check_all_healthy(
        self, service, mock_rec_repo, mock_follow_repo, mock_interest_repo
    ):
        """Test health check when all repositories are healthy."""
        mock_rec_repo.health_check.return_value = True
        mock_follow_repo.health_check.return_value = True
        mock_interest_repo.health_check.return_value = True

        result = service.health_check()

        assert result["recommendation"] is True
        assert result["follow"] is True
        assert result["interest"] is True

    def test_health_check_partial(
        self, service, mock_rec_repo, mock_follow_repo, mock_interest_repo
    ):
        """Test health check with some repositories unhealthy."""
        mock_rec_repo.health_check.return_value = True
        mock_follow_repo.health_check.return_value = False
        mock_interest_repo.health_check.return_value = True

        result = service.health_check()

        assert result["recommendation"] is True
        assert result["follow"] is False
        assert result["interest"] is True


# ============================================================================
# ArticleService Tests
# ============================================================================


class TestArticleService:
    """Test suite for ArticleService."""

    @pytest.fixture
    def mock_article_repo(self):
        """Create a mock ArticleRepository."""
        return Mock()

    @pytest.fixture
    def mock_interest_repo(self):
        """Create a mock InterestRepository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_article_repo, mock_interest_repo):
        """Create an ArticleService instance."""
        return ArticleService(mock_article_repo, mock_interest_repo)

    @pytest.fixture
    def service_no_interest_repo(self, mock_article_repo):
        """Create an ArticleService instance without interest repository."""
        return ArticleService(mock_article_repo, interest_repository=None)

    def test_add_website_success(self, service, mock_article_repo):
        """Test successful website addition."""
        website_data = {
            "id": "website1",
            "name": "Example Website",
            "rss": "https://example.com/rss",
        }
        expected_id = "website1"
        mock_article_repo.add_website.return_value = expected_id

        result = service.add_website(website_data)

        assert result == expected_id
        mock_article_repo.add_website.assert_called_once_with(website_data)

    def test_add_website_failure(self, service, mock_article_repo):
        """Test website addition failure."""
        website_data = {"name": "Example Website"}
        mock_article_repo.add_website.return_value = None

        result = service.add_website(website_data)

        assert result is None
        mock_article_repo.add_website.assert_called_once_with(website_data)

    def test_add_website_exception(self, service, mock_article_repo):
        """Test website addition with exception."""
        website_data = {"name": "Example Website"}
        mock_article_repo.add_website.side_effect = Exception("Database error")

        result = service.add_website(website_data)

        assert result is None

    def test_add_websites_batch_success(self, service, mock_article_repo):
        """Test successful batch website addition."""
        websites_data = [
            {"id": "website1", "name": "Website 1", "rss": "https://example1.com/rss"},
            {"id": "website2", "name": "Website 2", "rss": "https://example2.com/rss"},
        ]
        mock_article_repo.add_websites_batch.return_value = 2

        result = service.add_websites_batch(websites_data)

        assert result == 2
        mock_article_repo.add_websites_batch.assert_called_once_with(websites_data)

    def test_add_websites_batch_exception(self, service, mock_article_repo):
        """Test batch website addition with exception."""
        websites_data = [{"name": "Website 1"}]
        mock_article_repo.add_websites_batch.side_effect = Exception("Database error")

        result = service.add_websites_batch(websites_data)

        assert result == 0

    def test_add_article_success(self, service, mock_article_repo):
        """Test successful article addition."""
        article_data = {
            "id": "article1",
            "title": "Test Article",
            "content": "Article content",
            "website_id": "website1",
        }
        expected_id = "article1"
        mock_article_repo.add_article.return_value = expected_id

        result = service.add_article(article_data)

        assert result == expected_id
        mock_article_repo.add_article.assert_called_once_with(article_data)

    def test_add_article_failure(self, service, mock_article_repo):
        """Test article addition failure."""
        article_data = {"title": "Test Article"}
        mock_article_repo.add_article.return_value = None

        result = service.add_article(article_data)

        assert result is None

    def test_add_article_exception(self, service, mock_article_repo):
        """Test article addition with exception."""
        article_data = {"title": "Test Article"}
        mock_article_repo.add_article.side_effect = Exception("Database error")

        result = service.add_article(article_data)

        assert result is None

    def test_get_article_success(self, service, mock_article_repo):
        """Test getting an article."""
        article_id = "article1"
        expected_article = {"id": article_id, "title": "Test Article", "content": "Article content"}
        mock_article_repo.get_article.return_value = expected_article

        result = service.get_article(article_id)

        assert result == expected_article
        mock_article_repo.get_article.assert_called_once_with(article_id)

    def test_get_article_not_found(self, service, mock_article_repo):
        """Test getting a non-existent article."""
        mock_article_repo.get_article.return_value = None

        result = service.get_article("nonexistent")

        assert result is None

    def test_get_article_exception(self, service, mock_article_repo):
        """Test get article with exception."""
        mock_article_repo.get_article.side_effect = Exception("Database error")

        result = service.get_article("article1")

        assert result is None

    def test_get_website_by_rss_success(self, service, mock_article_repo):
        """Test getting a website by RSS URL."""
        rss_url = "https://example.com/rss"
        expected_website = {"id": "website1", "name": "Example Website", "rss": rss_url}
        mock_article_repo.get_website_by_rss.return_value = expected_website

        result = service.get_website_by_rss(rss_url)

        assert result == expected_website
        mock_article_repo.get_website_by_rss.assert_called_once_with(rss_url)

    def test_get_website_by_rss_not_found(self, service, mock_article_repo):
        """Test getting a non-existent website by RSS."""
        mock_article_repo.get_website_by_rss.return_value = None

        result = service.get_website_by_rss("https://nonexistent.com/rss")

        assert result is None

    def test_get_website_by_rss_exception(self, service, mock_article_repo):
        """Test get website by RSS with exception."""
        mock_article_repo.get_website_by_rss.side_effect = Exception("Database error")

        result = service.get_website_by_rss("https://example.com/rss")

        assert result is None

    def test_get_article_topics_success(self, service, mock_article_repo):
        """Test getting article topics."""
        article_id = "article1"
        expected_topics = ["topic1", "topic2", "topic3"]
        mock_article_repo.get_article_topics.return_value = expected_topics

        result = service.get_article_topics(article_id)

        assert result == expected_topics
        mock_article_repo.get_article_topics.assert_called_once_with(article_id)

    def test_get_article_topics_empty(self, service, mock_article_repo):
        """Test getting article topics with no topics."""
        mock_article_repo.get_article_topics.return_value = []

        result = service.get_article_topics("article1")

        assert result == []

    def test_get_article_topics_exception(self, service, mock_article_repo):
        """Test get article topics with exception."""
        mock_article_repo.get_article_topics.side_effect = Exception("Database error")

        result = service.get_article_topics("article1")

        assert result == []

    def test_get_article_with_topics_success(self, service, mock_article_repo, mock_interest_repo):
        """Test getting an article with topic names."""
        article_id = "article1"
        article_data = {"id": article_id, "title": "Test Article", "content": "Article content"}
        topic_ids = ["topic1", "topic2"]

        mock_article_repo.get_article.return_value = article_data
        mock_article_repo.get_article_topics.return_value = topic_ids
        mock_interest_repo.get_topic_name_from_id.side_effect = ["Technology", "Science"]

        result = service.get_article_with_topics(article_id)

        assert result is not None
        assert result["id"] == article_id
        assert "topics" in result
        assert result["topics"] == ["Technology", "Science"]
        mock_article_repo.get_article.assert_called_once_with(article_id)
        mock_article_repo.get_article_topics.assert_called_once_with(article_id)

    def test_get_article_with_topics_not_found(self, service, mock_article_repo):
        """Test getting a non-existent article with topics."""
        mock_article_repo.get_article.return_value = None

        result = service.get_article_with_topics("nonexistent")

        assert result is None
        mock_article_repo.get_article.assert_called_once_with("nonexistent")
        mock_article_repo.get_article_topics.assert_not_called()

    def test_get_article_with_topics_no_interest_repo(
        self, service_no_interest_repo, mock_article_repo
    ):
        """Test getting article with topics when no interest repo available."""
        article_id = "article1"
        article_data = {"id": article_id, "title": "Test Article", "content": "Article content"}
        mock_article_repo.get_article.return_value = article_data

        result = service_no_interest_repo.get_article_with_topics(article_id)

        assert result is not None
        assert result["id"] == article_id
        assert "topics" not in result
        mock_article_repo.get_article.assert_called_once_with(article_id)

    def test_get_article_with_topics_exception(self, service, mock_article_repo):
        """Test get article with topics with exception."""
        mock_article_repo.get_article.side_effect = Exception("Database error")

        result = service.get_article_with_topics("article1")

        assert result is None

    def test_health_check_success(self, service, mock_article_repo):
        """Test health check success."""
        mock_article_repo.health_check.return_value = True

        result = service.health_check()

        assert result is True
        mock_article_repo.health_check.assert_called_once()

    def test_health_check_failure(self, service, mock_article_repo):
        """Test health check failure."""
        mock_article_repo.health_check.return_value = False

        result = service.health_check()

        assert result is False

    def test_health_check_exception(self, service, mock_article_repo):
        """Test health check with exception."""
        mock_article_repo.health_check.side_effect = Exception("Connection error")

        result = service.health_check()

        assert result is False


# ============================================================================
# ImageService Tests
# ============================================================================


class TestImageService:
    """Test suite for ImageService."""

    @pytest.fixture
    def mock_image_repo(self):
        """Create a mock ImageRepository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_image_repo):
        """Create an ImageService instance."""
        return ImageService(mock_image_repo)

    def test_add_image_success(self, service, mock_image_repo):
        """Test successful image addition."""
        image_data = {
            "id": "image1",
            "url": "https://example.com/image.jpg",
            "description": "Test image",
        }
        expected_id = "image1"
        mock_image_repo.add_image.return_value = expected_id

        result = service.add_image(image_data)

        assert result == expected_id
        mock_image_repo.add_image.assert_called_once_with(image_data)

    def test_add_image_failure(self, service, mock_image_repo):
        """Test image addition failure."""
        image_data = {"url": "https://example.com/image.jpg"}
        mock_image_repo.add_image.return_value = None

        result = service.add_image(image_data)

        assert result is None
        mock_image_repo.add_image.assert_called_once_with(image_data)

    def test_add_image_exception(self, service, mock_image_repo):
        """Test image addition with exception."""
        image_data = {"url": "https://example.com/image.jpg"}
        mock_image_repo.add_image.side_effect = Exception("Database error")

        result = service.add_image(image_data)

        assert result is None

    def test_get_random_image_success(self, service, mock_image_repo):
        """Test getting a random image."""
        expected_image = {
            "id": "image1",
            "url": "https://example.com/image.jpg",
            "description": "Random image",
        }
        mock_image_repo.get_random_image.return_value = expected_image

        result = service.get_random_image()

        assert result == expected_image
        mock_image_repo.get_random_image.assert_called_once()

    def test_get_random_image_not_found(self, service, mock_image_repo):
        """Test getting a random image when none available."""
        mock_image_repo.get_random_image.return_value = None

        result = service.get_random_image()

        assert result is None

    def test_get_random_image_exception(self, service, mock_image_repo):
        """Test get random image with exception."""
        mock_image_repo.get_random_image.side_effect = Exception("Database error")

        result = service.get_random_image()

        assert result is None

    def test_health_check_success(self, service, mock_image_repo):
        """Test health check success."""
        mock_image_repo.health_check.return_value = True

        result = service.health_check()

        assert result is True
        mock_image_repo.health_check.assert_called_once()

    def test_health_check_failure(self, service, mock_image_repo):
        """Test health check failure."""
        mock_image_repo.health_check.return_value = False

        result = service.health_check()

        assert result is False

    def test_health_check_exception(self, service, mock_image_repo):
        """Test health check with exception."""
        mock_image_repo.health_check.side_effect = Exception("Connection error")

        result = service.health_check()

        assert result is False
