"""Utility script to generate representative benchmark log datasets for testing."""

import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "sample_logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 1. HDFS log template patterns (standard Loghub benchmark style)
HDFS_TEMPLATES = [
    "081109 {time} 26 INFO dfs.DataNode$DataXceiver: Receiving block blk_{blk_id} src: /10.{ip1}.{ip2}.{ip3}:{port} dest: /10.{ip1}.{ip2}.{ip4}:50010",
    "081109 {time} 29 INFO dfs.DataNode$DataXceiver: Received block blk_{blk_id} of size {size} from /10.{ip1}.{ip2}.{ip3}",
    "081109 {time} 31 INFO dfs.FSNamesystem: BLOCK* NameSystem.addStoredBlock: blockMap updated: 10.{ip1}.{ip2}.{ip3}:50010 is added to blk_{blk_id} size {size}",
    "081109 {time} 35 INFO dfs.FSNamesystem: BLOCK* ask 10.{ip1}.{ip2}.{ip3}:50010 to replicate blk_{blk_id} to datanode(s) 10.{ip1}.{ip2}.{ip4}:50010",
    "081109 {time} 40 INFO dfs.DataNode$BlockReceiver: PacketResponder {resp_id} for block blk_{blk_id} terminating",
    "081109 {time} 44 WARN dfs.DataNode$DataXceiver: 10.{ip1}.{ip2}.{ip3}:50010:Got exception while serving blk_{blk_id} to /10.{ip1}.{ip2}.{ip4}: java.net.SocketTimeoutException: 60000 millis timeout while waiting for channel to be ready for read",
    "081109 {time} 47 INFO dfs.FSNamesystem: BLOCK* NameSystem.delete: blk_{blk_id} is added to invalidSet of 10.{ip1}.{ip2}.{ip3}:50010",
    "081109 {time} 50 ERROR dfs.DataNode$PacketResponder: Exception in PacketResponder {resp_id} for block blk_{blk_id} java.io.IOException: Connection reset by peer",
]

# 2. Modern Cloud / Microservices incident patterns
MICROSERVICE_TEMPLATES = [
    '{time} [INFO] [auth-service] [req-{uuid}] User {user_id} authenticated successfully from 192.168.1.{ip}',
    '{time} [INFO] [order-service] [req-{uuid}] Created order {order_id} for customer {user_id} total: ${price}',
    '{time} [INFO] [payment-service] [req-{uuid}] Payment transaction {tx_id} completed via gateway stripe status: 200',
    '{time} [WARN] [inventory-service] [req-{uuid}] Low stock threshold reached for sku {sku_id} remaining: {count}',
    '{time} [ERROR] [payment-service] [req-{uuid}] Connection to payment-gateway-api:8443 timed out after {timeout}ms',
    '{time} [ERROR] [database-service] [req-{uuid}] Query timeout after {timeout}ms on table users executing 0x{hex_addr}',
    '{time} [CRITICAL] [order-service] [req-{uuid}] Unhandled exception NullPointerException at OrderProcessor.java:142 trace_id: 0x{hex_addr}',
    '{time} [ERROR] [ingress-gateway] [req-{uuid}] Upstream 502 Bad Gateway while connecting to upstream service http://order-service:8080',
]

def generate_logs(templates, filename, count=5000):
    output_path = DATA_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        for i in range(count):
            tmpl = random.choice(templates)
            line = tmpl.format(
                time=f"2026-10-02 10:{random.randint(10, 59)}:{random.randint(10, 59)}",
                blk_id=random.randint(1000000000, 9999999999),
                ip1=random.randint(1, 254),
                ip2=random.randint(1, 254),
                ip3=random.randint(1, 254),
                ip4=random.randint(1, 254),
                ip=random.randint(1, 254),
                port=random.randint(1024, 65535),
                size=random.randint(1024, 67108864),
                resp_id=random.randint(1, 100),
                uuid=f"{random.randint(100000, 999999)}-{random.randint(1000, 9999)}",
                user_id=random.randint(1000, 99999),
                order_id=random.randint(50000, 99999),
                price=random.randint(10, 500),
                tx_id=f"tx_{random.randint(1000000, 9999999)}",
                sku_id=f"SKU-{random.randint(100, 999)}",
                count=random.randint(0, 15),
                timeout=random.choice([3000, 5000, 10000, 30000]),
                hex_addr=f"{random.randint(0x1000, 0xFFFF):x}",
            )
            f.write(line + "\n")
    print(f"Generated {count} lines into {output_path}")

if __name__ == "__main__":
    generate_logs(HDFS_TEMPLATES, "sample_hdfs.log", 5000)
    generate_logs(MICROSERVICE_TEMPLATES, "sample_microservice.log", 5000)
