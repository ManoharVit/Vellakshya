"""
Comprehensive Phase 3 Test Suite: Real-Time WebSocket Collaboration & Presence Synchronization.
Tests two-user live synchronization, room state snapshots, presence updates,
synchronized comments with bounding box geometry, annotation broadcasting,
multi-room isolation, ping/pong heartbeats, and offline action reconciliation.
"""

from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_sample_pdf(num_pages: int = 2) -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"Collab PDF - Page {i + 1}", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def test_two_user_realtime_presence_and_cursor():
    r"""
    Validates Guidebook Milestone 4: Two-user real-time collaboration test.
    User A and User B connect simultaneously to the same document room:
    - User A receives initial room snapshot.
    - User B joins -> User A receives user_joined notification.
    - User B sends presence update -> User A receives live page and cursor updates.
    - User B disconnects -> User A receives user_left notification.
    """
    room_id = "doc-sync-alpha"

    with client.websocket_connect(f"/ws/documents/{room_id}?user_id=alice&name=Alice") as ws_alice:
        # 1. Alice connects and receives initial room snapshot
        state_alice = ws_alice.receive_json()
        assert state_alice["type"] == "room_state"
        assert state_alice["doc_id"] == room_id
        assert len(state_alice["users"]) == 1
        assert state_alice["users"][0]["user_id"] == "alice"

        with client.websocket_connect(f"/ws/documents/{room_id}?user_id=bob&name=Bob") as ws_bob:
            # 2. Bob connects and receives snapshot containing both Alice and Bob
            state_bob = ws_bob.receive_json()
            assert state_bob["type"] == "room_state"
            assert len(state_bob["users"]) == 2
            user_ids = {u["user_id"] for u in state_bob["users"]}
            assert user_ids == {"alice", "bob"}

            # 3. Alice receives user_joined notification for Bob
            join_event = ws_alice.receive_json()
            assert join_event["type"] == "user_joined"
            assert join_event["user"]["user_id"] == "bob"
            assert join_event["user"]["display_name"] == "Bob"
            assert "color" in join_event["user"]

            # 4. Bob moves to page 2 and moves mouse cursor
            ws_bob.send_json(
                {
                    "type": "presence",
                    "page_no": 2,
                    "cursor": {"x": 185.5, "y": 420.0},
                }
            )

            # 5. Alice receives presence_update event
            pres_event = ws_alice.receive_json()
            assert pres_event["type"] == "presence_update"
            assert pres_event["user_id"] == "bob"
            assert pres_event["page_no"] == 2
            assert pres_event["cursor"] == {"x": 185.5, "y": 420.0}

        # 6. Bob disconnects (exiting with block) -> Alice receives user_left
        leave_event = ws_alice.receive_json()
        assert leave_event["type"] == "user_left"
        assert leave_event["user_id"] == "bob"


def test_realtime_comment_and_annotation_broadcasting():
    r"""
    Validates synchronized comment and drawing annotation delivery across active peers.
    """
    room_id = "doc-sync-annotations"

    with client.websocket_connect(f"/ws/documents/{room_id}?user_id=charlie&name=Charlie") as ws_c:
        ws_c.receive_json()  # room_state

        with client.websocket_connect(f"/ws/documents/{room_id}?user_id=diana&name=Diana") as ws_d:
            ws_d.receive_json()  # room_state
            ws_c.receive_json()  # user_joined Diana

            # 1. Charlie adds a contextual comment with bounding box
            ws_c.send_json(
                {
                    "type": "comment",
                    "page_no": 1,
                    "anchor": {"x": 72.0, "y": 140.0, "w": 200.0, "h": 50.0},
                    "body": "Header font weight requires WCAG 2.2 AA audit.",
                }
            )

            # Both peers receive the comment broadcast
            c_msg = ws_c.receive_json()
            d_msg = ws_d.receive_json()
            assert c_msg["type"] == "comment_added"
            assert d_msg["type"] == "comment_added"
            assert d_msg["comment"]["author_id"] == "charlie"
            assert d_msg["comment"]["page_no"] == 1
            assert d_msg["comment"]["anchor"] == {"x": 72.0, "y": 140.0, "w": 200.0, "h": 50.0}
            assert "WCAG 2.2" in d_msg["comment"]["body"]

            # 2. Diana broadcasts a drawing overlay (highlight)
            ws_d.send_json(
                {
                    "type": "annotation",
                    "page_no": 2,
                    "tool": "highlight",
                    "data": {"rect": [50, 100, 300, 130], "color": "#FACC15"},
                }
            )

            annot_c = ws_c.receive_json()
            annot_d = ws_d.receive_json()
            assert annot_c["type"] == "annotation_drawn"
            assert annot_d["type"] == "annotation_drawn"
            assert annot_c["user_id"] == "diana"
            assert annot_c["annotation"]["tool"] == "highlight"


