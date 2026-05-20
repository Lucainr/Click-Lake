from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CampaignProfile:
    code: str
    view_rate: float
    click_rate: float
    product_view_after_click_rate: float
    add_to_cart_after_pv_rate: float
    invalid_multiplier: float


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    campaign_name: str
    profile: CampaignProfile


@dataclass(frozen=True)
class Promotion:
    promotion_id: str
    promotion_name: str
    campaign_id: str
    campaign_name: str
    placement: str
    creative_id: str
    creative_type: str
    position_index: int


@dataclass(frozen=True)
class Product:
    product_id: str
    product_name: str
    category_id: str
    category_name: str
    unit_price: int


class PartitionedEventWriter:
    """Write raw JSONL in the same partitioned format used by server storage."""

    def __init__(self, base_dir: Path, max_events_per_file: int) -> None:
        self.base_dir = base_dir
        self.max_events_per_file = max_events_per_file
        self._state: dict[str, dict[str, Any]] = {}

    def _line_count(self, file_path: Path) -> int:
        if not file_path.exists():
            return 0
        with file_path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)

    def _scan_partition(self, partition_dir: Path) -> tuple[int, Path, int]:
        seq_to_file: list[tuple[int, Path]] = []
        if partition_dir.exists():
            for path in partition_dir.iterdir():
                if not path.is_file() or not path.name.startswith("events-") or not path.name.endswith(".jsonl"):
                    continue
                core = path.name.replace("events-", "").replace(".jsonl", "")
                if not core.isdigit() or len(core) != 4:
                    continue
                seq_to_file.append((int(core), path))

        if not seq_to_file:
            seq = 1
            file_path = partition_dir / "events-0001.jsonl"
            return seq, file_path, 0

        seq_to_file.sort(key=lambda item: item[0])
        seq, file_path = seq_to_file[-1]
        count = self._line_count(file_path)
        return seq, file_path, count

    def _ensure_partition_state(self, date_key: str) -> dict[str, Any]:
        state = self._state.get(date_key)
        if state is not None:
            return state

        partition_dir = self.base_dir / f"date={date_key}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        seq, file_path, line_count = self._scan_partition(partition_dir)
        handle = file_path.open("a", encoding="utf-8")

        state = {
            "partition_dir": partition_dir,
            "seq": seq,
            "file_path": file_path,
            "line_count": line_count,
            "handle": handle,
        }
        self._state[date_key] = state
        return state

    def write_event(self, received_at: str, sdk_key: str, event: dict[str, Any]) -> None:
        date_key = received_at[:10]
        state = self._ensure_partition_state(date_key)

        if state["line_count"] >= self.max_events_per_file:
            state["handle"].close()
            state["seq"] += 1
            state["file_path"] = state["partition_dir"] / f"events-{state['seq']:04d}.jsonl"
            state["handle"] = state["file_path"].open("a", encoding="utf-8")
            state["line_count"] = 0

        record = {
            "received_at": received_at,
            "sdk_key": sdk_key,
            "event": event,
        }
        state["handle"].write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        state["line_count"] += 1

    def close(self) -> None:
        for state in self._state.values():
            handle = state.get("handle")
            if handle:
                handle.close()


