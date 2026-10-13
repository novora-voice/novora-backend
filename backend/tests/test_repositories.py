from novora.adapters.repositories import (
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
)
from novora.core.enums import OverallStatus
from novora.core.models import EvaluationReport, EvaluationScenario

def test_scenario_repository_crud():
    repo = InMemoryScenarioRepository()
    scen = EvaluationScenario(
        id="scen_1",
        name="Order Verification",
        business_goal="Verify order status",
    )
    saved = repo.save(scen)
    assert saved.id == "scen_1"

    fetched = repo.get("scen_1")
    assert fetched is not None
    assert fetched.name == "Order Verification"

    assert repo.get("non_existent") is None
    assert len(repo.list_all()) == 1

def test_evaluation_repository_crud():
    repo = InMemoryEvaluationRepository()
    report = EvaluationReport(
        id="eval_1",
        scenario_id="scen_1",
        conversation_id="conv_1",
        overall_status=OverallStatus.PASS,
        summary="Passed",
        rule_results=[],
    )
    repo.save(report)

    fetched = repo.get("eval_1")
    assert fetched is not None
    assert fetched.overall_status == OverallStatus.PASS

    listed = repo.list_by_scenario("scen_1")
    assert len(listed) == 1
    assert len(repo.list_by_scenario("other_scen")) == 0
