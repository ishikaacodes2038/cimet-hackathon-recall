"""Do-Not-Call gate — stubbed per the brief ("Assume a DNC check gates
dialling (ACMA register). You may stub it — but show where it sits.").

Real integration would call the ACMA Do Not Call Register API before ANY
outbound dial is placed. Here we simulate it against an in-memory registry
so the gate's position in the flow (before Call Initiation) is demonstrable.

The registry is also writable: "Don't call me again" is a no-contact
request, not just a reason to end the current call — per the brief's
"respect no" guardrail, that preference must be logged so it's respected on
the *next* dropout-recovery attempt too, not only this one.
"""

# Synthetic test numbers only, per the "test data only" guardrail. Seeded
# entries simulate numbers already on the register before the demo starts;
# add_to_dnc() adds to this same set at runtime when a customer refuses.
_dnc_registry: set[str] = {"+61400000001", "+61400000099"}


def check_dnc(phone_number: str) -> bool:
    """Returns True if the number is CLEAR to call, False if it's DNC-listed."""
    return phone_number not in _dnc_registry


def add_to_dnc(phone_number: str) -> None:
    """Logs a no-contact request so future recovery attempts respect it."""
    _dnc_registry.add(phone_number)


def is_on_dnc(phone_number: str) -> bool:
    return phone_number in _dnc_registry
