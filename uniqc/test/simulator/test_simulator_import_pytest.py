"""Pytest tests for simulator module imports."""
import pytest
import warnings


class TestSimulatorImport:
    """Tests for simulator import behavior."""

    def test_simulator_imports_originir_simulator(self):
        """Test that OriginIR_Simulator is importable."""
        from uniqc.simulator import OriginIR_Simulator, OriginIR_NoisySimulator

        assert OriginIR_Simulator is not None
        assert OriginIR_NoisySimulator is not None

    def test_simulator_warning_on_missing_cpp(self):
        """Test that a warning is issued when uniqc_cpp is not available."""
        # This test verifies the warning message is correct
        # by re-importing the module with a clean slate
        import importlib
        import sys

        # Remove the module from cache if present
        if "uniqc.simulator" in sys.modules:
            del sys.modules["uniqc.simulator"]

        # Try to import and check the warning message
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import uniqc.simulator

            # Check if a warning was issued (only if C++ backend is missing)
            if len(w) > 0:
                assert "uniqc is not installed with UniqcCpp" in str(w[0].message)
