from app.simulation.runtime_observability import ResourceTrace, collect_runtime_context


def test_collect_runtime_context_includes_cpu_and_memory() -> None:
    context = collect_runtime_context()

    assert "cpu" in context
    assert "memory" in context
    assert "env" in context


def test_resource_trace_records_stage_samples() -> None:
    trace = ResourceTrace()

    samples = trace.sample("data_loading")

    assert len(samples) == 1
    assert samples[0]["stage"] == "data_loading"
    assert samples[0]["elapsed_seconds"] >= 0
    assert samples[0]["threads"] >= 1
