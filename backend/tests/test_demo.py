import pytest
from fastapi.testclient import TestClient
from aegis.demo import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    result = client.get('/health')
    assert result.status_code == 200
    assert result.json() == {'status': 'ok', 'mode': 'public_demo'}
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('example_id', ['search', 'systems', 'project'])
def test_fixed_examples(client, example_id):
    result = client.get('/example', params={'id': example_id})
    assert result.status_code == 200
    assert result.json()['mode'] == 'recorded_demo'
    assert result.json()['prompt']
    assert result.json()['answer']


@pytest.mark.parametrize('query', ['', '?id=invalid', '?id=search&id=project', '?id=search&message=secret'])
def test_rejects_unknown_input(client, query):
    result = client.get('/example' + query)
    assert result.status_code == 400
    assert 'secret' not in result.text


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/v1/status'), ('POST', '/api/v1/chat'),
    ('POST', '/api/v1/conversation'), ('POST', '/api/v1/inference'),
    ('POST', '/api/v1/auth/login'), ('GET', '/api/v1/auth/session'),
    ('POST', '/api/v1/auth/logout'), ('GET', '/docs'),
    ('GET', '/openapi.json'), ('POST', '/example'),
])
def test_private_routes_not_available(client, method, path):
    assert client.request(method, path).status_code in (404, 405)
