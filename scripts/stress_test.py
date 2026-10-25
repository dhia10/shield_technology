"""
Shield Technology - Synthetic Telemetry Stress-Tester & Attack Simulator
Weeks 9-11: High-concurrency attack generator simulating SSH Brute Force, SQLi, DDoS,
Port Scans, and Malware Detections. Benchmarks throughput (events/sec) and p50/p95/p99 latency.
"""

import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from app.main import app
from app.security import compute_hmac_signature, API_KEY, HMAC_SECRET

ATTACK_TYPES = [
    {
        "event_type": "SQL_INJECTION_ATTEMPT",
        "severity": "CRITICAL",
        "payloads": [
            {"query": "admin' OR '1'='1' --", "target_table": "users", "password": "TargetPassClearText999!"},
            {"query": "UNION SELECT username, password, token FROM admin_credentials", "source": "sqlmap/1.8"},
            {"query": "1; DROP TABLE telemetry_events; --", "input_field": "search_param"},
        ]
    },
    {
        "event_type": "AUTH_ATTEMPT",
        "severity": "HIGH",
        "payloads": [
            {"service": "SSH", "user": "root", "password": "admin_root_password_123", "result": "FAILURE"},
            {"service": "SSH", "user": "admin", "password": "SuperSecretDevToken!", "result": "FAILURE"},
            {"service": "FTP", "user": "anonymous", "token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "result": "FAILURE"},
        ]
    },
    {
        "event_type": "DDOS_FLOOD",
        "severity": "CRITICAL",
        "payloads": [
            {"protocol": "SYN_FLOOD", "packets_per_sec": 85000, "target_port": 443},
            {"protocol": "UDP_AMPLIFICATION", "bandwidth_gbps": 12.5, "reflected_from": "NTP_DNS"},
        ]
    },
    {
        "event_type": "MALWARE_DETECTED",
        "severity": "CRITICAL",
        "payloads": [
            {"malware_family": "LockBit3.0", "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {"malware_family": "Mirai_Botnet", "process_name": "busybox_arm", "c2_server": "185.220.101.5"},
        ]
    },
    {
        "event_type": "PORT_SCAN",
        "severity": "MEDIUM",
        "payloads": [
            {"scan_type": "SYN_STEALTH", "scanned_ports": [21, 22, 23, 80, 443, 3306, 5432, 8080]},
        ]
    },
    {
        "event_type": "SYSTEM_HEARTBEAT",
        "severity": "LOW",
        "payloads": [
            {"cpu_utilization": 42.5, "memory_free_mb": 4096, "disk_pct": 58.1},
        ]
    }
]

SOURCE_IPS = [
    "197.14.88.22", "197.14.88.23", "196.203.45.10", "45.33.32.156",
    "185.220.101.4", "185.220.101.5", "104.244.72.115", "192.168.1.100"
]

AGENTS = [
    "probe-tunis-dc-01", "probe-sousse-core-02", "probe-sfax-edge-03",
    "probe-bizerte-perimeter-04"
]


def generate_synthetic_event() -> Dict[str, Any]:
    attack_profile = random.choice(ATTACK_TYPES)
    payload = random.choice(attack_profile["payloads"])
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": random.choice(AGENTS),
        "severity": attack_profile["severity"],
        "event_type": attack_profile["event_type"],
        "source_ip": random.choice(SOURCE_IPS),
        "destination_ip": "10.0.0.5",
        "payload": payload,
    }


async def run_stress_test(
    total_events: int = 10000,
    batch_size: int = 100,
    concurrency: int = 10,
) -> Dict[str, Any]:
    """
    Executes stress test sending `total_events` in batches via async HTTP client.
    """
    transport = httpx.ASGITransport(app=app)
    latencies_ms: List[float] = []
    total_batches = total_events // batch_size
    sent_count = 0
    failed_count = 0

    semaphore = asyncio.Semaphore(concurrency)

    async def send_batch(batch_events: List[Dict[str, Any]], client: httpx.AsyncClient):
        nonlocal sent_count, failed_count
        body = json.dumps({"events": batch_events}).encode("utf-8")
        signature = compute_hmac_signature(body, HMAC_SECRET)
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            "X-HMAC-Signature": signature,
        }

        async with semaphore:
            t0 = time.perf_counter()
            try:
                response = await client.post(
                    "http://testserver/api/v1/telemetry/ingest",
                    content=body,
                    headers=headers,
                )
                t1 = time.perf_counter()
                latency = (t1 - t0) * 1000
                latencies_ms.append(latency)

                if response.status_code == 202:
                    sent_count += len(batch_events)
                else:
                    failed_count += len(batch_events)
            except Exception as e:
                failed_count += len(batch_events)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        start_overall = time.perf_counter()

        tasks = []
        for _ in range(total_batches):
            batch = [generate_synthetic_event() for _ in range(batch_size)]
            tasks.append(send_batch(batch, client))

        await asyncio.gather(*tasks)
        end_overall = time.perf_counter()

    elapsed_sec = end_overall - start_overall
    throughput = sent_count / elapsed_sec if elapsed_sec > 0 else 0

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms) if latencies_ms else 0
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0
    mean_lat = statistics.mean(latencies_ms) if latencies_ms else 0

    return {
        "total_requested": total_events,
        "total_sent_accepted": sent_count,
        "total_failed": failed_count,
        "elapsed_seconds": round(elapsed_sec, 3),
        "throughput_events_per_sec": round(throughput, 1),
        "latency_mean_ms": round(mean_lat, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "batch_size": batch_size,
        "concurrency": concurrency,
        "loss_rate_pct": 0.0 if sent_count == total_events else round((failed_count / total_events) * 100, 2),
    }


if __name__ == "__main__":
    print("=== Shield Technology Telemetry Ingestion Stress-Tester ===")
    results = asyncio.run(run_stress_test(total_events=10000, batch_size=100, concurrency=10))
    print(json.dumps(results, indent=2))
