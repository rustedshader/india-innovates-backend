#!/usr/bin/env python3
"""Seed script for city metadata."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from models.database import SessionLocal
from models.city_metadata import CityMetadata

# Based on INDIA_CITIES from scrapers/weather.py
INDIAN_CITIES = [
    {"city_name": "Delhi", "latitude": 28.6139, "longitude": 77.2090, "zone": "plains", "state": "Delhi", "elevation_meters": 216, "is_india_seed": True},
    {"city_name": "Mumbai", "latitude": 19.0760, "longitude": 72.8777, "zone": "coastal", "state": "Maharashtra", "elevation_meters": 14, "is_india_seed": True},
    {"city_name": "Chennai", "latitude": 13.0827, "longitude": 80.2707, "zone": "coastal", "state": "Tamil Nadu", "elevation_meters": 7, "is_india_seed": True},
    {"city_name": "Kolkata", "latitude": 22.5726, "longitude": 88.3639, "zone": "plains", "state": "West Bengal", "elevation_meters": 9, "is_india_seed": True},
    {"city_name": "Bangalore", "latitude": 12.9716, "longitude": 77.5946, "zone": "plains", "state": "Karnataka", "elevation_meters": 920, "is_india_seed": True},
    {"city_name": "Hyderabad", "latitude": 17.3850, "longitude": 78.4867, "zone": "plains", "state": "Telangana", "elevation_meters": 542, "is_india_seed": True},
    {"city_name": "Ahmedabad", "latitude": 23.0225, "longitude": 72.5714, "zone": "plains", "state": "Gujarat", "elevation_meters": 53, "is_india_seed": True},
    {"city_name": "Pune", "latitude": 18.5204, "longitude": 73.8567, "zone": "plains", "state": "Maharashtra", "elevation_meters": 560, "is_india_seed": True},
    {"city_name": "Jaipur", "latitude": 26.9124, "longitude": 75.7873, "zone": "plains", "state": "Rajasthan", "elevation_meters": 431, "is_india_seed": True},
    {"city_name": "Lucknow", "latitude": 26.8467, "longitude": 80.9462, "zone": "plains", "state": "Uttar Pradesh", "elevation_meters": 123, "is_india_seed": True},
    {"city_name": "Bhopal", "latitude": 23.2599, "longitude": 77.4126, "zone": "plains", "state": "Madhya Pradesh", "elevation_meters": 527, "is_india_seed": True},
    {"city_name": "Patna", "latitude": 25.6093, "longitude": 85.1376, "zone": "plains", "state": "Bihar", "elevation_meters": 53, "is_india_seed": True},
    {"city_name": "Guwahati", "latitude": 26.1445, "longitude": 91.7362, "zone": "plains", "state": "Assam", "elevation_meters": 55, "is_india_seed": True},
    {"city_name": "Bhubaneswar", "latitude": 20.2961, "longitude": 85.8245, "zone": "coastal", "state": "Odisha", "elevation_meters": 45, "is_india_seed": True},
    {"city_name": "Thiruvananthapuram", "latitude": 8.5241, "longitude": 76.9366, "zone": "coastal", "state": "Kerala", "elevation_meters": 16, "is_india_seed": True},
    {"city_name": "Chandigarh", "latitude": 30.7333, "longitude": 76.7794, "zone": "plains", "state": "Chandigarh", "elevation_meters": 321, "is_india_seed": True},
    {"city_name": "Dehradun", "latitude": 30.3165, "longitude": 78.0322, "zone": "hills", "state": "Uttarakhand", "elevation_meters": 640, "is_india_seed": True},
    {"city_name": "Srinagar", "latitude": 34.0837, "longitude": 74.7973, "zone": "hills", "state": "Jammu and Kashmir", "elevation_meters": 1585, "is_india_seed": True},
    {"city_name": "Leh", "latitude": 34.1526, "longitude": 77.5771, "zone": "hills", "state": "Ladakh", "elevation_meters": 3524, "is_india_seed": True},
    {"city_name": "Jodhpur", "latitude": 26.2389, "longitude": 73.0243, "zone": "plains", "state": "Rajasthan", "elevation_meters": 231, "is_india_seed": True},
    {"city_name": "Nagpur", "latitude": 21.1458, "longitude": 79.0882, "zone": "plains", "state": "Maharashtra", "elevation_meters": 310, "is_india_seed": True},
    {"city_name": "Visakhapatnam", "latitude": 17.6868, "longitude": 83.2185, "zone": "coastal", "state": "Andhra Pradesh", "elevation_meters": 45, "is_india_seed": True},
    {"city_name": "Shillong", "latitude": 25.5788, "longitude": 91.8933, "zone": "hills", "state": "Meghalaya", "elevation_meters": 1496, "is_india_seed": True},
    {"city_name": "Gangtok", "latitude": 27.3389, "longitude": 88.6065, "zone": "hills", "state": "Sikkim", "elevation_meters": 1650, "is_india_seed": True},
    {"city_name": "Port Blair", "latitude": 11.6234, "longitude": 92.7265, "zone": "coastal", "state": "Andaman and Nicobar Islands", "elevation_meters": 7, "is_india_seed": True},
]


def seed_city_metadata():
    """Seed city metadata for all Indian cities."""
    db = SessionLocal()
    try:
        print("Seeding city metadata...")

        for city_data in INDIAN_CITIES:
            # Check if exists
            stmt = select(CityMetadata).where(
                CityMetadata.city_name == city_data["city_name"]
            )
            existing = db.execute(stmt).scalar_one_or_none()

            if existing:
                print(f"  ✓ City already exists: {city_data['city_name']} ({city_data['zone']})")
            else:
                new_city = CityMetadata(**city_data)
                db.add(new_city)
                print(
                    f"  + Added: {city_data['city_name']} ({city_data['zone']}, "
                    f"{city_data['state']}, elevation={city_data['elevation_meters']}m)"
                )

        db.commit()
        print(f"✓ Successfully seeded {len(INDIAN_CITIES)} cities")

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding city metadata: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_city_metadata()
