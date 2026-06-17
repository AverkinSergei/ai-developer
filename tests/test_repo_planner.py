import json

from app.clients.fakes import FakeBitrix, FakeLLM
from app.config import Settings
from app.contracts import TaskCard
from app.orchestrator import intake_task
from app.repo_planner import classify_repos

FIELD_MAP = {
    "task_type": "ufType",
    "target_repo": "ufRepo",
    "target_repos": "ufRepos",
    "context_repos": "ufCtx",
}
S = Settings(bitrix_field_map=FIELD_MAP)


async def test_classify_repos_parses_mismatches():
    llm = FakeLLM(
        responses=[
            json.dumps(
                {
                    "change_repos": ["grp/a", "grp/b"],
                    "context_repos": [],
                    "mismatches": ["grp/b помечен как контекст, но требует изменений"],
                }
            )
        ]
    )
    card = TaskCard(task_id="B24-1", task_type="feature", target_repo="grp/a")
    res = await classify_repos(card, llm)
    assert res.mismatches == ["grp/b помечен как контекст, но требует изменений"]


async def test_classify_repos_bad_json_empty():
    card = TaskCard(task_id="B24-1", task_type="feature", target_repo="grp/a")
    res = await classify_repos(card, FakeLLM(responses=["не json"]))
    assert res.mismatches == []


async def test_intake_posts_repo_mismatch_comment(db_session):
    raw = {"ufType": "feature", "ufRepo": "grp/a", "ufRepos": ["grp/b"], "createdBy": "u-a"}
    bitrix = FakeBitrix(tasks={"B24-1": raw})
    llm = FakeLLM(
        responses=[
            json.dumps(
                {"change_repos": ["grp/a"], "context_repos": [], "mismatches": ["grp/b лишний"]}
            )
        ]
    )
    await intake_task(
        db_session, task_id="B24-1", raw_fields=raw, text="", bitrix=bitrix, llm=llm, settings=S
    )
    assert any("[AI_REPO_CHECK]" in c["text"] for c in bitrix.comments)


async def test_intake_single_repo_skips_classification(db_session):
    raw = {"ufType": "feature", "ufRepo": "grp/a", "createdBy": "u-a"}
    bitrix = FakeBitrix(tasks={"B24-1": raw})
    llm = FakeLLM(responses=[json.dumps({"mismatches": ["не должно вызваться"]})])
    await intake_task(
        db_session, task_id="B24-1", raw_fields=raw, text="", bitrix=bitrix, llm=llm, settings=S
    )
    assert not any("[AI_REPO_CHECK]" in c["text"] for c in bitrix.comments)
    assert llm.calls == []  # классификация не запускалась
