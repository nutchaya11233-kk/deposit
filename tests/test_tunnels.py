"""ทดสอบการแยกยูส, plugin ของ frps และสิทธิ์แอดมิน — ใช้ mongomock ไม่ต้องมี MongoDB จริง"""
import mongomock
import pytest

from server import auth, db as db_module, frp_plugin, tunnels
from server.app import create_app


@pytest.fixture
def db(monkeypatch):
    fake = mongomock.MongoClient().get_database("test")
    monkeypatch.setattr(db_module, "_db", fake)
    db_module.ensure_indexes()
    auth.create_user("admin", "admin-password", "admin")
    auth.create_user("alice", "alice-password", "staff")
    auth.create_user("bob.x", "bob-password", "staff")
    return fake


@pytest.fixture
def client(db):
    return create_app().test_client


def login(make_client, username, password):
    c = make_client()
    res = c.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return c


def login_content(db, user):
    return {"user": user, "metas": {"token": tunnels.get_token(db, user)}}


def proxy_content(db, user, name, kind="stcp", **extra):
    return {
        "user": {"user": user, "metas": {"token": tunnels.get_token(db, user)}},
        "proxy_name": f"{user}.{name}",
        "proxy_type": kind,
        **extra,
    }


def test_users_only_see_their_own_tunnels(client):
    alice = login(client, "alice", "alice-password")
    bob = login(client, "bob.x", "bob-password")
    tid = alice.post("/api/tunnels", json={"name": "device-01"}).get_json()["id"]
    bob.post("/api/tunnels", json={"name": "device-01"})

    assert [t["id"] for t in alice.get("/api/tunnels").get_json()["tunnels"]] == [tid]
    assert tid not in [t["id"] for t in bob.get("/api/tunnels").get_json()["tunnels"]]
    assert bob.get(f"/api/tunnels/{tid}/setup").status_code == 400
    assert bob.get(f"/api/tunnels/{tid}/frpc.toml").status_code == 400
    assert bob.delete(f"/api/tunnels/{tid}").status_code == 400
    assert len(alice.get("/api/tunnels").get_json()["tunnels"]) == 1


def test_admin_sees_only_own_tunnels(client):
    alice = login(client, "alice", "alice-password")
    admin = login(client, "admin", "admin-password")
    tid = alice.post("/api/tunnels", json={"name": "d1"}).get_json()["id"]
    assert admin.get("/api/tunnels").get_json()["tunnels"] == []
    assert admin.get(f"/api/tunnels/{tid}/setup").status_code == 400


def test_tokens_are_per_user_and_rotate_alone(client, db):
    alice = login(client, "alice", "alice-password")
    bob = login(client, "bob.x", "bob-password")
    a1 = alice.get("/api/tunnels/token").get_json()["token"]
    b1 = bob.get("/api/tunnels/token").get_json()["token"]
    assert a1 != b1
    alice.post("/api/tunnels/token/rotate")
    assert alice.get("/api/tunnels/token").get_json()["token"] != a1
    assert bob.get("/api/tunnels/token").get_json()["token"] == b1


def test_only_admin_manages_users_and_new_user_can_login(client):
    alice = login(client, "alice", "alice-password")
    assert alice.post("/api/users", json={"username": "x1", "password": "x" * 10}).status_code == 403
    admin = login(client, "admin", "admin-password")
    assert admin.post("/api/users", json={"username": "carol", "password": "carol-password"}).status_code == 201
    login(client, "carol", "carol-password")


def test_deleting_user_removes_tunnels_and_access(client, db):
    alice = login(client, "alice", "alice-password")
    alice.post("/api/tunnels", json={"name": "d1"})
    content = login_content(db, "alice")
    assert frp_plugin.handle(db, "Login", content) == frp_plugin.ALLOW

    admin = login(client, "admin", "admin-password")
    assert admin.delete("/api/users/alice").status_code == 200
    assert db["tunnels"].count_documents({"owner": "alice"}) == 0
    assert frp_plugin.handle(db, "Login", content)["reject"] is True


def test_plugin_login(db):
    assert frp_plugin.handle(db, "Login", login_content(db, "alice")) == frp_plugin.ALLOW
    assert frp_plugin.handle(db, "Login", {"user": "alice", "metas": {"token": "wrong"}})["reject"]
    assert frp_plugin.handle(db, "Login", {"user": "alice", "metas": {}})["reject"]
    assert frp_plugin.handle(db, "Login", {"user": "", "metas": {"token": ""}})["reject"]
    # ใช้ token ของคนอื่นปลอมเป็นยูสนี้ไม่ได้
    other = tunnels.get_token(db, "bob.x")
    assert frp_plugin.handle(db, "Login", {"user": "alice", "metas": {"token": other}})["reject"]
    assert frp_plugin.handle(db, "Ping", login_content(db, "alice"))["reject"]


