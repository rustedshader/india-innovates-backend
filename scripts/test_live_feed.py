#!/usr/bin/env python3
"""Test script to publish fake articles to the live feed Redis channel.

Usage:
    python scripts/test_live_feed.py
"""

import json
import random
import time
from datetime import datetime

import redis

# Adjust these if your Redis is elsewhere
REDIS_HOST = "localhost"
REDIS_PORT = 6379
LIVE_FEED_CHANNEL = "india-innovates:live-feed"

# Sample test articles
SAMPLE_ARTICLES = [
    {
        "title": "India and Japan Strengthen Defense Cooperation in Indo-Pacific",
        "source": "The Hindu",
        "url": "https://www.thehindu.com/news/sample-1",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 8.5,
    },
    {
        "title": "RBI Announces New Monetary Policy Framework",
        "source": "Economic Times",
        "url": "https://economictimes.indiatimes.com/sample-2",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 7.2,
    },
    {
        "title": "Climate Change Impact on Monsoon Patterns Studied",
        "source": "The Times of India",
        "url": "https://timesofindia.indiatimes.com/sample-3",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 6.8,
    },
    {
        "title": "New AI Research Center Opens in Bangalore",
        "source": "Deccan Herald",
        "url": "https://www.deccanherald.com/sample-4",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 5.5,
    },
    {
        "title": "Border Security Enhanced with New Technology",
        "source": "India Today",
        "url": "https://www.indiatoday.in/sample-5",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 9.1,
    },
    {
        "title": "Trade Agreement Negotiations Progress with EU",
        "source": "Business Standard",
        "url": "https://www.business-standard.com/sample-6",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 7.8,
    },
    {
        "title": "Renewable Energy Targets Revised Upward",
        "source": "Mint",
        "url": "https://www.livemint.com/sample-7",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 6.3,
    },
    {
        "title": "Cybersecurity Threats Increase in Financial Sector",
        "source": "The Hindu BusinessLine",
        "url": "https://www.thehindubusinessline.com/sample-8",
        "thumbnail": "https://via.placeholder.com/150",
        "importance_score": 8.2,
    },
]


def main():
    print("=" * 60)
    print("Live Feed Test Publisher")
    print(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    print(f"Channel: {LIVE_FEED_CHANNEL}")
    print("=" * 60)

    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis\n")
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        return

    print("Publishing test articles (Ctrl+C to stop)...")
    print("Will publish 1 article every 3-5 seconds\n")

    try:
        count = 0
        while True:
            # Pick a random article
            article = random.choice(SAMPLE_ARTICLES)

            # Create event message matching backend format
            event = {
                "url": f"{article['url']}?test={count}",  # Make URLs unique
                "title": article["title"],
                "source": article["source"],
                "thumbnail": article["thumbnail"],
                "pub_date": datetime.now().isoformat(),
                "status": random.choice(["scraped", "processing", "indexed"]),
                "timestamp": datetime.now().isoformat(),
                "importance_score": article["importance_score"],
            }

            # Publish to Redis channel
            r.publish(LIVE_FEED_CHANNEL, json.dumps(event))

            count += 1
            print(f"[{count}] Published: {article['title'][:50]}... (score: {article['importance_score']})")

            # Wait random interval
            time.sleep(random.uniform(3, 5))

    except KeyboardInterrupt:
        print(f"\n\n✅ Published {count} test articles. Exiting.")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
