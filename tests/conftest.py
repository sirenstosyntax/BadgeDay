from pathlib import Path

import pytest

from app.config import Settings, get_settings

# Tests must not read the developer's .env. Whatever is in it — real credentials, a
# half-finished edit, a value pasted into the wrong variable — must not decide whether
# the suite passes. Disabling the dotenv read here happens before any test module
# imports app.main, which builds Settings at import time.
Settings.model_config["env_file"] = None
get_settings.cache_clear()

from app.ingest.analyzer import FixtureDocumentAnalyzer  # noqa: E402
from app.ingest.models import AnalyzedDocument  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def analyzer() -> FixtureDocumentAnalyzer:
    return FixtureDocumentAnalyzer(FIXTURE_DIR)


@pytest.fixture
def synthetic_sog(analyzer: FixtureDocumentAnalyzer) -> AnalyzedDocument:
    """Decimal-numbered guideline: 304.1, 304.2, 304.2.1."""
    return analyzer.analyze(Path("synthetic_sog.pdf"))


@pytest.fixture
def synthetic_outline_sog(analyzer: FixtureDocumentAnalyzer) -> AnalyzedDocument:
    """Lettered-outline guideline: named headings, then A. / 1. / a. / i."""
    return analyzer.analyze(Path("synthetic_outline_sog.pdf"))
