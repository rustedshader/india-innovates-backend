"""Reset script — clears Kafka topic offsets and all Redis state.

Usage:
    python -m scripts.reset          # clear both Kafka + Redis
    python -m scripts.reset --redis  # Redis only
    python -m scripts.reset --kafka  # Kafka only
"""

import argparse
import sys

import redis
from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import UnknownTopicOrPartitionError

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, REDIS_HOST, REDIS_PORT

CONSUMER_GROUP = "india-innovates-pipeline"
REDIS_KEY_PREFIX = "india-innovates:*"
CLUSTER_KEY_PREFIX = "cluster:*"


def reset_redis():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()

    # Gather all keys we own
    keys = list(r.scan_iter(REDIS_KEY_PREFIX)) + list(r.scan_iter(CLUSTER_KEY_PREFIX))
    if keys:
        r.delete(*keys)
        print(f"  Deleted {len(keys)} Redis keys")
    else:
        print("  No matching Redis keys found")


def reset_kafka():
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)

    # Delete topic (purges all messages and consumer offsets)
    try:
        admin.delete_topics([KAFKA_TOPIC])
        print(f"  Deleted topic '{KAFKA_TOPIC}'")
    except UnknownTopicOrPartitionError:
        print(f"  Topic '{KAFKA_TOPIC}' does not exist, skipping delete")

    # Re-create the topic with defaults
    import time
    time.sleep(2)  # allow broker to finish deletion
    try:
        admin.create_topics([NewTopic(name=KAFKA_TOPIC, num_partitions=1, replication_factor=1)])
        print(f"  Re-created topic '{KAFKA_TOPIC}'")
    except Exception as e:
        print(f"  Could not re-create topic (may already exist): {e}")

    admin.close()


def main():
    parser = argparse.ArgumentParser(description="Reset Kafka + Redis state for a fresh test run")
    parser.add_argument("--redis", action="store_true", help="Reset Redis only")
    parser.add_argument("--kafka", action="store_true", help="Reset Kafka only")
    args = parser.parse_args()

    do_both = not args.redis and not args.kafka

    if do_both or args.redis:
        print("Resetting Redis...")
        reset_redis()

    if do_both or args.kafka:
        print("Resetting Kafka...")
        reset_kafka()

    print("Done.")


if __name__ == "__main__":
    main()
