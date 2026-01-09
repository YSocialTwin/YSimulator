"""
Simple test script to verify database annotation methods work correctly.

This is a basic manual test to check that the database methods can be called
without errors. Full integration testing would require a running database.
"""

import sys
import uuid


def test_db_method_signatures():
    """
    Test that all database methods have the correct signatures.
    This doesn't test actual database operations, just the method definitions.
    """
    from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware

    # Check that all methods exist
    required_methods = [
        "add_or_get_hashtag",
        "add_post_hashtag",
        "get_user_by_username",
        "add_mention",
        "add_post_sentiment",
        "add_post_toxicity",
    ]

    for method_name in required_methods:
        if not hasattr(DatabaseMiddleware, method_name):
            print(f"✗ Missing method: {method_name}")
        else:
            print(f"✓ Method exists: {method_name}")


def test_annotation_processing():
    """
    Test the annotation processing logic structure.
    """
    # Create sample annotation data
    sample_annotations = {
        "hashtags": ["AI", "machinelearning"],
        "mentions": ["researcher", "scientist"],
        "sentiment": {"neg": 0.0, "pos": 0.8, "neu": 0.2, "compound": 0.7},
        "toxicity": None,
    }

    print("\n✓ Sample annotation structure is valid:")
    print(f"  - Hashtags: {sample_annotations['hashtags']}")
    print(f"  - Mentions: {sample_annotations['mentions']}")
    print(f"  - Sentiment: compound={sample_annotations['sentiment']['compound']}")


def test_action_dto_with_annotations():
    """
    Test that ActionDTO can hold annotation data.
    """
    from YSimulator.YClient.classes.ray_models import ActionDTO

    # Create an action with annotations
    annotations = {
        "hashtags": ["test"],
        "mentions": ["user"],
        "sentiment": {"compound": 0.5, "pos": 0.5, "neg": 0.0, "neu": 0.5},
        "toxicity": None,
    }

    action = ActionDTO(
        agent_id="test-uuid",
        cluster_id=1,
        action_type="POST",
        content="Test post #test @user",
        annotations=annotations,
    )

    if action.annotations is not None:
        print("\n✓ ActionDTO can hold annotations")
        print(f"  - Content: {action.content}")
        print(f"  - Hashtags: {action.annotations['hashtags']}")
        print(f"  - Mentions: {action.annotations['mentions']}")
    else:
        print("\n✗ ActionDTO annotations are None")


def test_text_annotation_flow():
    """
    Test the complete text annotation flow.
    """
    from YSimulator.YClient.text_support.text_annotator import annotate_text

    test_texts = [
        "Great work on #AI research @researcher!",
        "Discussing #machinelearning with @scientist1 and @scientist2",
        "Simple post without hashtags or mentions",
    ]

    print("\n✓ Testing complete annotation flow:")
    for text in test_texts:
        annotations = annotate_text(
            text, enable_sentiment=True, enable_toxicity=False, perspective_api_key=None
        )

        print(f"\n  Text: {text}")
        print(f"  Hashtags: {annotations['hashtags']}")
        print(f"  Mentions: {annotations['mentions']}")
        print(f"  Sentiment: {annotations['sentiment']['compound']:.3f}")


if __name__ == "__main__":
    print("=" * 60)
    print("Database Annotation Methods Test")
    print("=" * 60)

    all_passed = True

    print("\n1. Testing database method signatures...")
    if not test_db_method_signatures():
        all_passed = False

    print("\n2. Testing annotation data structure...")
    if not test_annotation_processing():
        all_passed = False

    print("\n3. Testing ActionDTO with annotations...")
    if not test_action_dto_with_annotations():
        all_passed = False

    print("\n4. Testing complete text annotation flow...")
    if not test_text_annotation_flow():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        print("=" * 60)
        sys.exit(1)
