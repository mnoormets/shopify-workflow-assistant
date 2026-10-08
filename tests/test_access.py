from fastapi.testclient import TestClient
from backend.api import create_app
import pytest

KEY = "test-only-key-" + "x" * 32

@pytest.fixture
def client():
    with TestClient(create_app("sqlite://", operator_key=KEY)) as c:
        yield c

@pytest.mark.parametrize("method,path", [("get","/api/findings"),("get","/api/policy"),("get","/api/events"),("get","/api/incidents"),("post","/api/demo"),("post","/api/incidents/sync"),("put","/api/policy")])
def test_missing_or_wrong_key_blocks_reads_and_mutations(client,method,path):
    assert getattr(client,method)(path).status_code == 401
    assert getattr(client,method)(path,headers={"X-Operator-Key":"incorrect"}).status_code == 401


def test_valid_key_and_trusted_audit_identity(client):
    client.headers["X-Operator-Key"] = KEY
    assert client.post("/api/demo").status_code == 200
    assert client.post("/api/incidents/sync").status_code == 200
    row=client.get("/api/incidents").json()["incidents"][0]
    path="/api/incidents/"+row["incident_id"]
    result=client.patch(path,json={"revision":row["revision"],"status":"investigating","owner":"reviewer","actor":"forged-director","note":"Checked synthetic evidence."})
    assert result.status_code == 200
    history=client.get(path).json()["history"]
    assert history[-1]["actor"] == "local-operator"
    assert "forged-director" not in str(history)
    assert client.get(path).headers["cache-control"] == "no-store"


def test_health_is_public_and_never_exposes_key(client):
    response=client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["operator_auth"] is True
    assert KEY not in response.text


def test_webhook_retains_separate_signature_validation():
    with TestClient(create_app("sqlite://",operator_key=KEY,webhook_secret="webhook-test-secret",allowed_shop="test.myshopify.com")) as c:
        r=c.post("/api/webhooks/shopify",content=b"{}",headers={"X-Operator-Key":KEY,"X-Shopify-Shop-Domain":"test.myshopify.com","X-Shopify-Hmac-Sha256":"wrong"})
        assert r.status_code in (400,401,403)

@pytest.mark.parametrize("key",["", "short", " " + KEY, KEY + " "])
def test_invalid_explicit_key_fails_closed(key):
    with pytest.raises(ValueError):create_app("sqlite://",operator_key=key)


def test_demo_mode_still_works_without_key(monkeypatch):
    monkeypatch.delenv("SHOPIFY_OPS_OPERATOR_KEY",raising=False)
    with TestClient(create_app("sqlite://")) as c:
        assert c.get("/api/health").json()["operator_auth"] is False
        assert c.post("/api/demo").status_code == 200
