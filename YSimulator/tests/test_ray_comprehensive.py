"""
Comprehensive tests for Ray models and data transfer objects.

Achieving 80%+ coverage for Ray models including all DTOs and dataclasses.
"""

import pytest
from dataclasses import asdict
from YSimulator.YClient.classes.ray_models import (
    AgentProfile,
    ActionDTO,
    SimulationInstruction,
    FollowDTO,
    ReactionDTO,
    MentionDTO,
    RecommendationDTO,
    VotingDTO,
    UserInterestDTO,
    PostEmotionDTO,
    PostHashtagDTO,
    PostSentimentDTO,
    PostTopicDTO,
    PostToxicityDTO,
)


class TestAgentProfile:
    """Test AgentProfile dataclass."""

    def test_agent_profile_basic_creation(self):
        """Test basic AgentProfile creation with required fields."""
        profile = AgentProfile(
            id="test-uuid-123",
            username="test_user",
        )
        assert profile.id == "test-uuid-123"
        assert profile.username == "test_user"
        assert profile.email == ""  # Default value
        assert profile.password == "default_password"  # Default placeholder

    def test_agent_profile_with_all_fields(self):
        """Test AgentProfile with all fields populated."""
        profile = AgentProfile(
            id="agent-1",
            username="john_doe",
            email="john@example.com",
            password="test123",
            leaning="liberal",
            user_type="user",
            age=30,
            oe="high",
            co="medium",
            ex="high",
            ag="medium",
            ne="low",
            recsys_type="rchrono_followers",
            frecsys_type="common_neighbors",
            language="en",
            owner="organization1",
            education_level="bachelor",
            joined_on="round-1",
            gender="male",
            nationality="USA",
            round_actions=5,
            toxicity="low",
            is_page=0,
            left_on=None,
            daily_activity_level=2,
            profession="engineer",
            activity_profile="9-to-5",
            archetype="Validator",
            feed_url=None,
            cluster=1,
            llm=True,
            interests=(["Tech", "Science"], [10, 5]),
            opinions={"Tech": 0.8, "Science": 0.6},
        )

        assert profile.age == 30
        assert profile.archetype == "Validator"
        assert profile.llm is True
        assert profile.interests == (["Tech", "Science"], [10, 5])
        assert profile.opinions == {"Tech": 0.8, "Science": 0.6}

    def test_agent_profile_page_agent(self):
        """Test page agent specific fields."""
        profile = AgentProfile(
            id="page-1",
            username="news_page",
            is_page=1,
            feed_url="https://example.com/rss",
            user_type="page",
        )

        assert profile.is_page == 1
        assert profile.feed_url == "https://example.com/rss"

    def test_agent_profile_big_five_personality(self):
        """Test Big Five personality traits."""
        profile = AgentProfile(
            id="agent-2",
            username="personality_test",
            oe="high",
            co="medium",
            ex="low",
            ag="high",
            ne="medium",
        )

        assert profile.oe == "high"  # Openness
        assert profile.co == "medium"  # Conscientiousness
        assert profile.ex == "low"  # Extraversion
        assert profile.ag == "high"  # Agreeableness
        assert profile.ne == "medium"  # Neuroticism

    def test_agent_profile_activity_patterns(self):
        """Test activity-related fields."""
        profile = AgentProfile(
            id="agent-3",
            username="active_user",
            round_actions=10,
            daily_activity_level=3,
            activity_profile="Night Owl",
        )

        assert profile.round_actions == 10
        assert profile.daily_activity_level == 3
        assert profile.activity_profile == "Night Owl"

    def test_agent_profile_churn_tracking(self):
        """Test churn-related fields (joined_on, left_on)."""
        profile = AgentProfile(
            id="agent-4",
            username="churned_user",
            joined_on="round-uuid-1",
            left_on="round-uuid-100",
        )

        assert profile.joined_on == "round-uuid-1"
        assert profile.left_on == "round-uuid-100"

    def test_agent_profile_interests_structure(self):
        """Test interests tuple structure (topics, counts)."""
        topics = ["Sports", "Politics", "Entertainment"]
        counts = [20, 15, 10]

        profile = AgentProfile(id="agent-5", username="interested_user", interests=(topics, counts))

        assert profile.interests[0] == topics
        assert profile.interests[1] == counts
        assert len(profile.interests[0]) == len(profile.interests[1])

    def test_agent_profile_opinions_dictionary(self):
        """Test opinions dictionary structure."""
        opinions = {"Climate Change": 0.9, "Economy": 0.5, "Healthcare": 0.7}

        profile = AgentProfile(id="agent-6", username="opinionated_user", opinions=opinions)

        assert profile.opinions == opinions
        assert profile.opinions["Climate Change"] == 0.9


