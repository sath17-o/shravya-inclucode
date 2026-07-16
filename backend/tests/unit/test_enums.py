from app.contracts.enums import STUDENT_CONCEPT_STATE_LABELS, ConceptState


def test_student_concept_state_labels_are_presentation_text_not_enum_values() -> None:
    assert STUDENT_CONCEPT_STATE_LABELS[ConceptState.UNSURE] == "Not sure yet"
    assert ConceptState.UNSURE.value == "unsure"
