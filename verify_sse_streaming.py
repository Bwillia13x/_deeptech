#!/usr/bin/env python3
"""Manual SSE streaming verification test.

This script tests the Server-Sent Events (SSE) endpoint to ensure:
1. Connection establishes correctly
2. Events stream in real-time
3. Progress updates are received
4. Connection closes properly on completion

Run this while the API server is running:
    python verify_sse_streaming.py
"""
import asyncio
import httpx
import json
import os
import sys
from datetime import datetime


async def test_sse_stream():
    """Test SSE streaming endpoint with a real bulk operation."""
    base_url = "http://localhost:8000"
    
    # API key is optional - only needed if HARVEST_API_KEY is set in server env
    api_key = os.getenv("HARVEST_API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    
    print("🧪 SSE Streaming Verification Test")
    print("=" * 60)
    if api_key:
        print("ℹ️  Using API key authentication")
    else:
        print("ℹ️  No API key configured (optional)")
    
    # Step 1: Start a bulk operation
    print("\n1️⃣  Starting bulk status update operation...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Use bulk status update with a minimal scope to trigger SSE
        response = await client.post(
            f"{base_url}/signals/bulk/status",
            headers=headers,
            json={
                "filters": {"status": "active"},  # Update all active signals
                "status": "active",  # Keep them active (no-op update)
            },
        )
        if response.status_code != 200:
            print(f"❌ Failed to start bulk operation: {response.status_code}")
            print(response.text)
            return False
        
        job_data = response.json()
        job_id = job_data["jobId"]
        print(f"✅ Bulk job started: {job_id}")
        print(f"   Total items: {job_data['total']}")
    
    # Step 2: Connect to SSE stream
    print(f"\n2️⃣  Connecting to SSE stream at /bulk-jobs/{job_id}/stream...")
    event_count = 0
    last_done = 0
    start_time = datetime.now()
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "GET",
                f"{base_url}/bulk-jobs/{job_id}/stream",
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    print(f"❌ Failed to connect to SSE: {response.status_code}")
                    return False
                
                # Verify headers
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    print(f"❌ Wrong content type: {content_type}")
                    return False
                
                cache_control = response.headers.get("cache-control", "")
                connection = response.headers.get("connection", "")
                print("✅ SSE connection established")
                print(f"   Content-Type: {content_type}")
                print(f"   Cache-Control: {cache_control}")
                print(f"   Connection: {connection}")
                
                print("\n3️⃣  Receiving events...")
                print("-" * 60)
                
                # Read events
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    if line.startswith("data: "):
                        event_count += 1
                        data = json.loads(line[6:])
                        
                        # Extract progress info
                        status = data.get("status", "unknown")
                        total = data.get("total", 0)
                        done = data.get("done", 0)
                        fail = data.get("fail", 0)
                        
                        # Show progress
                        if done != last_done:
                            pct = (done / total * 100) if total > 0 else 0
                            print(f"Event #{event_count}: [{status}] {done}/{total} ({pct:.1f}%) - {fail} failed")
                            last_done = done
                        
                        # Check if job finished
                        if status in ["completed", "cancelled", "failed"]:
                            print(f"\n✅ Job finished with status: {status}")
                            break
    
    except httpx.ReadTimeout:
        print("❌ Stream timed out")
        return False
    except Exception as e:
        print(f"❌ Error during stream: {e}")
        return False
    
    # Step 3: Verify results
    duration = (datetime.now() - start_time).total_seconds()
    print("-" * 60)
    print(f"\n4️⃣  Verification Summary:")
    print(f"   ✅ Events received: {event_count}")
    print(f"   ✅ Duration: {duration:.2f}s")
    print(f"   ✅ Final progress: {last_done}/{job_data['total']}")
    
    if event_count == 0:
        print("   ⚠️  Warning: No events received!")
        return False
    
    if event_count < 2:
        print("   ⚠️  Warning: Expected multiple progress events")
    
    print("\n🎉 SSE streaming verification PASSED")
    return True


async def main():
    """Run the verification test."""
    print("Starting SSE verification test...")
    print("Ensure the API server is running on http://localhost:8000")
    print()
    
    try:
        success = await test_sse_stream()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