class TestActionDTO:
    """Test ActionDTO dataclass."""

    def test_action_dto_post(self):
        """Test POST action DTO."""
        action = ActionDTO(
            agent_id="agent-1",
            cluster_id=1,
            action_type="POST",
            content="This is a test post",
            topic="Technology",
        )

        assert action.action_type == "POST"
        assert action.content == "This is a test post"
        assert action.topic == "Technology"

    def test_action_dto_like(self):
        """Test LIKE action DTO."""
        action = ActionDTO(
            agent_id="agent-2", cluster_id=1, action_type="LIKE", target_post_id="post-uuid-123"
        )

        assert action.action_type == "LIKE"
        assert action.target_post_id == "post-uuid-123"

    def test_action_dto_comment(self):
        """Test COMMENT action DTO."""
        action = ActionDTO(
            agent_id="agent-3",
            cluster_id=2,
            action_type="COMMENT",
            content="Great post!",
            target_post_id="post-uuid-456",
            updated_opinions={"topic-1": 0.8},
        )

        assert action.action_type == "COMMENT"
        assert action.content == "Great post!"
        assert action.updated_opinions == {"topic-1": 0.8}

    def test_action_dto_share(self):
        """Test SHARE action DTO."""
        action = ActionDTO(
            agent_id="agent-4", cluster_id=1, action_type="SHARE", target_post_id="post-uuid-789"
        )

        assert action.action_type == "SHARE"
        assert action.target_post_id == "post-uuid-789"

    def test_action_dto_follow(self):
        """Test FOLLOW action DTO."""
        action = ActionDTO(
            agent_id="agent-5", cluster_id=1, action_type="FOLLOW", target_user_id="user-uuid-321"
        )

        assert action.action_type == "FOLLOW"
        assert action.target_user_id == "user-uuid-321"

    def test_action_dto_unfollow(self):
        """Test UNFOLLOW action DTO."""
        action = ActionDTO(
            agent_id="agent-6", cluster_id=1, action_type="UNFOLLOW", target_user_id="user-uuid-654"
        )

        assert action.action_type == "UNFOLLOW"
        assert action.target_user_id == "user-uuid-654"

    def test_action_dto_with_annotations(self):
        """Test action with text annotations."""
        annotations = {
            "hashtags": ["#tech", "#AI"],
            "mentions": ["@user1", "@user2"],
            "sentiment": {"compound": 0.8},
            "toxicity": 0.1,
        }

        action = ActionDTO(
            agent_id="agent-7",
            cluster_id=1,
            action_type="POST",
            content="Check out this #tech #AI post @user1 @user2",
            annotations=annotations,
        )

        assert action.annotations == annotations
        assert len(action.annotations["hashtags"]) == 2
        assert len(action.annotations["mentions"]) == 2

    def test_action_dto_news_post(self):
        """Test POST action with news article."""
        action = ActionDTO(
            agent_id="agent-8",
            cluster_id=2,
            action_type="POST",
            content="Breaking news!",
            article_id="article-uuid-999",
            topic="News",
        )

        assert action.article_id == "article-uuid-999"
        assert action.topic == "News"


class TestSimulationInstruction:
    """Test SimulationInstruction dataclass."""

    def test_simulation_instruction_wait(self):
        """Test WAIT instruction."""
        instruction = SimulationInstruction(status="WAIT", day=1, slot=5)

        assert instruction.status == "WAIT"
        assert instruction.day == 1
        assert instruction.slot == 5

    def test_simulation_instruction_proceed(self):
        """Test PROCEED instruction."""
        recent_posts = ["post-1", "post-2", "post-3"]
        instruction = SimulationInstruction(
            status="PROCEED", day=2, slot=10, recent_post_ids=recent_posts
        )

        assert instruction.status == "PROCEED"
        assert instruction.recent_post_ids == recent_posts
        assert len(instruction.recent_post_ids) == 3

    def test_simulation_instruction_default_values(self):
        """Test default values for SimulationInstruction."""
        instruction = SimulationInstruction(status="WAIT")

        assert instruction.day == 0
        assert instruction.slot == 0
        assert instruction.recent_post_ids is None


