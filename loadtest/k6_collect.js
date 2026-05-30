import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const TARGET_URL = __ENV.TARGET_URL || 'http://localhost:8000/collect';
const TEST_TYPE = (__ENV.TEST_TYPE || 'smoke').toLowerCase(); // smoke | load | stress | all
const RUN_ID = __ENV.RUN_ID || `${Date.now()}`;
const SDK_KEYS = (__ENV.SDK_KEYS || 'clk_k6_a,clk_k6_b,clk_k6_c,clk_k6_d,clk_k6_e').split(',').map((s) => s.trim()).filter(Boolean);
const DAYS = Number(__ENV.DAYS || 14);
const INVALID_RATIO = Number(__ENV.INVALID_RATIO || 0.03);
const DUPLICATE_RATIO = Number(__ENV.DUPLICATE_RATIO || 0.01);
const SLEEP_MS = Number(__ENV.SLEEP_MS || 200);

const collectSuccess = new Counter('collect_success_total');
const collectFailure = new Counter('collect_failure_total');
const payloadBytes = new Trend('collect_payload_bytes', false);
const invalidEventRate = new Rate('collect_invalid_event_rate');

const campaignProfiles = [
  { code: 'A', viewRate: 0.9, clickRate: 0.42, productRate: 0.64, addRate: 0.16, invalidBoost: 0.8 },
  { code: 'B', viewRate: 0.84, clickRate: 0.2, productRate: 0.8, addRate: 0.31, invalidBoost: 0.9 },
  { code: 'C', viewRate: 0.78, clickRate: 0.3, productRate: 0.55, addRate: 0.12, invalidBoost: 1.8 },
  { code: 'D', viewRate: 0.93, clickRate: 0.08, productRate: 0.4, addRate: 0.09, invalidBoost: 1.0 },
];

function buildScenarios(mode) {
  const smoke = {
    executor: 'constant-vus',
    vus: 5,
    duration: '1m',
    tags: { scenario: 'smoke' },
  };

  const load = {
    executor: 'ramping-vus',
    startVUs: 20,
    stages: [
      { duration: '2m', target: 60 },
      { duration: '4m', target: 100 },
      { duration: '2m', target: 40 },
    ],
    gracefulRampDown: '30s',
    tags: { scenario: 'load' },
  };

  const stress = {
    executor: 'ramping-vus',
    startVUs: 30,
    stages: [
      { duration: '2m', target: 120 },
      { duration: '3m', target: 220 },
      { duration: '3m', target: 300 },
      { duration: '2m', target: 80 },
    ],
    gracefulRampDown: '30s',
    tags: { scenario: 'stress' },
  };

  if (mode === 'smoke') return { smoke };
  if (mode === 'load') return { load };
  if (mode === 'stress') return { stress };
  return { smoke, load, stress };
}

export const options = {
  scenarios: buildScenarios(TEST_TYPE),
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1200', 'p(99)<2500'],
    checks: ['rate>0.99'],
    collect_failure_total: ['count<10'],
  },
};

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function chance(probability) {
  return Math.random() < probability;
}

function pick(arr) {
  return arr[randomInt(0, arr.length - 1)];
}

function isoWithinDays(days) {
  const now = Date.now();
  const backMs = randomInt(0, Math.max(0, days - 1)) * 24 * 3600 * 1000 + randomInt(0, 24 * 3600 * 1000 - 1);
  return new Date(now - backMs).toISOString();
}

function maybeDuplicateEventId(baseId) {
  if (chance(DUPLICATE_RATIO)) {
    return `evt_dup_${RUN_ID}_${Math.floor(baseId / 50)}`;
  }
  return `evt_${RUN_ID}_${baseId}`;
}

function maybeInvalidate(event, eventType, profile) {
  if (eventType === 'page_view') {
    invalidEventRate.add(0);
    return;
  }

  const effectiveInvalid = Math.min(1.0, INVALID_RATIO * profile.invalidBoost);
  if (!chance(effectiveInvalid)) {
    invalidEventRate.add(0);
    return;
  }

  if (eventType === 'promotion_view' || eventType === 'promotion_click') {
    const fields = ['promotion_id', 'promotion_name', 'campaign_id', 'placement'];
    const field = pick(fields);
    delete event[field];
  } else if (eventType === 'product_view' || eventType === 'add_to_cart') {
    delete event.product_id;
  }

  invalidEventRate.add(1);
}

