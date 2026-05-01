from .timeline import plot_time_line
from .converter import convert_oir_to_qasm, convert_qasm_to_oir
from .compiler import compile, TranspilerConfig, CompilationResult


def draw(*args, **kwargs):
    """Lazy import for draw function to avoid hard dependency on pyqpanda3."""
    from .draw import draw as _draw
    return _draw(*args, **kwargs)