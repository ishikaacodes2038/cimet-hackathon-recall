from app.services.script_loader import load_energy_script
from app.state.machine import JourneyStateMachine


def make_machine(prefilled=None, last_completed_step=None):
    script = load_energy_script()
    return JourneyStateMachine.start(
        lead_id="LEAD-1",
        session_id="SESSION-1",
        script=script,
        prefilled_fields=prefilled or {},
        last_completed_step=last_completed_step,
    )


def test_script_loads_and_has_required_fields():
    script = load_energy_script()
    assert script.vertical == "energy"
    assert "full_name" in script.fields
    assert "life_support_status" in script.fields
    assert script.fields["life_support_status"].escalate_on_values == ["yes"]


def test_prefilled_fields_are_not_reasked():
    machine = make_machine(prefilled={"full_name": "Priya Sharma"})
    next_field = machine.get_next_required_field()
    assert next_field.field != "full_name"
    assert "full_name" not in machine.state.missing_fields


def test_apply_valid_field_value_advances_step():
    machine = make_machine()
    result = machine.apply_field_value("full_name", "Priya Sharma", confidence=0.95, evidence="stated name")
    assert result.accepted
    assert machine.state.collected_fields["full_name"].value == "Priya Sharma"


def test_apply_invalid_field_value_does_not_accept():
    machine = make_machine()
    result = machine.apply_field_value("property_type", "somewhere nice", confidence=0.4, evidence="unclear")
    assert not result.accepted
    # apply_field_value only validates; retry bookkeeping is the orchestrator's
    # job (via record_retry) so it can apply the same accounting whether the
    # failure was "invalid candidate" or "no candidate extracted at all".
    assert machine.state.retry_counts.get("property_type", 0) == 0


def test_retries_exhausted_after_max():
    machine = make_machine()
    for _ in range(2):
        machine.record_retry("property_type")
    assert machine.retries_exhausted("property_type")


def test_optional_field_can_be_skipped_after_max_retries():
    machine = make_machine()
    field = machine.script.fields["nmi_or_mirn"]
    assert not field.required
    for _ in range(field.max_retries):
        machine.record_retry("nmi_or_mirn")
    assert machine.retries_exhausted("nmi_or_mirn")
    machine.skip_optional_field("nmi_or_mirn", reason="customer didn't have it")
    assert "nmi_or_mirn" not in machine.state.missing_fields
    assert machine.state.collected_fields["nmi_or_mirn"].value is None


def test_life_support_yes_flags_escalation():
    machine = make_machine()
    result = machine.apply_field_value("life_support_status", "yes", confidence=0.9, evidence="said yes")
    assert result.accepted
    assert result.escalate_value is True


def test_journey_complete_when_all_required_fields_collected():
    machine = make_machine()
    required = machine.script.required_field_names()
    for name in required:
        field_script = machine.script.fields[name]
        vtype = field_script.validation.type
        if vtype == "yes_no":
            value = "no"
        elif vtype == "enum":
            value = field_script.validation.options[0]
        elif vtype == "date":
            value = "14/03/1990"
        else:
            value = "test value"
        machine.apply_field_value(name, value, confidence=0.9, evidence="test")
    assert machine.is_ready_for_confirmation()