function buildSessionEvents(seq) {
  const sdkKey = pick(SDK_KEYS);
  const sessionId = `sess_${RUN_ID}_${__VU}_${__ITER}_${seq}`;
  const profile = pick(campaignProfiles);
  const campaignNum = randomInt(1, 20);
  const promotionNum = randomInt(1, 100);
  const productNum = randomInt(1, 500);

  const campaignId = `camp_${profile.code.toLowerCase()}_${String(campaignNum).padStart(3, '0')}`;
  const campaignName = `Campaign ${profile.code}-${String(campaignNum).padStart(3, '0')}`;
  const promotionId = `promo_${String(promotionNum).padStart(4, '0')}`;
  const promotionName = `Promotion ${String(promotionNum).padStart(4, '0')}`;
  const productId = `prod_${String(productNum).padStart(5, '0')}`;

  const base = {
    session_id: sessionId,
    page_url: pick(['/', '/home', '/category', '/product']),
    page_title: pick(['Home', 'Category', 'Product']),
    event_version: 1,
    anonymous_id: `anon_${RUN_ID}_${__VU}_${seq}`,
    language: pick(['ko-KR', 'en-US', 'ja-JP']),
    country: pick(['KR', 'US', 'JP']),
    device_type: pick(['desktop', 'mobile']),
    os_name: pick(['macOS', 'Windows', 'iOS', 'Android']),
    browser_name: pick(['Chrome', 'Safari', 'Edge']),
    viewport_width: pick([390, 768, 1024, 1440]),
    viewport_height: pick([844, 900, 1024]),
  };

  const events = [];

  const pageView = {
    ...base,
    event_id: maybeDuplicateEventId(seq * 10 + 1),
    event_type: 'page_view',
    event_time: isoWithinDays(DAYS),
  };
  events.push(pageView);

  if (chance(profile.viewRate)) {
    const promotionView = {
      ...base,
      event_id: maybeDuplicateEventId(seq * 10 + 2),
      event_type: 'promotion_view',
      event_time: isoWithinDays(DAYS),
      campaign_id: campaignId,
      campaign_name: campaignName,
      promotion_id: promotionId,
      promotion_name: promotionName,
      placement: pick(['main_hero', 'category_top', 'cart_sidebar']),
      creative_id: `creative_${promotionNum}`,
      creative_type: pick(['image', 'video', 'carousel']),
      position_index: randomInt(1, 5),
    };
    maybeInvalidate(promotionView, 'promotion_view', profile);
    events.push(promotionView);

    if (chance(profile.clickRate)) {
      const promotionClick = {
        ...base,
        event_id: maybeDuplicateEventId(seq * 10 + 3),
        event_type: 'promotion_click',
        event_time: isoWithinDays(DAYS),
        campaign_id: campaignId,
        campaign_name: campaignName,
        promotion_id: promotionId,
        promotion_name: promotionName,
        placement: pick(['main_hero', 'category_top', 'cart_sidebar']),
        creative_id: `creative_${promotionNum}`,
        creative_type: pick(['image', 'video', 'carousel']),
        position_index: randomInt(1, 5),
        click_target_url: `/product/${productId}`,
        click_x: randomInt(20, 980),
        click_y: randomInt(20, 980),
      };
      maybeInvalidate(promotionClick, 'promotion_click', profile);
      events.push(promotionClick);

      if (chance(profile.productRate)) {
        const productView = {
          ...base,
          event_id: maybeDuplicateEventId(seq * 10 + 4),
          event_type: 'product_view',
          event_time: isoWithinDays(DAYS),
          product_id: productId,
          product_name: `Product ${String(productNum).padStart(5, '0')}`,
          category_id: pick(['cat_outer', 'cat_top', 'cat_bottom', 'cat_shoes']),
          category_name: pick(['Outerwear', 'Top', 'Bottom', 'Shoes']),
          source_promotion_id: promotionId,
          source_campaign_id: campaignId,
        };
        maybeInvalidate(productView, 'product_view', profile);
        events.push(productView);

        if (chance(profile.addRate)) {
          const addToCart = {
            ...base,
            event_id: maybeDuplicateEventId(seq * 10 + 5),
            event_type: 'add_to_cart',
            event_time: isoWithinDays(DAYS),
            product_id: productId,
            product_name: `Product ${String(productNum).padStart(5, '0')}`,
            category_id: pick(['cat_outer', 'cat_top', 'cat_bottom', 'cat_shoes']),
            category_name: pick(['Outerwear', 'Top', 'Bottom', 'Shoes']),
            quantity: pick([1, 1, 1, 2, 2, 3]),
            unit_price: randomInt(39000, 249000),
            currency: 'KRW',
            source_promotion_id: promotionId,
            source_campaign_id: campaignId,
          };
          maybeInvalidate(addToCart, 'add_to_cart', profile);
          events.push(addToCart);
        }
      }
    }
  }

  return { sdkKey, events };
}

export default function () {
  const seq = __VU * 10000000 + __ITER;
  const session = buildSessionEvents(seq);

  const payload = JSON.stringify({
    sdk_key: session.sdkKey,
    events: session.events,
  });

  payloadBytes.add(payload.length);

  const res = http.post(TARGET_URL, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: '/collect' },
    timeout: '30s',
  });

  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'response has success=true': (r) => {
      try {
        const body = JSON.parse(r.body || '{}');
        return body.success === true;
      } catch (e) {
        return false;
      }
    },
  });

  if (ok) {
    collectSuccess.add(1);
  } else {
    collectFailure.add(1);
  }

  sleep(SLEEP_MS / 1000);
}
