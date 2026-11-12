import pytest

from onco_research_ai.agent.citations import (
    Source,
    check_citations,
    unsupported_numbers,
)
from onco_research_ai.agent.sql_tool import UnsafeSQL, validate


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE trials",
        "DELETE FROM trials",
        "SELECT 1; DELETE FROM trials",
        "UPDATE trials SET enrollment = 0",
        "SELECT * FROM pg_user",
        "INSERT INTO drugs (canonical_name) VALUES ('x')",
    ],
)
def test_sql_tool_blocks_unsafe_queries(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql)


def test_sql_tool_adds_limit_and_allows_ctes():
    assert validate("select nct_id from trials").endswith("LIMIT 50")
    validate("with x as (select nct_id from trials) select count(*) from x")


def _src(ref):
    return Source(ref=ref, doc_id=ref, source="trial", title="t", url="u", text="x")


def test_check_citations_flags_invalid_and_uncited():
    answer = (
        "Encorafenib improved survival in the COLUMBUS trial [S1]. "
        "It was also approved for many other cancers worldwide [S9]. "
        "This sentence has no citation at all but is long enough."
    )
    c = check_citations(answer, [_src("S1"), _src("S2")], has_sql=False)
    assert c["cited"] == ["S1"]
    assert c["invalid"] == ["S9"]
    assert len(c["uncited_sentences"]) == 1


def test_unsupported_numbers_catches_invented_totals():
    context = "drug | status | n\ndabrafenib | COMPLETED | 5\nvemurafenib | COMPLETED | 7\nPFS 14,9 months"
    assert unsupported_numbers(
        "There are 13 trials: 5 [SQL] and 7 [SQL]; PFS 14.9 [S2].", context
    ) == ["13"]