def test_multi_room_isolation():
    r"""
    Validates multi-tenant / multi-document boundary isolation.
    Events in Room A MUST NEVER leak into Room B.
    """
    room_a = "doc-isolated-A"
    room_b = "doc-isolated-B"

    with client.websocket_connect(f"/ws/documents/{room_a}?user_id=userA&name=UserA") as ws_a:
        ws_a.receive_json()  # room_state A

        with client.websocket_connect(f"/ws/documents/{room_b}?user_id=userB&name=UserB") as ws_b:
            state_b = ws_b.receive_json()  # room_state B
            # Room B should only contain userB
            assert len(state_b["users"]) == 1
            assert state_b["users"][0]["user_id"] == "userB"

            # userA performs action in Room A
            ws_a.send_json(
                {
                    "type": "presence",
                    "page_no": 5,
                    "cursor": {"x": 50, "y": 50},
                }
            )

            # Send ping on userB to confirm no leaked messages in ws_b queue
            ws_b.send_json({"type": "ping"})
            pong = ws_b.receive_json()
            assert pong["type"] == "pong", "User B should only receive pong, not Room A events"


def test_websocket_heartbeat_ping_pong():
    r"""
    Validates keep-alive heartbeat ping/pong mechanism.
    """
    room_id = "doc-heartbeat"
    with client.websocket_connect(f"/ws/documents/{room_id}?user_id=ping_user") as ws:
        ws.receive_json()  # room_state
        ws.send_json({"type": "ping"})
        res = ws.receive_json()
        assert res["type"] == "pong"
        assert "timestamp" in res


def test_active_collaborators_rest_endpoint():
    r"""
    Validates GET /api/v2/documents/{doc_id}/collaborators query.
    """
    room_id = "doc-roster-check"

    # Initially empty
    res0 = client.get(f"/api/v2/documents/{room_id}/collaborators")
    assert res0.status_code == 200
    assert res0.json()["count"] == 0

    with client.websocket_connect(f"/ws/documents/{room_id}?user_id=emma&name=Emma") as ws:
        ws.receive_json()  # room_state

        # Now active
        res1 = client.get(f"/api/v2/documents/{room_id}/collaborators")
        assert res1.status_code == 200
        data = res1.json()
        assert data["count"] == 1
        assert data["collaborators"][0]["user_id"] == "emma"
        assert data["collaborators"][0]["display_name"] == "Emma"

    # Disconnected
    res2 = client.get(f"/api/v2/documents/{room_id}/collaborators")
    assert res2.status_code == 200
    assert res2.json()["count"] == 0


def test_offline_reconciliation_and_comment_merge_endpoints():
    r"""
    Validates offline sync replay and concurrent comment merging endpoints.
    """
    pdf_bytes = create_sample_pdf(num_pages=3)
    headers = {"X-User-Id": "collab_owner"}

    # 1. Create document
    create_res = client.post(
        "/api/v2/documents",
        headers=headers,
        data={"title": "Reconciliation Test"},
        files={"file": ("sync.pdf", pdf_bytes, "application/pdf")},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["document"]["id"]

    # 2. Test offline sync replay
    offline_actions = [
        {
            "type": "add_comment",
            "page": 1,
            "text": "Offline annotation notes",
            "author": "Field Worker",
        },
        {"type": "rotate_page", "page": 2, "angle": 90},
        {"type": "highlight", "page": 1, "text": "Collab"},
    ]
    sync_res = client.post(
        f"/api/v2/documents/{doc_id}/sync-offline",
        headers=headers,
        json={"actions": offline_actions, "baseVersion": 1},
    )
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["status"] == "reconciled"
    assert sync_data["actions_processed"] == 3
    assert sync_data["summary"]["status"] == "SYNCED"

    # 3. Test concurrent comment set merge
    comments_a = [
        {
            "id": "c1",
            "user": "Alice",
            "page": 1,
            "text": "Review title",
            "rect": [72, 72, 100, 100],
        },
        {"id": "c2", "user": "Alice", "page": 2, "text": "Check table", "rect": [72, 72, 100, 100]},
    ]
    comments_b = [
        {
            "id": "c2",
            "user": "Alice",
            "page": 2,
            "text": "Check table",
            "rect": [72, 72, 100, 100],
        },  # Duplicate
        {
            "id": "c3",
            "user": "Bob",
            "page": 1,
            "text": "Approve figure",
            "rect": [72, 72, 100, 100],
        },
    ]
    merge_res = client.post(
        f"/api/v2/documents/{doc_id}/merge-comments",
        headers=headers,
        json={"commentsUserA": comments_a, "commentsUserB": comments_b, "baseVersion": 1},
    )
    assert merge_res.status_code == 200
    merge_data = merge_res.json()
    assert merge_data["status"] == "merged"
    summary = merge_data["summary"]
    assert summary["total_comments_applied"] == 3  # c1, c2, c3 (duplicate c2 suppressed)
    assert summary["duplicates_suppressed"] == 1
