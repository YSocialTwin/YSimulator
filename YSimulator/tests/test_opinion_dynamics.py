"""
Tests for opinion dynamics models.
"""
import pytest
from YSimulator.YClient.opinion_dynamics.confidence_bound import bounded_confidence
from YSimulator.YClient.opinion_dynamics.llm_evaluation import shift_class, Direction


class TestBoundedConfidence:
    """Tests for the bounded confidence model."""
    
    def test_cold_start_neutral(self):
        """Test cold start with neutral initialization."""
        result = bounded_confidence(x=None, y=0.8, cold_start="neutral")
        assert result == 0.5
    
    def test_cold_start_inherited(self):
        """Test cold start with inherited initialization."""
        result = bounded_confidence(x=None, y=0.8, cold_start="inherited")
        assert result == 0.8
    
    def test_within_epsilon_convergence(self):
        """Test opinion convergence when within epsilon."""
        # When opinions are close (within epsilon), they should converge
        result = bounded_confidence(x=0.5, y=0.6, epsilon=0.25, mu=0.5)
        assert result > 0.5  # Should move towards y
        assert result <= 0.6
    
    def test_outside_epsilon_no_change(self):
        """Test no change when opinions are outside epsilon."""
        # When opinions are far apart (outside epsilon), no change by default
        result = bounded_confidence(x=0.2, y=0.8, epsilon=0.25, mu=0.5, theta=0.0)
        assert result == 0.2  # Should stay the same


class TestLLMEvaluation:
    """Tests for the LLM evaluation model components."""
    
    def test_shift_class_agree(self):
        """Test opinion shift when agreeing."""
        opinion_groups = {
            "Strongly against": [0.0, 0.2],
            "Against": [0.2, 0.4],
            "Neutral": [0.4, 0.6],
            "In favor": [0.6, 0.8],
            "Strongly in favor": [0.8, 1.0]
        }
        
        # Move from Neutral towards In favor
        label, value = shift_class("Neutral", "In favor", Direction.AGREE, opinion_groups)
        assert label == "In favor"
        assert abs(value - 0.7) < 0.001
    
    def test_shift_class_disagree(self):
        """Test opinion shift when disagreeing."""
        opinion_groups = {
            "Strongly against": [0.0, 0.2],
            "Against": [0.2, 0.4],
            "Neutral": [0.4, 0.6],
            "In favor": [0.6, 0.8],
            "Strongly in favor": [0.8, 1.0]
        }
        
        # Move from Neutral away from In favor
        label, value = shift_class("Neutral", "In favor", Direction.DISAGREE, opinion_groups)
        assert label == "Against"
        assert abs(value - 0.3) < 0.001
    
    def test_shift_class_same(self):
        """Test no shift when opinions are the same."""
        opinion_groups = {
            "Strongly against": [0.0, 0.2],
            "Against": [0.2, 0.4],
            "Neutral": [0.4, 0.6],
            "In favor": [0.6, 0.8],
            "Strongly in favor": [0.8, 1.0]
        }
        
        # Same opinion class - no shift
        label, value = shift_class("Neutral", "Neutral", Direction.AGREE, opinion_groups)
        assert label == "Neutral"
        assert abs(value - 0.5) < 0.001
    
    def test_shift_class_boundary_clamping(self):
        """Test that shifts are clamped at boundaries."""
        opinion_groups = {
            "Strongly against": [0.0, 0.2],
            "Against": [0.2, 0.4],
            "Neutral": [0.4, 0.6],
            "In favor": [0.6, 0.8],
            "Strongly in favor": [0.8, 1.0]
        }
        
        # At the top, can't go higher even when disagreeing with someone below
        label, value = shift_class("Strongly in favor", "Against", Direction.DISAGREE, opinion_groups)
        assert label == "Strongly in favor"
        
        # At the bottom, can't go lower even when disagreeing with someone above
        label, value = shift_class("Strongly against", "In favor", Direction.DISAGREE, opinion_groups)
        assert label == "Strongly against"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
