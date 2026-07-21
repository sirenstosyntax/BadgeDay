from pathlib import Path

import pytest

from app.ingest.analyzer import FixtureDocumentAnalyzer
from app.ingest.models import AnalyzedDocument

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def analyzer() -> FixtureDocumentAnalyzer:
    return FixtureDocumentAnalyzer(FIXTURE_DIR)


@pytest.fixture
def synthetic_sog(analyzer: FixtureDocumentAnalyzer) -> AnalyzedDocument:
    return analyzer.analyze(Path("synthetic_sog.pdf"))