def test_plugin_new_proxy(db):
    tunnels.create(db, "alice", {"name": "d1"})
    assert frp_plugin.handle(db, "NewProxy", proxy_content(db, "alice", "d1")) == frp_plugin.ALLOW
    assert frp_plugin.handle(db, "NewProxy", proxy_content(db, "alice", "nope"))["reject"]
    # ยูสอื่นเปิดชื่อเดียวกันไม่ได้ถ้ายังไม่ได้สร้างเอง
    assert frp_plugin.handle(db, "NewProxy", proxy_content(db, "bob.x", "d1"))["reject"]
    # เปิด private ให้กลายเป็นพอร์ต public ไม่ได้
    assert frp_plugin.handle(db, "NewProxy", proxy_content(db, "alice", "d1", "tcp", remote_port=20000))["reject"]
    # ชื่อ proxy ที่ไม่ขึ้นต้นด้วยยูสตัวเอง
    content = proxy_content(db, "bob.x", "d1")
    content["proxy_name"] = "alice.d1"
    assert frp_plugin.handle(db, "NewProxy", content)["reject"]


def test_plugin_public_port_must_match(db, monkeypatch):
    monkeypatch.setattr(tunnels, "TUNNEL_PUBLIC_ENABLED", True)
    tunnels.create(db, "alice", {"name": "pub", "mode": "public"})
    port = db["tunnels"].find_one({"name": "pub"})["remote_port"]
    ok = proxy_content(db, "alice", "pub", "tcp", remote_port=port)
    assert frp_plugin.handle(db, "NewProxy", ok) == frp_plugin.ALLOW
    bad = proxy_content(db, "alice", "pub", "tcp", remote_port=port + 1)
    assert frp_plugin.handle(db, "NewProxy", bad)["reject"]


def test_public_mode_is_off_by_default(db):
    with pytest.raises(tunnels.TunnelError):
        tunnels.create(db, "alice", {"name": "pub", "mode": "public"})


def test_plugin_route_needs_secret_and_fails_closed(client, db):
    c = client()
    assert c.post("/internal/frp/wrong?op=Login", json={"content": {}}).status_code == 404
    secret = tunnels.plugin_secret(db)
    res = c.post(f"/internal/frp/{secret}?op=Login", json={"content": login_content(db, "alice")})
    assert res.get_json() == frp_plugin.ALLOW
    res = c.post(f"/internal/frp/{secret}?op=Login", data="not json")
    assert res.get_json()["reject"] is True


def test_rejects_shell_breaking_local_ip(db):
    with pytest.raises(tunnels.TunnelError):
        tunnels.create(db, "alice", {"name": "d1", "localIp": "127.0.0.1'; rm -rf ~"})


def test_tunnel_quota(db, monkeypatch):
    monkeypatch.setattr(tunnels, "TUNNEL_MAX_PER_USER", 1)
    tunnels.create(db, "alice", {"name": "d1"})
    with pytest.raises(tunnels.TunnelError):
        tunnels.create(db, "alice", {"name": "d2"})
    tunnels.create(db, "bob.x", {"name": "d1"})


def test_generated_config(db, monkeypatch):
    monkeypatch.setattr(tunnels, "TUNNEL_TRANSPORT", "wss")
    monkeypatch.setattr(tunnels, "TUNNEL_SERVER_HOST", "frp.example.com")
    monkeypatch.setattr(tunnels, "TUNNEL_SERVER_PORT", 443)
    tid = tunnels.create(db, "alice", {"name": "d1"})
    doc = tunnels.get(db, "alice", tid)

    frpc = tunnels.frpc_toml(db, doc)
    assert 'transport.protocol = "wss"' in frpc
    assert 'user = "alice"' in frpc
    assert 'type = "stcp"' in frpc
    assert "remotePort" not in frpc
    assert doc["secret_key"] in frpc

    visitor = tunnels.visitor_toml(db, doc)
    assert 'serverName = "d1"' in visitor
    assert "bindPort = 15555" in visitor
    assert tunnels.serialize(doc)["endpoint"] == "127.0.0.1:15555"

    frps = tunnels.render_frps_toml(db)
    assert 'bindAddr = "127.0.0.1"' in frps
    assert f'/internal/frp/{tunnels.plugin_secret(db)}' in frps
    assert 'ops = ["Login", "NewProxy"]' in frps


def test_bootstrap_admin_only_when_empty(db):
    assert auth.bootstrap_admin("root", "root-password") is False
    db["users"].delete_many({})
    assert auth.bootstrap_admin("root", "root-password") is True
    assert auth.verify("root", "root-password") == "admin"
    assert auth.bootstrap_admin("second", "second-password") is False