class TestSocialActionDTOs:
    """Test social action DTOs (Follow, Reaction, Mention, etc.)."""

    def test_follow_dto(self):
        """Test FollowDTO."""
        follow = FollowDTO(
            id="follow-uuid-1",
            user_id="user-1",
            follower_id="user-2",
            action="follow",
            round="round-1",
        )

        assert follow.action == "follow"
        assert follow.user_id == "user-1"
        assert follow.follower_id == "user-2"

    def test_follow_dto_unfollow(self):
        """Test FollowDTO with unfollow action."""
        unfollow = FollowDTO(
            id="follow-uuid-2",
            user_id="user-3",
            follower_id="user-4",
            action="unfollow",
            round="round-5",
        )

        assert unfollow.action == "unfollow"

    def test_reaction_dto(self):
        """Test ReactionDTO."""
        reaction = ReactionDTO(
            id="reaction-uuid-1", user_id=123, post_id="post-uuid-1", type="like", round="round-1"
        )

        assert reaction.type == "like"
        assert reaction.user_id == 123

    def test_reaction_dto_various_types(self):
        """Test various reaction types."""
        types = ["like", "love", "laugh", "angry", "sad"]

        for i, reaction_type in enumerate(types):
            reaction = ReactionDTO(
                id=f"reaction-{i}",
                user_id=i,
                post_id=f"post-{i}",
                type=reaction_type,
                round="round-1",
            )
            assert reaction.type == reaction_type

    def test_mention_dto(self):
        """Test MentionDTO."""
        mention = MentionDTO(
            id="mention-uuid-1",
            post_id="post-uuid-1",
            user_id="user-1",
            round="round-1",
            answered=0,
        )

        assert mention.answered == 0
        assert mention.user_id == "user-1"

    def test_mention_dto_answered(self):
        """Test MentionDTO with answered status."""
        mention = MentionDTO(
            id="mention-uuid-2",
            post_id="post-uuid-2",
            user_id="user-2",
            round="round-2",
            answered=1,
        )

        assert mention.answered == 1

    def test_recommendation_dto(self):
        """Test RecommendationDTO."""
        recommendation = RecommendationDTO(
            id="rec-uuid-1", user_id=456, post_ids="post-1,post-2,post-3", round="round-1"
        )

        assert recommendation.user_id == 456
        assert "post-1" in recommendation.post_ids

    def test_voting_dto(self):
        """Test VotingDTO."""
        voting = VotingDTO(
            vid="vote-uuid-1",
            user_id="user-1",
            preference="upvote",
            content_type="post",
            content_id="post-1",
            round="round-1",
        )

        assert voting.preference == "upvote"
        assert voting.content_type == "post"

    def test_user_interest_dto(self):
        """Test UserInterestDTO."""
        user_interest = UserInterestDTO(
            id="ui-uuid-1", user_id="user-1", interest_id="interest-1", round_id="round-1"
        )

        assert user_interest.user_id == "user-1"
        assert user_interest.interest_id == "interest-1"


