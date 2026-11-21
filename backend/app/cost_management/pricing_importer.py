import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal
from .models import PricingProduct, PricingRate


REGIONS = {
    "us-east-1": "US East (N. Virginia)",
    "ap-south-1": "Asia Pacific (Mumbai)",
}

# EBS is included in AmazonEC2 pricing.
# Each entry is an AWS Price List service code.
SERVICE_CODES = [
    "AmazonEC2",
    "AmazonRDS",
    "AmazonEKS",
    "AmazonS3",
    "AmazonVPC",
    "ElasticLoadBalancing",
    "AWSDataTransfer",
]

CURRENCY = "USD"
PROVIDER = "aws_price_list"


def parse_datetime(value):
    if not value:
        return datetime.now(timezone.utc)

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def import_product(db, raw_product, region_code):
    document = json.loads(raw_product)

    product = document.get("product", {})
    sku = product.get("sku")
    service_code = document.get("serviceCode")
    attributes = product.get("attributes", {})

    if not sku or not service_code:
        return 0

    if attributes.get("location") != REGIONS[region_code]:
        return 0

    existing = db.scalar(
        select(PricingProduct).where(
            PricingProduct.provider == PROVIDER,
            PricingProduct.sku == sku,
        )
    )

    if existing:
        pricing_product = existing
        pricing_product.attributes_json = json.dumps(attributes)
        pricing_product.region = region_code
    else:
        pricing_product = PricingProduct(
            provider=PROVIDER,
            sku=sku,
            service_code=service_code,
            region=region_code,
            attributes_json=json.dumps(attributes),
        )
        db.add(pricing_product)
        db.flush()

    inserted_rates = 0
    on_demand = document.get("terms", {}).get("OnDemand", {})

    for term in on_demand.values():
        effective_from = parse_datetime(term.get("effectiveDate"))

        for dimension in term.get("priceDimensions", {}).values():
            rate_code = dimension.get("rateCode")
            unit = dimension.get("unit")
            prices = dimension.get("pricePerUnit", {})

            if not rate_code or not unit or CURRENCY not in prices:
                continue

            try:
                amount = Decimal(prices[CURRENCY])
            except (InvalidOperation, TypeError):
                continue

            if amount < 0:
                continue

            exists = db.scalar(
                select(PricingRate.id).where(
                    PricingRate.product_id == pricing_product.id,
                    PricingRate.rate_code == rate_code,
                    PricingRate.effective_from == effective_from,
                )
            )

            if exists:
                continue

            db.add(
                PricingRate(
                    product_id=pricing_product.id,
                    rate_code=rate_code,
                    unit=unit,
                    currency=CURRENCY,
                    price_per_unit=amount,
                    effective_from=effective_from,
                    effective_to=None,
                    source_version=document.get("version"),
                )
            )
            inserted_rates += 1

    return inserted_rates


def import_catalog():
    endpoint_region = os.getenv(
        "PRICING_API_REGION", "us-east-1"
    )

    session = boto3.Session()
    client = session.client(
        "pricing",
        region_name=endpoint_region,
    )

    db = SessionLocal()

    summary = {
        "regions": {},
        "products_processed": 0,
        "rates_inserted": 0,
        "errors": [],
    }

    try:
        for region_code, location_name in REGIONS.items():
            region_summary = {
                "location": location_name,
                "services": {},
            }

            for service_code in SERVICE_CODES:
                print(
                    f"Importing {service_code} "
                    f"for {region_code}..."
                )

                next_token = None
                processed = 0
                inserted = 0

                while True:
                    request = {
                        "ServiceCode": service_code,
                        "FormatVersion": "aws_v1",
                        "MaxResults": 100,
                        "Filters": [
                            {
                                "Type": "TERM_MATCH",
                                "Field": "location",
                                "Value": location_name,
                            }
                        ],
                    }

                    if next_token:
                        request["NextToken"] = next_token

                    response = client.get_products(**request)

                    try:
                        for raw_product in response.get("PriceList", []):
                            inserted += import_product(
                                db,
                                raw_product,
                                region_code,
                            )
                            processed += 1

                        db.commit()

                    except Exception:
                        db.rollback()
                        raise

                    next_token = response.get("NextToken")

                    if not next_token:
                        break

                region_summary["services"][service_code] = {
                    "products_processed": processed,
                    "rates_inserted": inserted,
                }

                summary["products_processed"] += processed
                summary["rates_inserted"] += inserted

            summary["regions"][region_code] = region_summary

        return summary

    finally:
        db.close()


if __name__ == "__main__":
    try:
        result = import_catalog()
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"Pricing import failed: {type(exc).__name__}: {exc}")
        raise