class ApiBatchSender:
    def __init__(
        self,
        collect_url: str,
        batch_size: int,
        concurrency: int,
        timeout_seconds: float,
    ) -> None:
        self.collect_url = collect_url
        self.batch_size = batch_size
        self.concurrency = max(1, concurrency)
        self.timeout_seconds = timeout_seconds
        self._buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._executor = ThreadPoolExecutor(max_workers=self.concurrency)
        self._inflight: set[Future[int]] = set()
        self.sent_batches = 0
        self.sent_events = 0

    def _post_batch(self, sdk_key: str, events: list[dict[str, Any]]) -> int:
        payload = {
            "sdk_key": sdk_key,
            "events": events,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.collect_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"collect returned status={response.status}")
                response.read()
        except HTTPError as exc:
            raise RuntimeError(f"collect HTTPError status={exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"collect URLError reason={exc.reason}") from exc

        return len(events)

    def _drain_one(self) -> None:
        if not self._inflight:
            return
        done, not_done = wait(self._inflight, return_when=FIRST_COMPLETED)
        self._inflight = set(not_done)
        for future in done:
            sent = future.result()
            self.sent_events += sent
            self.sent_batches += 1

    def _submit(self, sdk_key: str, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        future = self._executor.submit(self._post_batch, sdk_key, events)
        self._inflight.add(future)
        if len(self._inflight) >= self.concurrency * 2:
            self._drain_one()

    def add_event(self, sdk_key: str, event: dict[str, Any]) -> None:
        buffer = self._buffers[sdk_key]
        buffer.append(event)
        if len(buffer) >= self.batch_size:
            self._submit(sdk_key, buffer[:])
            buffer.clear()

    def flush(self) -> None:
        for sdk_key, buffer in self._buffers.items():
            if buffer:
                self._submit(sdk_key, buffer[:])
                buffer.clear()

        while self._inflight:
            self._drain_one()

    def close(self) -> None:
        try:
            self.flush()
        finally:
            self._executor.shutdown(wait=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate large Click Lake test events for Bronze/Silver/Gold validation.",
    )
    parser.add_argument("--events", type=int, default=200_000, help="Total events to generate (default: 200000)")
    parser.add_argument("--days", type=int, default=14, help="Spread event_time over recent N days")
    parser.add_argument("--sdk-keys", type=int, default=5, help="Number of distinct sdk_key values")
    parser.add_argument("--campaigns", type=int, default=20, help="Number of campaigns")
    parser.add_argument("--promotions", type=int, default=100, help="Number of promotions")
    parser.add_argument("--products", type=int, default=500, help="Number of products")
    parser.add_argument("--invalid-ratio", type=float, default=0.03, help="Fraction of events intentionally invalid")
    parser.add_argument("--duplicate-ratio", type=float, default=0.01, help="Fraction of events reusing event_id")
    parser.add_argument("--direct-ratio", type=float, default=0.6, help="In file mode, share written to direct raw")
    parser.add_argument("--mode", choices=["api", "file", "both"], default="api", help="Output mode")
    parser.add_argument("--collect-url", default="http://localhost:8000/collect", help="Collect endpoint for API mode")
    parser.add_argument("--batch-size", type=int, default=500, help="Collect API batch size")
    parser.add_argument("--concurrency", type=int, default=10, help="Collect API concurrent workers")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout per request")
    parser.add_argument("--max-events-per-file", type=int, default=1000, help="File mode rolling max lines per file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--progress-every", type=int, default=10_000, help="Progress log interval")
    parser.add_argument(
        "--file-direct-dir",
        default="server/data/raw_events",
        help="Direct raw output root for file mode",
    )
    parser.add_argument(
        "--file-kafka-dir",
        default="server/data/raw_events_kafka",
        help="Kafka raw output root for file mode",
    )
    return parser.parse_args()


def clamp_ratio(value: float, name: str) -> float:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def build_reference_data(args: argparse.Namespace) -> tuple[list[str], list[Campaign], dict[str, list[Promotion]], list[Product]]:
    sdk_keys = [f"clk_live_sim_{idx:03d}" for idx in range(1, args.sdk_keys + 1)]

    profiles = [
        CampaignProfile("A", view_rate=0.88, click_rate=0.42, product_view_after_click_rate=0.66, add_to_cart_after_pv_rate=0.18, invalid_multiplier=0.8),
        CampaignProfile("B", view_rate=0.83, click_rate=0.18, product_view_after_click_rate=0.82, add_to_cart_after_pv_rate=0.33, invalid_multiplier=0.9),
        CampaignProfile("C", view_rate=0.80, click_rate=0.29, product_view_after_click_rate=0.53, add_to_cart_after_pv_rate=0.14, invalid_multiplier=1.7),
        CampaignProfile("D", view_rate=0.92, click_rate=0.09, product_view_after_click_rate=0.41, add_to_cart_after_pv_rate=0.10, invalid_multiplier=1.0),
    ]

    campaigns: list[Campaign] = []
    for idx in range(1, args.campaigns + 1):
        profile = profiles[(idx - 1) % len(profiles)]
        campaigns.append(
            Campaign(
                campaign_id=f"camp_{profile.code.lower()}_{idx:03d}",
                campaign_name=f"Campaign {profile.code}-{idx:03d}",
                profile=profile,
            )
        )

    promotions_by_campaign: dict[str, list[Promotion]] = defaultdict(list)
    placements = ["main_hero", "category_top", "product_reco", "cart_sidebar"]
    creative_types = ["image", "video", "carousel"]

    for idx in range(1, args.promotions + 1):
        campaign = campaigns[(idx - 1) % len(campaigns)]
        placement = placements[(idx - 1) % len(placements)]
        promotion = Promotion(
            promotion_id=f"promo_{idx:04d}",
            promotion_name=f"Promotion {idx:04d}",
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            placement=placement,
            creative_id=f"creative_{idx:04d}",
            creative_type=creative_types[(idx - 1) % len(creative_types)],
            position_index=((idx - 1) % 5) + 1,
        )
        promotions_by_campaign[campaign.campaign_id].append(promotion)

    products: list[Product] = []
    categories = [
        ("cat_outer", "Outerwear"),
        ("cat_top", "Top"),
        ("cat_bottom", "Bottom"),
        ("cat_shoes", "Shoes"),
        ("cat_acc", "Accessories"),
    ]
    for idx in range(1, args.products + 1):
        category_id, category_name = categories[(idx - 1) % len(categories)]
        price = 39000 + ((idx * 1700) % 210000)
        products.append(
            Product(
                product_id=f"prod_{idx:05d}",
                product_name=f"Product {idx:05d}",
                category_id=category_id,
                category_name=category_name,
                unit_price=price,
            )
        )

    return sdk_keys, campaigns, promotions_by_campaign, products


def iso_from_recent_days(rng: random.Random, days: int) -> str:
    now = datetime.now(timezone.utc)
    day_offset = rng.randint(0, max(0, days - 1))
    seconds = rng.randint(0, 86_399)
    dt = now - timedelta(days=day_offset, seconds=seconds)
    return dt.isoformat().replace("+00:00", "Z")


def random_id(prefix: str, rng: random.Random) -> str:
    return f"{prefix}_{rng.getrandbits(64):016x}"


def maybe_duplicate_event_id(
    rng: random.Random,
    seen_event_ids: list[str],
    duplicate_ratio: float,
    stats: Counter,
) -> str:
    if seen_event_ids and rng.random() < duplicate_ratio:
        stats["duplicate_events"] += 1
        return rng.choice(seen_event_ids)

    event_id = random_id("evt", rng)
    seen_event_ids.append(event_id)
    return event_id


def maybe_invalidate_event(
    event: dict[str, Any],
    event_type: str,
    rng: random.Random,
    invalid_ratio: float,
    profile: CampaignProfile,
    stats: Counter,
) -> None:
    if event_type == "page_view":
        return

    effective_invalid = min(1.0, invalid_ratio * profile.invalid_multiplier)
    if rng.random() >= effective_invalid:
        return

    stats["invalid_events"] += 1

    if event_type in {"promotion_view", "promotion_click"}:
        drop_field = rng.choice(["promotion_id", "promotion_name", "campaign_id", "placement"])
        event.pop(drop_field, None)
        stats[f"invalid_{event_type}_{drop_field}"] += 1
        return

    if event_type in {"product_view", "add_to_cart"}:
        event.pop("product_id", None)
        stats[f"invalid_{event_type}_product_id"] += 1


def build_base_context(sdk_key: str, session_id: str, event_time: str, rng: random.Random) -> dict[str, Any]:
    return {
        "sdk_key": sdk_key,
        "session_id": session_id,
        "event_time": event_time,
        "page_url": rng.choice(["/", "/home", "/category", "/product", "/campaign"]),
        "page_title": rng.choice(["Home", "Category", "Product", "Campaign"]),
        "referrer_url": rng.choice([None, "https://search.example.com", "https://ads.example.com"]),
        "device_type": rng.choice(["desktop", "mobile", "tablet"]),
        "os_name": rng.choice(["macOS", "Windows", "iOS", "Android"]),
        "browser_name": rng.choice(["Chrome", "Safari", "Edge", "Firefox"]),
        "language": rng.choice(["en-US", "ko-KR", "ja-JP"]),
        "country": rng.choice(["US", "KR", "JP", "SG"]),
        "viewport_width": rng.choice([390, 430, 768, 1024, 1440]),
        "viewport_height": rng.choice([844, 932, 1024, 900, 1200]),
        "anonymous_id": random_id("anon", rng),
        "user_id": None,
        "event_version": 1,
    }


def generate_session_events(
    rng: random.Random,
    sdk_keys: list[str],
    campaigns: list[Campaign],
    promotions_by_campaign: dict[str, list[Promotion]],
    products: list[Product],
    invalid_ratio: float,
    duplicate_ratio: float,
    days: int,
    seen_event_ids: list[str],
    stats: Counter,
) -> list[tuple[str, dict[str, Any]]]:
    sdk_key = rng.choice(sdk_keys)
    session_id = random_id("sess", rng)
    campaign = rng.choice(campaigns)
    promotion = rng.choice(promotions_by_campaign[campaign.campaign_id])
    product = rng.choice(products)

    events: list[tuple[str, dict[str, Any]]] = []

    def append_event(event_type: str, payload: dict[str, Any]) -> None:
        event_id = maybe_duplicate_event_id(rng, seen_event_ids, duplicate_ratio, stats)
        payload["event_id"] = event_id
        payload["event_type"] = event_type
        maybe_invalidate_event(payload, event_type, rng, invalid_ratio, campaign.profile, stats)
        events.append((sdk_key, payload))
        stats["events_total"] += 1
        stats[f"event_type_{event_type}"] += 1

    # 1) page_view always
    event_time = iso_from_recent_days(rng, days)
    base = build_base_context(sdk_key, session_id, event_time, rng)
    page_event = {
        **base,
        "page_type": rng.choice(["home", "category", "product", "campaign"]),
    }
    append_event("page_view", page_event)

    # 2) promotion_view
    if rng.random() < campaign.profile.view_rate:
        event_time = iso_from_recent_days(rng, days)
        pv_base = build_base_context(sdk_key, session_id, event_time, rng)
        promotion_view_event = {
            **pv_base,
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "promotion_id": promotion.promotion_id,
            "promotion_name": promotion.promotion_name,
            "placement": promotion.placement,
            "creative_id": promotion.creative_id,
            "creative_type": promotion.creative_type,
            "position_index": promotion.position_index,
        }
        append_event("promotion_view", promotion_view_event)

        # 3) promotion_click
        clicked = rng.random() < campaign.profile.click_rate
        if clicked:
            event_time = iso_from_recent_days(rng, days)
            click_base = build_base_context(sdk_key, session_id, event_time, rng)
            promotion_click_event = {
                **click_base,
                "campaign_id": campaign.campaign_id,
                "campaign_name": campaign.campaign_name,
                "promotion_id": promotion.promotion_id,
                "promotion_name": promotion.promotion_name,
                "placement": promotion.placement,
                "creative_id": promotion.creative_id,
                "creative_type": promotion.creative_type,
                "position_index": promotion.position_index,
                "click_target_url": f"/product/{product.product_id}",
                "click_x": rng.randint(20, 900),
                "click_y": rng.randint(20, 900),
            }
            append_event("promotion_click", promotion_click_event)

            # 4) product_view
            if rng.random() < campaign.profile.product_view_after_click_rate:
                event_time = iso_from_recent_days(rng, days)
                prod_base = build_base_context(sdk_key, session_id, event_time, rng)
                product_view_event = {
                    **prod_base,
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "category_id": product.category_id,
                    "category_name": product.category_name,
                    "source_promotion_id": promotion.promotion_id,
                    "source_campaign_id": campaign.campaign_id,
                }
                append_event("product_view", product_view_event)

                # 5) add_to_cart
                if rng.random() < campaign.profile.add_to_cart_after_pv_rate:
                    event_time = iso_from_recent_days(rng, days)
                    atc_base = build_base_context(sdk_key, session_id, event_time, rng)
                    add_to_cart_event = {
                        **atc_base,
                        "product_id": product.product_id,
                        "product_name": product.product_name,
                        "category_id": product.category_id,
                        "category_name": product.category_name,
                        "quantity": rng.choice([1, 1, 1, 2, 2, 3]),
                        "unit_price": product.unit_price,
                        "currency": "USD",
                        "source_promotion_id": promotion.promotion_id,
                        "source_campaign_id": campaign.campaign_id,
                    }
                    append_event("add_to_cart", add_to_cart_event)

    return events


def run_simulation(args: argparse.Namespace) -> int:
    clamp_ratio(args.invalid_ratio, "invalid_ratio")
    clamp_ratio(args.duplicate_ratio, "duplicate_ratio")
    clamp_ratio(args.direct_ratio, "direct_ratio")

    if args.events <= 0:
        raise ValueError("events must be greater than zero")
    if args.days <= 0:
        raise ValueError("days must be greater than zero")

    rng = random.Random(args.seed)
    sdk_keys, campaigns, promotions_by_campaign, products = build_reference_data(args)

    print("[simulate] start")
    print(
        f"[simulate] mode={args.mode} events={args.events} days={args.days} "
        f"sdk_keys={len(sdk_keys)} campaigns={len(campaigns)} promotions={sum(len(v) for v in promotions_by_campaign.values())} products={len(products)}"
    )
    print(
        f"[simulate] invalid_ratio={args.invalid_ratio:.4f} duplicate_ratio={args.duplicate_ratio:.4f} direct_ratio={args.direct_ratio:.4f} seed={args.seed}"
    )

    direct_writer: PartitionedEventWriter | None = None
    kafka_writer: PartitionedEventWriter | None = None
    sender: ApiBatchSender | None = None

    if args.mode in {"file", "both"}:
        direct_writer = PartitionedEventWriter(Path(args.file_direct_dir), args.max_events_per_file)
        kafka_writer = PartitionedEventWriter(Path(args.file_kafka_dir), args.max_events_per_file)

    if args.mode in {"api", "both"}:
        sender = ApiBatchSender(
            collect_url=args.collect_url,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout_seconds,
        )

    stats: Counter = Counter()
    seen_event_ids: list[str] = []

    generated = 0
    session_count = 0

    try:
        while generated < args.events:
            session_count += 1
            session_events = generate_session_events(
                rng=rng,
                sdk_keys=sdk_keys,
                campaigns=campaigns,
                promotions_by_campaign=promotions_by_campaign,
                products=products,
                invalid_ratio=args.invalid_ratio,
                duplicate_ratio=args.duplicate_ratio,
                days=args.days,
                seen_event_ids=seen_event_ids,
                stats=stats,
            )

            for sdk_key, event in session_events:
                if generated >= args.events:
                    break

                generated += 1

                # file mode: split source between direct and kafka roots
                if args.mode in {"file", "both"}:
                    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    source_direct = rng.random() < args.direct_ratio
                    if source_direct:
                        assert direct_writer is not None
                        direct_writer.write_event(received_at, sdk_key, event)
                        stats["source_direct"] += 1
                    else:
                        assert kafka_writer is not None
                        kafka_writer.write_event(received_at, sdk_key, event)
                        stats["source_kafka"] += 1

                # api mode: send through /collect pipeline
                if args.mode in {"api", "both"}:
                    assert sender is not None
                    sender.add_event(sdk_key, event)
                    stats["source_api_collect"] += 1

                if generated % args.progress_every == 0 or generated == args.events:
                    print(
                        f"[simulate] progress events={generated}/{args.events} "
                        f"sessions={session_count} invalid={stats['invalid_events']} duplicates={stats['duplicate_events']}"
                    )

        if sender is not None:
            sender.close()

    finally:
        if direct_writer is not None:
            direct_writer.close()
        if kafka_writer is not None:
            kafka_writer.close()

    print("[simulate] completed")
    print(f"[simulate] generated_events={generated} sessions={session_count}")
    print(f"[simulate] invalid_events={stats['invalid_events']} duplicate_events={stats['duplicate_events']}")

    if args.mode in {"file", "both"}:
        total_source = stats["source_direct"] + stats["source_kafka"]
        direct_share = (stats["source_direct"] / total_source) if total_source else 0.0
        kafka_share = (stats["source_kafka"] / total_source) if total_source else 0.0
        print(
            "[simulate] file_source_distribution "
            f"direct={stats['source_direct']} ({direct_share:.2%}) "
            f"kafka={stats['source_kafka']} ({kafka_share:.2%})"
        )

    if sender is not None:
        print(
            f"[simulate] api_send_summary batches={sender.sent_batches} sent_events={sender.sent_events} "
            f"collect_url={args.collect_url}"
        )

    event_types = ["page_view", "promotion_view", "promotion_click", "product_view", "add_to_cart"]
    breakdown = ", ".join(f"{etype}={stats[f'event_type_{etype}']}" for etype in event_types)
    print(f"[simulate] event_type_breakdown {breakdown}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_simulation(args)
    except Exception as exc:  # pragma: no cover
        print(f"[simulate] failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
