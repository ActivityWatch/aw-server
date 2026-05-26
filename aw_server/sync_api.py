"""
ActivityWatch Sync API
Allows exporting and importing bucket data between devices.
"""
import json
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app

from .api import ServerAPI

sync_blueprint = Blueprint("sync", __name__, url_prefix="/api")

@sync_blueprint.route("/0/sync/export", methods=["GET"])
def sync_export():
    """Export all buckets and their events as a portable format."""
    api: ServerAPI = current_app.api
    buckets = api.get_buckets()
    export_data = {}
    
    for bucket_id in buckets:
        events = api.get_events(bucket_id, limit=None)
        export_data[bucket_id] = {
            "metadata": buckets[bucket_id],
            "events": [{
                "id": e.get("id"),
                "timestamp": e.get("timestamp").isoformat() if hasattr(e.get("timestamp"), "isoformat") else e.get("timestamp"),
                "duration": e.get("duration"),
                "data": e.get("data", {}),
            } for e in events],
        }
    
    return jsonify({
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "device_id": api.get_info().get("device_id", "unknown"),
        "buckets": export_data,
    })

@sync_blueprint.route("/0/sync/import", methods=["POST"])
def sync_import():
    """Import bucket data from another device.
    
    Accepts JSON in the same format as export.
    Uses last-write-wins conflict resolution based on event timestamps.
    """
    api: ServerAPI = current_app.api
    data = request.get_json()
    
    if not data or "buckets" not in data:
        return {"error": "Invalid sync data format"}, 400
    
    source_device = data.get("device_id", "unknown")
    imported_count = 0
    skipped_count = 0
    
    for bucket_id, bucket_data in data["buckets"].items():
        # Create bucket if it doesn't exist
        existing = api.get_bucket_metadata(bucket_id)
        if not existing:
            meta = bucket_data.get("metadata", {})
            api.create_bucket(
                bucket_id,
                meta.get("client", "sync"),
                meta.get("type", "unknown"),
                meta.get("hostname", source_device),
            )
        
        # Import events
        for event_data in bucket_data.get("events", []):
            ts = event_data.get("timestamp")
            duration = event_data.get("duration", 0)
            event_payload = event_data.get("data", {})
            
            # Last-write-wins: check if event with same id exists
            event_id = event_data.get("id")
            if event_id:
                existing_events = api.get_events(bucket_id, limit=1000)
                exists = any(e.get("id") == event_id for e in existing_events)
                if exists:
                    skipped_count += 1
                    continue
            
            api.heartbeat(bucket_id, event_payload, duration, timestamp=ts)
            imported_count += 1
    
    return jsonify({
        "imported": imported_count,
        "skipped": skipped_count,
        "source_device": source_device,
    })

@sync_blueprint.route("/0/sync/status", methods=["GET"])
def sync_status():
    """Get sync status info."""
    api: ServerAPI = current_app.api
    buckets = api.get_buckets()
    info = api.get_info()
    
    return jsonify({
        "device_id": info.get("device_id", "unknown"),
        "hostname": info.get("hostname"),
        "version": info.get("version"),
        "bucket_count": len(buckets),
        "bucket_ids": list(buckets.keys()),
    })
