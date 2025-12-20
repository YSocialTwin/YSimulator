from sqlalchemy import desc, func, case
from YSimulator.YServer.recsys.utils import (
    get_follows,
    fetch_common_interest_posts,
    fetch_common_user_interest_posts,
    fetch_similar_users_posts,
)
from YSimulator.YServer.classes.models import (
    Post,
    User_mgmt,
    Round,
    Follow,
    PostTopic,
    Reaction,
)


def read(db_session, limit, mode, visibility_rounds, uid, followers_ratio=1, article=False):
    """
    Return a list of candidate posts for the user as filtered by the content recommendation system.

    :return: a json object with the post ids
    """

    vround = visibility_rounds
    uid = uid
    fratio = followers_ratio

    if article in True:
        # get the user
        us = User_mgmt.query.filter_by(id=uid).first()
        # get news pages ids having the same user leaning
        pages = User_mgmt.query.filter_by(is_page=1, leaning=us.leaning).all()
        if pages is not None:
            pages = [x.id for x in pages]
        else:
            pages = []

    # visibility
    current_round = Round.query.order_by(desc(Round.id)).first()
    visibility = current_round.id - vround

    if fratio < 1:
        follower_posts_limit = int(limit * fratio)
        additional_posts_limit = limit - follower_posts_limit
    else:
        follower_posts_limit = limit
        additional_posts_limit = 0

    if mode == "rchrono":
        # get posts in reverse chronological order
        if article:
            posts = (
                db.session.query(Post)
                .filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(pages),
                )
                .order_by(desc(Post.id))
                .limit(10)
            ).all()
        else:
            posts = (
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.user_id != uid)
                .order_by(desc(Post.id))
                .limit(10)
            ).all()

    elif mode == "rchrono_popularity":
        if article:
            posts = (
                db.session.query(Post)
                .filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(pages),
                )
                .order_by(desc(Post.id), desc(Post.reaction_count))
                .limit(limit)
            ).all()

        else:
            posts = (
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.user_id != uid)
                .order_by(desc(Post.id), desc(Post.reaction_count))
                .limit(limit)
            ).all()

        posts = [posts, []]

    elif mode == "rchrono_followers":
        if fratio < 1:
            follower_posts_limit = int(limit * fratio)
            additional_posts_limit = limit - follower_posts_limit
        else:
            follower_posts_limit = limit
            additional_posts_limit = 0

        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers in reverse chronological order
        if article:
            posts = (
                Post.query.filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(pages),
                    Post.user_id.in_(follower_ids),
                )
                .order_by(desc(Post.id))
                .limit(follower_posts_limit)
            ).all()
        else:
            posts = (
                Post.query.filter(
                    Post.round >= visibility, Post.user_id.in_(follower_ids)
                )
                .order_by(desc(Post.id))
                .limit(follower_posts_limit)
            ).all()

        if additional_posts_limit != 0:
            if article:
                additional_posts = (
                    Post.query.filter(
                        Post.round >= visibility,
                        Post.news_id != -1,
                        Post.user_id != uid,
                    )
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                ).all()
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.user_id != uid)
                    .order_by(desc(Post.id))
                    .limit(additional_posts_limit)
                ).all()

            posts = [posts, additional_posts]

    elif mode == "rchrono_followers_popularity":
        if fratio < 1:
            follower_posts_limit = int(limit * fratio)
            additional_posts_limit = limit - follower_posts_limit
        else:
            follower_posts_limit = limit
            additional_posts_limit = 0

        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers ordered by likes and reverse chronologically
        if article:
            posts = (
                db.session.query(Post)
                .filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(pages),
                )
                .order_by(desc(Post.id), desc(Post.reaction_count))
                .limit(follower_posts_limit)
            ).all()
        else:
            posts = (
                db.session.query(Post)
                .filter(Post.round >= visibility, Post.user_id.in_(follower_ids))
                .order_by(desc(Post.id), desc(Post.reaction_count))
                .limit(follower_posts_limit)
            ).all()

        if additional_posts_limit != 0:
            if article:
                additional_posts = (
                    Post.query.filter(
                        Post.round >= visibility,
                        Post.news_id != -1,
                        Post.user_id.in_(pages),
                    )
                    .order_by(
                        desc(Post.id),
                        desc(Post.reaction_count),
                    )
                    .limit(additional_posts_limit)
                ).all()
            else:
                additional_posts = (
                    Post.query.filter(Post.round >= visibility, Post.user_id != uid)
                    .order_by(desc(Post.id), desc(Post.reaction_count))
                    .limit(additional_posts_limit)
                ).all()

            posts = [posts, additional_posts]

    elif mode == "rchrono_comments":
        # get posts with the most comments in reverse chronological order (as longer thread)
        query = (
            db.session.query(
                Post
            )  # , func.count(Post.thread_id).label("comment_count"))
            .filter(
                Post.round >= visibility,
                # Post.comment_to != -1,
                Post.news_id != -1 if article else True,
            )
            .group_by(Post.thread_id)
        )
        follower_ids = get_follows(uid)
        query_follower = query.filter(Post.user_id.in_(follower_ids))

        posts = [
            # query_follower.order_by(desc("comment_count"), desc(Post.id))
            query_follower.order_by(desc(Post.reaction_count), desc(Post.id))
            .limit(follower_posts_limit)
            .all()
        ]

        if additional_posts_limit != 0:
           # query_additional = query.filter(Post.user_id.notin_(follower_ids))
            additional_posts = (
                # query_additional.order_by(desc("comment_count"), desc(Post.id))
                query_follower.order_by(desc(Post.reaction_count), desc(Post.id))
                .limit(additional_posts_limit)
                .all()
            )

            posts = [posts, additional_posts]

    elif mode == "common_interests":
        # get posts with common topic interests
        posts = fetch_common_interest_posts(
            uid=uid,
            visibility=visibility,
            articles=article,
            follower_posts_limit=follower_posts_limit,
            additional_posts_limit=additional_posts_limit,
        )

    elif mode == "common_user_interests":
        # get most interacted posts by users with common interests
        posts = fetch_common_user_interest_posts(
            uid=uid,
            visibility=visibility,
            articles=article,
            follower_posts_limit=follower_posts_limit,
            additional_posts_limit=additional_posts_limit,
            reactions_type=["like", "dislike"],
        )

    elif mode == "similar_users_react":
        # get posts from similar users
        posts = fetch_similar_users_posts(
            uid=uid,
            visibility=visibility,
            articles=article,
            limit=limit,
            filter_function=get_posts_by_reactions,
            reactions_type=["like"],
        )

    elif mode == "similar_users_posts":
        # get posts from similar users
        posts = fetch_similar_users_posts(
            uid=uid,
            visibility=visibility,
            articles=article,
            limit=limit,
            filter_function=get_posts_by_author,
            reactions_type=["like"],
        )

    else:
        # get posts in random order
        if article:
            posts = (
                Post.query.filter(
                    Post.round >= visibility,
                    Post.news_id != -1,
                    Post.user_id.in_(pages),
                )
                .order_by(func.random())
                .limit(limit)
            ).all()

        else:
            posts = (
                Post.query.filter(Post.round >= visibility, Post.user_id != uid)
                .order_by(func.random())
                .limit(limit)
            ).all()

    res = []

    for post_type in posts:
        if type(post_type) == list:
            for post in post_type:
                try:
                    if len(post) > 0 and post[0] is not None:
                        res.append(post[0].id)
                except:
                    if post is not None:
                        res.append(post.id)
        else:
            if type(post_type) == tuple:
                if len(post_type) > 0 and post_type[0] is not None:
                    res.append(post_type[0].id)
            else:
                if post_type is not None:
                    res.append(post_type.id)

    # save recommendations
    current_round = Round.query.order_by(desc(Round.id)).first()
    if len(res) > 0:
        recs = Recommendation(
            user_id=uid,
            post_ids="|".join([str(x) for x in res]),
            round=current_round.id,
        )
        db.session.add(recs)
        db.session.commit()
    return res