class TestContentMetadataDTOs:
    """Test content metadata DTOs (PostEmotion, PostHashtag, etc.)."""

    def test_post_emotion_dto(self):
        """Test PostEmotionDTO."""
        emotion = PostEmotionDTO(id="emotion-uuid-1", post_id="post-uuid-1", emotion_id="joy")

        assert emotion.post_id == "post-uuid-1"
        assert emotion.emotion_id == "joy"

    def test_post_hashtag_dto(self):
        """Test PostHashtagDTO."""
        hashtag = PostHashtagDTO(id="hashtag-uuid-1", post_id="post-uuid-1", hashtag_id="tech")

        assert hashtag.hashtag_id == "tech"

    def test_post_sentiment_dto(self):
        """Test PostSentimentDTO."""
        sentiment = PostSentimentDTO(
            id="sentiment-uuid-1",
            post_id="post-uuid-1",
            user_id="user-1",
            topic_id="topic-1",
            round="round-1",
            neg=0.1,
            pos=0.8,
            neu=0.1,
            compound=0.7,
            is_post=1,
            is_comment=0,
            is_reaction=0,
        )

        assert sentiment.compound == 0.7
        assert sentiment.pos == 0.8
        assert sentiment.is_post == 1

    def test_post_sentiment_dto_comment(self):
        """Test PostSentimentDTO for comment."""
        sentiment = PostSentimentDTO(
            id="sentiment-uuid-2",
            post_id="post-uuid-2",
            user_id="user-2",
            topic_id="topic-2",
            round="round-2",
            is_post=0,
            is_comment=1,
            is_reaction=0,
        )

        assert sentiment.is_comment == 1
        assert sentiment.is_post == 0

    def test_post_topic_dto(self):
        """Test PostTopicDTO."""
        topic = PostTopicDTO(id="topic-uuid-1", post_id="post-uuid-1", topic_id="technology")

        assert topic.topic_id == "technology"

    def test_post_toxicity_dto(self):
        """Test PostToxicityDTO."""
        toxicity = PostToxicityDTO(
            id="toxicity-uuid-1",
            post_id="post-uuid-1",
            toxicity=0.2,
            severe_toxicity=0.05,
            identity_attack=0.01,
            insult=0.15,
            profanity=0.1,
            threat=0.02,
            sexually_explicit=0.01,
            flirtation=0.05,
        )

        assert toxicity.toxicity == 0.2
        assert toxicity.insult == 0.15
        assert toxicity.threat == 0.02

    def test_post_toxicity_dto_defaults(self):
        """Test PostToxicityDTO default values."""
        toxicity = PostToxicityDTO(id="toxicity-uuid-2", post_id="post-uuid-2")

        assert toxicity.toxicity == 0.0
        assert toxicity.severe_toxicity == 0.0
        assert toxicity.identity_attack == 0.0


class TestDataclassConversions:
    """Test dataclass conversion utilities."""

    def test_agent_profile_to_dict(self):
        """Test converting AgentProfile to dictionary."""
        profile = AgentProfile(id="agent-1", username="test_user", age=25, llm=True)

        profile_dict = asdict(profile)
        assert profile_dict["id"] == "agent-1"
        assert profile_dict["username"] == "test_user"
        assert profile_dict["age"] == 25
        assert profile_dict["llm"] is True

    def test_action_dto_to_dict(self):
        """Test converting ActionDTO to dictionary."""
        action = ActionDTO(
            agent_id="agent-1", cluster_id=1, action_type="POST", content="Test post"
        )

        action_dict = asdict(action)
        assert action_dict["agent_id"] == "agent-1"
        assert action_dict["action_type"] == "POST"
        assert action_dict["content"] == "Test post"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_agent_profile_empty_interests(self):
        """Test AgentProfile with empty interests."""
        profile = AgentProfile(id="agent-1", username="no_interests", interests=([], []))

        assert profile.interests == ([], [])
        assert len(profile.interests[0]) == 0

    def test_agent_profile_none_optional_fields(self):
        """Test AgentProfile with None for optional fields."""
        profile = AgentProfile(
            id="agent-1",
            username="minimal",
            oe=None,
            co=None,
            ex=None,
            ag=None,
            ne=None,
            opinions=None,
            interests=None,
        )

        assert profile.oe is None
        assert profile.opinions is None
        assert profile.interests is None

    def test_action_dto_all_none_optionals(self):
        """Test ActionDTO with all optional fields as None."""
        action = ActionDTO(agent_id="agent-1", cluster_id=1, action_type="POST")

        assert action.content is None
        assert action.target_post_id is None
        assert action.topic is None
        assert action.annotations is None

    def test_simulation_instruction_no_recent_posts(self):
        """Test SimulationInstruction without recent posts."""
        instruction = SimulationInstruction(status="PROCEED", day=1, slot=1)

        assert instruction.recent_post_ids is None

    def test_post_toxicity_boundary_values(self):
        """Test PostToxicityDTO with boundary values (0.0 and 1.0)."""
        toxicity = PostToxicityDTO(
            id="toxicity-uuid-1",
            post_id="post-uuid-1",
            toxicity=1.0,
            severe_toxicity=0.0,
            identity_attack=1.0,
            insult=0.5,
        )

        assert toxicity.toxicity == 1.0
        assert toxicity.severe_toxicity == 0.0
        assert toxicity.identity_attack == 1.0
