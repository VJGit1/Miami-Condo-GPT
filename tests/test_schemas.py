from condo_gpt.schemas import AgentResponse, ChartArtifact, ChartDataset, SqlCitation


def test_agent_response_display_includes_citations():
    resp = AgentResponse(
        text="<p>hi</p>",
        artifacts=[
            ChartArtifact(
                labels=["a"],
                datasets=[ChartDataset(label="s", data=[1.0])],
            )
        ],
        sql_citations=[SqlCitation(query="SELECT 1", blocked=False)],
        prompt_version="test",
    )
    blocks = resp.display_blocks()
    joined = "\n".join(str(b) for b in blocks)
    assert "SQL citations" in joined
    assert "SELECT 1" in joined
    assert "run_id" in joined
