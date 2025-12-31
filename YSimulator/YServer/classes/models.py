"""
Complete SQLAlchemy models based on postgresql_server.sql schema.

This module defines all database models with proper relationships, foreign keys,
and UUID-based primary keys where appropriate for distributed system compatibility.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ================================================
# REFERENCE DATA TABLES (Integer IDs)
# ================================================


class Emotion(Base):
    """Emotion types with icon mappings."""

    __tablename__ = "emotions"

    id = Column(String(36), primary_key=True)
    emotion = Column(Text, nullable=False)
    icon = Column(Text)

    # Relationships
    post_emotions = relationship("PostEmotion", back_populates="emotion", cascade="all, delete-orphan")


class Hashtag(Base):
    """Hashtag registry for content categorization."""

    __tablename__ = "hashtags"

    id = Column(String(36), primary_key=True)
    hashtag = Column(Text, nullable=False)

    # Relationships
    post_hashtags = relationship("PostHashtag", back_populates="hashtag", cascade="all, delete-orphan")


class Interest(Base):
    """Topics/interests for content and user profiling."""

    __tablename__ = "interests"

    iid = Column(String(36), primary_key=True)
    interest = Column(Text)

    # Relationships
    user_interests = relationship("UserInterest", back_populates="interest", cascade="all, delete-orphan")
    article_topics = relationship("ArticleTopic", back_populates="topic", cascade="all, delete-orphan")
    post_topics = relationship("PostTopic", back_populates="topic", cascade="all, delete-orphan")
    post_sentiments = relationship("PostSentiment", back_populates="topic", cascade="all, delete-orphan")


class Round(Base):
    """Simulation time tracking (day and hour/slot)."""

    __tablename__ = "rounds"

    id = Column(String(36), primary_key=True)
    day = Column(Integer)
    hour = Column(Integer)

    # Unique constraint to prevent duplicate rounds
    __table_args__ = (UniqueConstraint("day", "hour", name="uq_round_day_hour"),)

    # Relationships to all tables that reference rounds
    posts = relationship("Post", back_populates="round_obj", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="round_obj", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="round_obj", cascade="all, delete-orphan")
    user_interests = relationship("UserInterest", back_populates="round_obj", cascade="all, delete-orphan")
    post_sentiments = relationship("PostSentiment", back_populates="round_obj", cascade="all, delete-orphan")


# ================================================
# USER MANAGEMENT (Integer IDs from config)
# ================================================


class User_mgmt(Base):
    """
    User management model for experiment participants.

    Stores user profile information including personality traits (Big Five),
    demographic information, preferences, and activity settings.
    """

    __tablename__ = "user_mgmt"

    id = Column(String(36), primary_key=True)  # UUID string
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(50))
    password = Column(String(400), nullable=False)
    user_type = Column(Text)
    leaning = Column(Text)
    age = Column(Integer)
    # Big Five personality traits
    oe = Column(Text)  # Openness to Experience
    co = Column(Text)  # Conscientiousness
    ex = Column(Text)  # Extraversion
    ag = Column(Text)  # Agreeableness
    ne = Column(Text)  # Neuroticism
    recsys_type = Column(Text)
    language = Column(Text)
    owner = Column(Text)
    education_level = Column(Text)
    joined_on = Column(String(36), ForeignKey("rounds.id", ondelete="SET NULL"))
    frecsys_type = Column(Text)
    round_actions = Column(Integer, nullable=False, default=3)
    gender = Column(Text)
    nationality = Column(Text)
    toxicity = Column(Text)
    is_page = Column(Integer, nullable=False, default=0)
    left_on = Column(String(36))
    daily_activity_level = Column(Integer, default=1)
    profession = Column(Text)
    activity_profile = Column(Text)
    archetype = Column(Text, default=None)
    last_active_day = Column(Integer)

    # Relationships
    follows_as_user = relationship(
        "Follow", foreign_keys="Follow.user_id", back_populates="user", cascade="all, delete-orphan"
    )
    follows_as_follower = relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        back_populates="follower",
        cascade="all, delete-orphan",
    )
    recommendations = relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")
    user_interests = relationship("UserInterest", back_populates="user", cascade="all, delete-orphan")
    votings = relationship("Voting", back_populates="user", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    mentions = relationship("Mention", back_populates="user", cascade="all, delete-orphan")
    post_sentiments = relationship("PostSentiment", back_populates="user", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="user", cascade="all, delete-orphan")
    round_joined = relationship("Round")


# ================================================
# SOCIAL INTERACTIONS (UUID IDs)
# ================================================


class Follow(Base):
    """Follow relationships between users."""

    __tablename__ = "follow"

    id = Column(String(36), primary_key=True)  # UUID string
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"), nullable=False)
    follower_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"), nullable=False)
    action = Column(Text)
    round = Column(String(36))

    # Relationships
    user = relationship("User_mgmt", foreign_keys=[user_id], back_populates="follows_as_user")
    follower = relationship("User_mgmt", foreign_keys=[follower_id], back_populates="follows_as_follower")


Index("idx_follow_user_id", Follow.user_id)
Index("idx_follow_follower_id", Follow.follower_id)
Index("idx_follow_round", Follow.round)


class Recommendation(Base):
    """Content recommendations for users."""

    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"), nullable=False)
    post_ids = Column(Text)  # Comma-separated or JSON list of post UUIDs
    round = Column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    user = relationship("User_mgmt", back_populates="recommendations")
    round_obj = relationship("Round", back_populates="recommendations")


Index("idx_recommendations_user_id", Recommendation.user_id)
Index("idx_recommendations_round", Recommendation.round)


class UserInterest(Base):
    """User interest associations."""

    __tablename__ = "user_interest"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"))
    interest_id = Column(String(36), ForeignKey("interests.iid", ondelete="CASCADE"))
    round_id = Column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"))

    # Relationships
    user = relationship("User_mgmt", back_populates="user_interests")
    interest = relationship("Interest", back_populates="user_interests")
    round_obj = relationship("Round", back_populates="user_interests")


Index("idx_user_interest_user_id", UserInterest.user_id)
Index("idx_user_interest_interest_id", UserInterest.interest_id)
Index("idx_user_interest_round_id", UserInterest.round_id)


class Voting(Base):
    """User voting and content preferences."""

    __tablename__ = "voting"

    vid = Column(String(36), primary_key=True)  # UUID
    round = Column(String(36))
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"))
    preference = Column(Text)
    content_type = Column(Text)
    content_id = Column(String(36))

    # Relationships
    user = relationship("User_mgmt", back_populates="votings")


Index("idx_voting_user_id", Voting.user_id)
Index("idx_voting_round", Voting.round)


# ================================================
# CONTENT SOURCES (Integer IDs)
# ================================================


class Website(Base):
    """News source/website definitions."""

    __tablename__ = "websites"

    id = Column(String(36), primary_key=True)
    name = Column(Text)
    rss = Column(Text)
    leaning = Column(Text)
    category = Column(Text)
    last_fetched = Column(String(36))
    country = Column(Text)
    language = Column(Text)

    # Relationships
    articles = relationship("Article", back_populates="website", cascade="all, delete-orphan")


class Article(Base):
    """News articles from content sources."""

    __tablename__ = "articles"

    id = Column(String(36), primary_key=True)
    title = Column(Text, nullable=False)
    summary = Column(Text)
    website_id = Column(String(36), ForeignKey("websites.id", ondelete="CASCADE"), nullable=False)
    fetched_on = Column(String(36), nullable=False)
    link = Column(Text)

    # Relationships
    website = relationship("Website", back_populates="articles")
    article_topics = relationship("ArticleTopic", back_populates="article", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="article", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="article", cascade="all, delete-orphan")


Index("idx_articles_website_id", Article.website_id)


class ArticleTopic(Base):
    """Article-topic relationships."""

    __tablename__ = "article_topics"

    id = Column(String(36), primary_key=True)
    article_id = Column(String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(String(36), ForeignKey("interests.iid", ondelete="CASCADE"))

    # Relationships
    article = relationship("Article", back_populates="article_topics")
    topic = relationship("Interest", back_populates="article_topics")

    # Unique constraint
    __table_args__ = (UniqueConstraint("article_id", "topic_id", name="article_topic"),)


Index("idx_article_topics_article_id", ArticleTopic.article_id)
Index("idx_article_topics_topic_id", ArticleTopic.topic_id)


class Image(Base):
    """Image metadata for articles."""

    __tablename__ = "images"

    id = Column(String(36), primary_key=True)
    url = Column(Text)
    description = Column(Text)
    article_id = Column(String(36), ForeignKey("articles.id", ondelete="CASCADE"))

    # Relationships
    article = relationship("Article", back_populates="images")
    posts = relationship("Post", back_populates="image", cascade="all, delete-orphan")


Index("idx_images_article_id", Image.article_id)


# ================================================
# POSTS AND INTERACTIONS (UUID IDs)
# ================================================


class Post(Base):
    """Social media posts."""

    __tablename__ = "post"

    id = Column(String(36), primary_key=True)  # UUID
    tweet = Column(Text, nullable=False)
    post_img = Column(String(20))
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"), nullable=False)
    comment_to = Column(String(36), default=-1)
    thread_id = Column(String(36))
    round = Column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"))
    news_id = Column(String(36), ForeignKey("articles.id", ondelete="CASCADE"), default=-1)
    shared_from = Column(String(36), default=-1)
    image_id = Column(String(36), ForeignKey("images.id", ondelete="CASCADE"))
    reaction_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User_mgmt", back_populates="posts")
    round_obj = relationship("Round", back_populates="posts")
    article = relationship("Article", back_populates="posts")
    image = relationship("Image", back_populates="posts")
    mentions = relationship("Mention", back_populates="post", cascade="all, delete-orphan")
    post_emotions = relationship("PostEmotion", back_populates="post", cascade="all, delete-orphan")
    post_hashtags = relationship("PostHashtag", back_populates="post", cascade="all, delete-orphan")
    post_sentiments = relationship("PostSentiment", back_populates="post", cascade="all, delete-orphan")
    post_topics = relationship("PostTopic", back_populates="post", cascade="all, delete-orphan")
    post_toxicity = relationship("PostToxicity", back_populates="post", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="post", cascade="all, delete-orphan")


Index("idx_post_user_id", Post.user_id)
Index("idx_post_round", Post.round)
Index("idx_post_thread_id", Post.thread_id)
Index("idx_post_news_id", Post.news_id)
Index("idx_post_image_id", Post.image_id)


class Mention(Base):
    """User mentions in posts."""

    __tablename__ = "mentions"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"))
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"))
    round = Column(String(36))
    answered = Column(Integer, default=0)

    # Relationships
    user = relationship("User_mgmt", back_populates="mentions")
    post = relationship("Post", back_populates="mentions")


Index("idx_mentions_user_id", Mention.user_id)
Index("idx_mentions_post_id", Mention.post_id)
Index("idx_mentions_round", Mention.round)


class PostEmotion(Base):
    """Emotional tags for posts."""

    __tablename__ = "post_emotions"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"))
    emotion_id = Column(String(36), ForeignKey("emotions.id", ondelete="CASCADE"))

    # Relationships
    post = relationship("Post", back_populates="post_emotions")
    emotion = relationship("Emotion", back_populates="post_emotions")


Index("idx_post_emotions_post_id", PostEmotion.post_id)
Index("idx_post_emotions_emotion_id", PostEmotion.emotion_id)


class PostHashtag(Base):
    """Hashtag associations for posts."""

    __tablename__ = "post_hashtags"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"))
    hashtag_id = Column(String(36), ForeignKey("hashtags.id", ondelete="CASCADE"))

    # Relationships
    post = relationship("Post", back_populates="post_hashtags")
    hashtag = relationship("Hashtag", back_populates="post_hashtags")


Index("idx_post_hashtags_post_id", PostHashtag.post_id)
Index("idx_post_hashtags_hashtag_id", PostHashtag.hashtag_id)


class PostSentiment(Base):
    """Sentiment analysis data for posts."""

    __tablename__ = "post_sentiment"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"), nullable=False)
    neg = Column(Float)
    pos = Column(Float)
    neu = Column(Float)
    compound = Column(Float)
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"), nullable=False)
    round = Column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    sentiment_parent = Column(Text)
    topic_id = Column(String(36), ForeignKey("interests.iid", ondelete="CASCADE"), nullable=False)
    is_post = Column(Integer, nullable=False, default=0)
    is_comment = Column(Integer, nullable=False, default=0)
    is_reaction = Column(Integer, nullable=False, default=0)

    # Relationships
    post = relationship("Post", back_populates="post_sentiments")
    user = relationship("User_mgmt", back_populates="post_sentiments")
    round_obj = relationship("Round", back_populates="post_sentiments")
    topic = relationship("Interest", back_populates="post_sentiments")


Index("idx_post_sentiment_post_id", PostSentiment.post_id)
Index("idx_post_sentiment_user_id", PostSentiment.user_id)
Index("idx_post_sentiment_round", PostSentiment.round)
Index("idx_post_sentiment_topic_id", PostSentiment.topic_id)


class PostTopic(Base):
    """Topic associations for posts."""

    __tablename__ = "post_topics"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"))
    topic_id = Column(String(36), ForeignKey("interests.iid", ondelete="CASCADE"))

    # Relationships
    post = relationship("Post", back_populates="post_topics")
    topic = relationship("Interest", back_populates="post_topics")


Index("idx_post_topics_post_id", PostTopic.post_id)
Index("idx_post_topics_topic_id", PostTopic.topic_id)


class PostToxicity(Base):
    """Toxicity analysis data for posts."""

    __tablename__ = "post_toxicity"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"), nullable=False)
    toxicity = Column(Float, nullable=False, default=0)
    severe_toxicity = Column(Float, default=0)
    identity_attack = Column(Float, default=0)
    insult = Column(Float, default=0)
    profanity = Column(Float, default=0)
    threat = Column(Float, default=0)
    sexually_explicit = Column(Float, default=0)
    flirtation = Column(Float, default=0)

    # Relationships
    post = relationship("Post", back_populates="post_toxicity")


Index("idx_post_toxicity_post_id", PostToxicity.post_id)


class Reaction(Base):
    """User reactions to posts."""

    __tablename__ = "reactions"

    id = Column(String(36), primary_key=True)  # UUID
    post_id = Column(String(36), ForeignKey("post.id", ondelete="CASCADE"))
    user_id = Column(String(36), ForeignKey("user_mgmt.id", ondelete="CASCADE"))
    type = Column(Text)
    round = Column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"))

    # Relationships
    post = relationship("Post", back_populates="reactions")
    user = relationship("User_mgmt", back_populates="reactions")
    round_obj = relationship("Round", back_populates="reactions")


Index("idx_reactions_post_id", Reaction.post_id)
Index("idx_reactions_user_id", Reaction.user_id)
Index("idx_reactions_round", Reaction.round)
