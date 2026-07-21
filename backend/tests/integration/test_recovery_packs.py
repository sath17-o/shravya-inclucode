from datetime import UTC, datetime

from sqlalchemy import func, select

from app.contracts.enums import TeacherReviewStatus
from app.demo.photosynthesis_fixture import (
    CONTEXT_V1_ID,
    CONTEXT_V2_ID,
    COURSE_ID,
    seed_photosynthesis_demo,
)
from app.models.foundation import ConceptRecoveryPack, CourseContextVersion
from app.repositories.curriculum import CurriculumRepository
from app.services.context_versioning import ContextVersioningService


def test_fixture_recovery_packs_are_version_scoped_and_student_safe(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        packs = list(
            session.scalars(
                select(ConceptRecoveryPack).order_by(
                    ConceptRecoveryPack.context_version_id, ConceptRecoveryPack.id
                )
            )
        )
        assert len(packs) == 10
        assert all(
            pack.teacher_review_status is TeacherReviewStatus.APPROVED
            for pack in packs
            if pack.context_version_id == CONTEXT_V1_ID
        )
        assert all(
            pack.teacher_review_status is TeacherReviewStatus.DRAFT
            for pack in packs
            if pack.context_version_id == CONTEXT_V2_ID
        )
        v1_text = "\n".join(
            value
            for pack in packs
            if pack.context_version_id == CONTEXT_V1_ID
            for value in (
                pack.cue_en,
                pack.cue_ml,
                pack.example_en,
                pack.example_ml,
                pack.alternate_explanation_en,
                pack.alternate_explanation_ml,
            )
        )
        v2_text = "\n".join(
            value
            for pack in packs
            if pack.context_version_id == CONTEXT_V2_ID
            for value in (
                pack.cue_en,
                pack.cue_ml,
                pack.example_en,
                pack.example_ml,
                pack.alternate_explanation_en,
                pack.alternate_explanation_ml,
            )
        )
        old_english_strings = (
            "The leaf receives water and carbon dioxide before photosynthesis continues.",
            "Chlorophyll captures sunlight in the leaf.",
            "Sunlight provides energy and Chlorophyll helps capture that light.",
            "The plant changes its inputs into glucose, a sugar used as food.",
            "Glucose is the food made by the plant during photosynthesis.",
        )
        corrected_recovery_text = (
            "Photosynthesis uses the water and carbon dioxide that reach the leaf.",
            "ഇലയിലെത്തുന്ന ജലവും കാർബൺ ഡൈ ഓക്സൈഡും പ്രകാശസംശ്ലേഷണത്തിൽ ഉപയോഗിക്കുന്നു.",
            "Chlorophyll in the leaf captures energy from sunlight.",
            "ഇലയിലെ ക്ലോറോഫിൽ സൂര്യപ്രകാശത്തിൽ നിന്നുള്ള ഊർജം പിടിച്ചെടുക്കുന്നു.",
            "Sunlight provides energy, and chlorophyll in the leaf captures that energy.",
            "സൂര്യപ്രകാശം ഊർജം നൽകുന്നു; ഇലയിലെ ക്ലോറോഫിൽ ആ ഊർജം പിടിച്ചെടുക്കുന്നു.",
            "The plant uses water and carbon dioxide to make glucose, a sugar it uses as food.",
            "സസ്യം ജലവും കാർബൺ ഡൈ ഓക്സൈഡും ഉപയോഗിച്ച് ഗ്ലൂക്കോസ് എന്ന പഞ്ചസാര നിർമ്മിക്കുന്നു; "
            "അത് സസ്യം ഭക്ഷണമായി ഉപയോഗിക്കുന്നു.",
            "Glucose is a sugar made during photosynthesis and used by the plant as food.",
            "പ്രകാശസംശ്ലേഷണത്തിൽ നിർമ്മിക്കുന്ന ഗ്ലൂക്കോസ് സസ്യം ഭക്ഷണമായി ഉപയോഗിക്കുന്ന ഒരു പഞ്ചസാരയാണ്.",
        )
        assert all(text not in v1_text for text in old_english_strings)
        assert "After glucose is made" not in v1_text
        assert "after food is made" not in v1_text.casefold()
        assert "as the photosynthesis process completes" not in v1_text
        corrected_input_cue = (
            "Follow water travelling from the roots and carbon dioxide entering "
            "through the stomata."
        )
        assert corrected_input_cue in v1_text
        assert (
            "വേരുകളിൽ നിന്ന് ഇലയിലേക്കെത്തുന്ന ജലവും സ്റ്റോമാറ്റയിലൂടെ ഇലയിലേക്ക് കടക്കുന്ന കാർബൺ ഡൈ ഓക്സൈഡും ശ്രദ്ധിക്കുക."
            in v1_text
        )
        assert "During photosynthesis, the leaf releases oxygen into the air." in v1_text
        assert "Notice oxygen leaving the leaf during photosynthesis." in v1_text
        assert "പ്രകാശസംശ്ലേഷണത്തിനിടെ ഇല ഓക്സിജൻ വായുവിലേക്ക് പുറത്തുവിടുന്നു." in v1_text
        assert (
            "Oxygen is released from the leaf while the plant makes food through photosynthesis."
            in v1_text
        )
        assert "പ്രകാശസംശ്ലേഷണത്തിലൂടെ സസ്യം ഭക്ഷണം നിർമ്മിക്കുമ്പോൾ ഇലയിൽ നിന്ന് ഓക്സിജൻ പുറത്തുവിടുന്നു." in v1_text
        assert all(text in v1_text for text in corrected_recovery_text)
        assert all(text in v2_text for text in corrected_recovery_text)
        assert "During photosynthesis, the leaf releases oxygen into the air." in v2_text

    visible = migrated_api.client.get(f"/api/v1/student/courses/{COURSE_ID}/lesson-overview")
    support = visible.json()["data"]["chapters"][0]["lessons"][0]["recovery_support"]
    assert [item["concept_id"] for item in support]
    assert all(
        set(item) == {"concept_id", "cue", "example", "alternate_explanation"}
        and set(item["cue"]) == {"english", "malayalam"}
        and set(item["example"]) == {"english", "malayalam"}
        and set(item["alternate_explanation"]) == {"english", "malayalam"}
        for item in support
    )
    support_text = "\n".join(str(item) for item in support)
    assert all(text not in support_text for text in old_english_strings)
    assert all(text in support_text for text in corrected_recovery_text)
    assert "chlorophil" not in str(support).casefold()

    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        assert session.scalar(select(func.count()).select_from(ConceptRecoveryPack)) == 10


def test_context_copy_rebinds_recovery_packs_to_new_concepts(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        repository = CurriculumRepository(session)
        source = repository.get_context_with_graph(CONTEXT_V1_ID)
        assert source is not None
        source_packs = {pack.concept.concept_key: pack for pack in source.recovery_packs}

        copied = ContextVersioningService(session, repository).create_draft_from_approved(
            CONTEXT_V1_ID
        )
        copied_graph = repository.get_context_with_graph(copied.id)
        assert copied_graph is not None
        copied_packs = {pack.concept.concept_key: pack for pack in copied_graph.recovery_packs}

        assert copied.id != source.id
        assert copied.teacher_review_status is TeacherReviewStatus.DRAFT
        assert set(copied_packs) == set(source_packs)
        assert {pack.id for pack in copied_packs.values()}.isdisjoint(
            {pack.id for pack in source_packs.values()}
        )
        for concept_key, source_pack in source_packs.items():
            copied_pack = copied_packs[concept_key]
            assert copied_pack.context_version_id == copied.id
            assert copied_pack.concept_id != source_pack.concept_id
            assert copied_pack.teacher_review_status is TeacherReviewStatus.DRAFT
            assert copied_pack.approved_at is None
            assert copied_pack.cue_en == source_pack.cue_en
            assert copied_pack.cue_ml == source_pack.cue_ml
            assert source_pack.context_version_id == CONTEXT_V1_ID
            assert source_pack.teacher_review_status is TeacherReviewStatus.APPROVED
            assert source_pack.approved_at is not None


def test_pack_approval_does_not_approve_context_or_project_partial_draft_set(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        pack = session.scalar(
            select(ConceptRecoveryPack).where(
                ConceptRecoveryPack.context_version_id == CONTEXT_V2_ID
            )
        )
        assert pack is not None
        pack_id = pack.id
        source_statuses = list(
            session.scalars(
                select(ConceptRecoveryPack.teacher_review_status).where(
                    ConceptRecoveryPack.context_version_id == CONTEXT_V1_ID
                )
            )
        )
    response = migrated_api.client.post(f"/api/v1/teacher/recovery-packs/{pack_id}/approve")
    assert response.status_code == 200
    with migrated_api.session_factory() as session:
        context = session.get(CourseContextVersion, CONTEXT_V2_ID)
        assert context is not None and context.teacher_review_status is TeacherReviewStatus.DRAFT
        assert (
            list(
                session.scalars(
                    select(ConceptRecoveryPack.teacher_review_status).where(
                        ConceptRecoveryPack.context_version_id == CONTEXT_V1_ID
                    )
                )
            )
            == source_statuses
        )
    visible = migrated_api.client.get(f"/api/v1/student/courses/{COURSE_ID}/lesson-overview")
    assert visible.json()["data"]["version_number"] == 1


def test_recovery_pack_approval_is_idempotent_and_isolated(migrated_api, monkeypatch) -> None:
    approved_at = datetime(2040, 1, 2, 3, 4, 5, tzinfo=UTC)
    monkeypatch.setattr("app.api.dependencies.utcnow", lambda: approved_at)
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        pack = session.scalar(
            select(ConceptRecoveryPack)
            .where(ConceptRecoveryPack.context_version_id == CONTEXT_V2_ID)
            .order_by(ConceptRecoveryPack.id)
        )
        assert pack is not None
        pack_id = pack.id
        other_states = {
            item.id: (item.teacher_review_status, item.approved_at)
            for item in session.scalars(
                select(ConceptRecoveryPack).where(ConceptRecoveryPack.id != pack_id)
            )
        }
        context = session.get(CourseContextVersion, CONTEXT_V2_ID)
        assert context is not None
        context_status = context.teacher_review_status

    student_before = migrated_api.client.get(
        f"/api/v1/student/courses/{COURSE_ID}/lesson-overview"
    ).json()["data"]
    first = migrated_api.client.post(f"/api/v1/teacher/recovery-packs/{pack_id}/approve")
    assert first.status_code == 200
    assert first.json()["data"]["teacher_review_status"] == "APPROVED"
    assert first.json()["data"]["approved_at"] == "2040-01-02T03:04:05"

    with migrated_api.session_factory() as session:
        approved = session.get(ConceptRecoveryPack, pack_id)
        assert approved is not None
        original_approved_at = approved.approved_at
        assert original_approved_at is not None

    repeated = migrated_api.client.post(f"/api/v1/teacher/recovery-packs/{pack_id}/approve")
    assert repeated.status_code == 200
    assert repeated.json()["data"]["approved_at"] == "2040-01-02T03:04:05"

    with migrated_api.session_factory() as session:
        approved = session.get(ConceptRecoveryPack, pack_id)
        assert approved is not None
        assert approved.teacher_review_status is TeacherReviewStatus.APPROVED
        assert approved.approved_at == original_approved_at
        assert {
            item.id: (item.teacher_review_status, item.approved_at)
            for item in session.scalars(
                select(ConceptRecoveryPack).where(ConceptRecoveryPack.id != pack_id)
            )
        } == other_states
        context = session.get(CourseContextVersion, CONTEXT_V2_ID)
        assert context is not None and context.teacher_review_status is context_status

    student_after = migrated_api.client.get(
        f"/api/v1/student/courses/{COURSE_ID}/lesson-overview"
    ).json()["data"]
    assert student_after == student_before
