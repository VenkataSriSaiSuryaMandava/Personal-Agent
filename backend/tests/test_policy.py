import pytest
from aegis.policy import Action, DataClass, Decision, Request, evaluate


@pytest.mark.parametrize("data", [DataClass.PERSONAL, DataClass.SENSITIVE, DataClass.UNKNOWN])
def test_private_data_never_reaches_cloud(data):
    assert evaluate(Request(Action.CLOUD_INFERENCE, data, True)).decision is Decision.DENY


def test_default_deny():
    assert evaluate(Request(Action.PUBLIC_RESEARCH, DataClass.PUBLIC)).decision is Decision.DENY


def test_public_inference_with_grant():
    assert evaluate(Request(Action.CLOUD_INFERENCE, DataClass.PUBLIC, True)).decision is Decision.ALLOW


@pytest.mark.parametrize("action", [Action.EXTERNAL_DISCLOSURE, Action.SEND_MESSAGE, Action.SUBMIT_APPLICATION, Action.TERMINAL, Action.HIGH_RISK])
def test_risky_actions_need_approval(action):
    assert evaluate(Request(action, DataClass.PERSONAL, True)).decision is Decision.APPROVAL_REQUIRED


def test_emergency_stop():
    assert evaluate(Request(Action.CLOUD_INFERENCE, DataClass.PUBLIC, True, stopped=True)).decision is Decision.DENY


def test_demo_isolation():
    assert evaluate(Request(Action.LOCAL_READ, DataClass.SYNTHETIC, True, demo=True)).decision is Decision.DENY
    assert evaluate(Request(Action.CLOUD_INFERENCE, DataClass.SYNTHETIC, True, demo=True)).decision is Decision.ALLOW


def test_sensitive_local_read():
    assert evaluate(Request(Action.LOCAL_READ, DataClass.SENSITIVE, True)).decision is Decision.APPROVAL_REQUIRED
